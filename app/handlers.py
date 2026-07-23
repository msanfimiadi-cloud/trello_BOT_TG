from __future__ import annotations

import logging
from datetime import datetime
from html import escape

from telegram import Update
from telegram.ext import ContextTypes

from .auth import access_required, admin_required
from .config import Settings
from .dates import display_date, parse_date
from .keyboards import admin_users_keyboard, assignee_keyboard, confirmation_keyboard, deadline_keyboard, preview_keyboard, retry_keyboard
from .models import Session, Task
from .parser import card_description, card_title, parse_meeting
from .storage import Storage
from .trello_client import TrelloClient, TrelloError

logger = logging.getLogger(__name__)
EXAMPLE = "Пост-мит Авито 02.07\n\n1. Подготовить отчёт\n2. 16.07 — провести созвон"


class BotHandlers:
    def __init__(self, settings: Settings, storage: Storage, trello: TrelloClient):
        self.settings, self.storage, self.trello = settings, storage, trello

    async def require_allowed(self, update: Update) -> bool:
        user = update.effective_user
        if user:
            await self.storage.touch_user(user.id, user.username, user.full_name)
        if user and await self.storage.has_access(user.id):
            return True
        if update.callback_query:
            await update.callback_query.answer("Нет доступа", show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text("У вас нет доступа к этому внутреннему боту.")
        return False

    async def require_admin(self, update: Update) -> bool:
        user = update.effective_user
        if user:
            await self.storage.touch_user(user.id, user.username, user.full_name)
        if user and await self.storage.is_admin(user.id):
            return True
        if update.callback_query:
            await update.callback_query.answer("Только для администратора", show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text("Команда доступна только администратору.")
        return False

    async def myid(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user:
            await self.storage.touch_user(user.id, user.username, user.full_name)
            await update.effective_message.reply_text(f"Ваш Telegram user ID: {user.id}")

    @access_required
    async def trello_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self.storage.get_user(update.effective_user.id)
        if not context.args:
            if user and user.trello_member_id:
                await update.effective_message.reply_text(
                    f"Связь активна ✅\nTelegram: {user.telegram_user_id}\nTrello: {user.trello_display_name}\nMember ID: {user.trello_member_id}\n\nЧтобы изменить связь: /trello <member_id>"
                )
            else:
                await update.effective_message.reply_text("Trello пока не привязан. Использование: /trello <member_id>")
            return
        if len(context.args) != 1:
            await update.effective_message.reply_text("Использование: /trello <member_id>")
            return
        member_id = context.args[0].strip()
        try:
            member = await self.trello.get_member(member_id)
            display_name = member.get("fullName") or member.get("username") or member_id
            await self.storage.link_trello(update.effective_user.id, member_id, display_name)
        except (TrelloError, ValueError) as exc:
            await update.effective_message.reply_text(f"Не удалось привязать Trello: {exc}")
            return
        await update.effective_message.reply_text(f"Trello привязан ✅\n{display_name}\nMember ID: {member_id}")

    @admin_required
    async def admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args
        if args and args[0].lower() in {"add", "grant", "remove", "revoke"}:
            if len(args) != 2:
                await update.effective_message.reply_text("Использование: /admin add <user_id> или /admin revoke <user_id>"); return
            try: target_id = int(args[1])
            except ValueError:
                await update.effective_message.reply_text("user_id должен быть целым числом."); return
            active = args[0].lower() in {"add", "grant"}
            changed = await self.storage.set_access(update.effective_user.id, target_id, active)
            logger.info("admin_access_changed admin_user_id=%s target_user_id=%s active=%s changed=%s", update.effective_user.id, target_id, active, changed)
            await update.effective_message.reply_text(("Доступ выдан." if active else "Доступ отозван.") if changed else "Нельзя отозвать доступ администратора.")
        await self._show_admin_page(update, 0)

    async def _show_admin_page(self, update: Update, page: int) -> None:
        users, total = await self.storage.list_users(max(page, 0))
        pages = max(1, (total + 7) // 8); page = min(max(page, 0), pages - 1)
        if page and not users: users, total = await self.storage.list_users(page)
        lines = [f"Пользователи — страница {page + 1}/{pages}:"]
        for user in users:
            label = user.full_name or (f"@{user.username}" if user.username else "без имени")
            status = "администратор" if user.is_admin else ("доступ есть" if user.is_active else "доступа нет")
            trello = user.trello_display_name or "Trello не привязан"
            lines.append(f"• {user.telegram_user_id} — {label} — {status} — {trello}")
        markup = admin_users_keyboard(users, page, pages)
        if update.callback_query:
            await update.callback_query.edit_message_text("\n".join(lines), reply_markup=markup)
        else:
            await update.effective_message.reply_text("\n".join(lines), reply_markup=markup)

    @access_required
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text("Я превращаю итоги встречи в отдельные карточки Trello.\n\nПример:\n" + EXAMPLE)

    @access_required
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text("Первая непустая строка — название встречи. Далее используйте 1., 1), 1 - или 1.Задача. Переносы внутри пункта сохраняются.\n\n" + EXAMPLE)

    @access_required
    async def new(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.storage.cancel(update.effective_user.id)
        await update.effective_message.reply_text("Текущая сессия отменена. Пришлите новый текст встречи.")

    cancel = new

    @access_required
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        session = await self.storage.load(update.effective_user.id)
        if not session:
            await update.effective_message.reply_text("Нет активной встречи."); return
        created = sum(t.status == "created" for t in session.tasks)
        skipped = sum(t.status == "skipped" for t in session.tasks)
        await update.effective_message.reply_text(f"Встреча: {session.meeting_title}\nПрогресс: {min(session.current_index + 1, len(session.tasks))} из {len(session.tasks)}\nСоздано: {created}, пропущено: {skipped}")

    @access_required
    async def check_trello(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            info = await self.trello.check_ready()
            await update.effective_message.reply_text(f"Trello доступен ✅\nСписок: {info.get('name', 'настроенный список')}")
        except TrelloError as exc:
            logger.exception("trello_check_failed user_id=%s error_class=%s", update.effective_user.id, type(exc).__name__)
            await update.effective_message.reply_text(f"Проверка Trello не пройдена: {exc}")

    @access_required
    async def text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        session = await self.storage.load(update.effective_user.id)
        if session and session.phase == "await_date":
            await self._date_text(update, session); return
        if session and session.phase == "await_assignee":
            task = session.tasks[session.current_index]
            task.assignee, task.member_id, task.manual_assignee = update.effective_message.text.strip(), None, True
            session.phase = "confirm"; await self.storage.save(session); await self.show_confirmation(update, session); return
        title, tasks = parse_meeting(update.effective_message.text, self.settings.timezone)
        if not tasks:
            await update.effective_message.reply_text("Не нашёл нумерованных задач. Правильный пример:\n\n" + EXAMPLE); return
        session = Session(update.effective_user.id, update.effective_chat.id, title, update.effective_message.text, tasks)
        await self.storage.save(session)
        logger.info("session_started user_id=%s task_count=%s", session.user_id, len(tasks))
        preview = "\n\n".join(f"{i}. {task.text}" for i, task in enumerate(tasks, 1))
        await update.effective_message.reply_text(f"Встреча: {title}\n\nНайденные задачи:\n\n{preview}", reply_markup=preview_keyboard())

    async def callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query.data.startswith("admin:"):
            if not await self.require_admin(update): return
            await query.answer()
            parts = query.data.split(":")
            if parts[1] == "page":
                await self._show_admin_page(update, int(parts[2])); return
            target_id, page = int(parts[2]), int(parts[3])
            active = not await self.storage.has_access(target_id)
            changed = await self.storage.set_access(update.effective_user.id, target_id, active)
            logger.info("admin_access_changed admin_user_id=%s target_user_id=%s active=%s changed=%s", update.effective_user.id, target_id, active, changed)
            await self._show_admin_page(update, page); return
        if not await self.require_allowed(update): return
        await query.answer()
        session = await self.storage.load(update.effective_user.id)
        if not session:
            await query.message.reply_text("Сессия не найдена. Пришлите текст встречи заново."); return
        data = query.data
        if data == "all:cancel": await self.storage.cancel(session.user_id); await query.edit_message_reply_markup(None); await query.message.reply_text("Обработка отменена."); return
        if data == "preview:edit": session.phase = "editing"; await self.storage.save(session); await query.edit_message_reply_markup(None); await query.message.reply_text("Пришлите исправленный текст целиком."); return
        if data == "preview:ok": await query.edit_message_reply_markup(None); session.phase = "deadline"; await self.storage.save(session); await self.show_task(update, session); return
        task = session.tasks[session.current_index]
        if data == "task:skip": task.status = "skipped"; await query.edit_message_reply_markup(None); await self._advance(update, session); return
        if data.startswith("due:"):
            choice = data.split(":", 1)[1]
            if choice == "input": session.phase = "await_date"; await self.storage.save(session); await query.edit_message_reply_markup(None); await query.message.reply_text("Введите дату целиком: ДД.ММ, ДД.ММ.ГГ или ДД.ММ.ГГГГ"); return
            if choice == "none": task.deadline, task.no_deadline = None, True
            elif choice != "confirm": task.deadline, task.no_deadline = parse_date(choice, self.settings.timezone).isoformat(), False
            session.phase = "assignee"; await self.storage.save(session); await query.edit_message_reply_markup(None); await self._ask_assignee(query.message); return
        if data.startswith("assignee:"):
            choice = data.split(":", 1)[1]
            if choice == "back": await self.show_task(update, session); return
            if choice == "change": await self._ask_assignee(query.message); return
            if choice == "manual": session.phase = "await_assignee"; await self.storage.save(session); await query.edit_message_reply_markup(None); await query.message.reply_text("Введите имя. Оно будет записано только в описание карточки."); return
            if choice.startswith("pick:"):
                try:
                    selected = await self.storage.get_user(int(choice.split(":", 1)[1]))
                except ValueError:
                    selected = None
                if not selected or not selected.is_active or not selected.trello_member_id:
                    await query.message.reply_text("Связь пользователя изменилась. Выберите ещё раз."); await self._ask_assignee(query.message); return
                task.assignee, task.member_id = selected.trello_display_name, selected.trello_member_id
            else:
                task.assignee, task.member_id = None, None
            task.manual_assignee = False
            session.phase = "confirm"; await self.storage.save(session); await query.edit_message_reply_markup(None); await self.show_confirmation(update, session); return
        if data == "card:edit": await self.show_task(update, session); return
        if data == "card:create": await self.create_card(update, session)

    async def _date_text(self, update: Update, session: Session) -> None:
        try: deadline = parse_date(update.effective_message.text, self.settings.timezone)
        except ValueError as exc:
            await update.effective_message.reply_text(f"Некорректная дата: {exc}. Попробуйте ещё раз."); return
        task = session.tasks[session.current_index]; task.deadline, task.no_deadline = (deadline.isoformat() if deadline else None), deadline is None
        session.phase = "assignee"; await self.storage.save(session)
        await update.effective_message.reply_text(f"Итоговая дата: {display_date(deadline)}")
        await self._ask_assignee(update.effective_message)

    async def _ask_assignee(self, message) -> None:
        users = await self.storage.list_linked_users()
        await message.reply_text("Кто ответственный?", reply_markup=assignee_keyboard(users))

    async def show_task(self, update: Update, session: Session) -> None:
        task = session.tasks[session.current_index]; session.phase = "deadline"; await self.storage.save(session)
        found = bool(task.deadline)
        text = f"Задача {session.current_index + 1} из {len(session.tasks)}\n\n{task.text}\n\nДедлайн: {display_date(task.deadline) if found else 'в тексте не найден'}"
        await update.effective_message.reply_text(text, reply_markup=deadline_keyboard(found))

    async def show_confirmation(self, update: Update, session: Session) -> None:
        task = session.tasks[session.current_index]
        description = card_description(
            session.meeting_title,
            task.text,
            task.assignee if task.manual_assignee else None,
            task.uuid,
        )
        assignee = "без ответственного" if not task.assignee else (f"{task.assignee} — имя указано только текстом ⚠️" if task.manual_assignee else task.assignee)
        await update.effective_message.reply_text(f"Задача {session.current_index + 1} из {len(session.tasks)}\n\nНазвание:\n{card_title(task.text)}\n\nОписание:\n{description}\n\nДедлайн:\n{display_date(task.deadline)}\n\nОтветственный:\n{assignee}", reply_markup=confirmation_keyboard())

    async def create_card(self, update: Update, session: Session) -> None:
        task = session.tasks[session.current_index]
        async with self.storage.creation_lock(task.uuid):
            latest = await self.storage.load(session.user_id); task = latest.tasks[latest.current_index]; session = latest
            if session.phase != "confirm":
                await update.effective_message.reply_text("Эта кнопка уже устарела. Используйте актуальные кнопки ниже.")
                return
            if task.status == "created":
                await update.effective_message.reply_text("Карточка уже создана.")
                return
            await update.callback_query.edit_message_reply_markup(None); task.status = "creating"; await self.storage.save(session)
            try:
                card = await self.trello.find_card_by_reference(task.uuid)
                if card is None:
                    description = card_description(
                        session.meeting_title,
                        task.text,
                        task.assignee if task.manual_assignee else None,
                        task.uuid,
                    )
                    card = await self.trello.create_card(
                        card_title(task.text), description, task.deadline, task.member_id
                    )
            except TrelloError as exc:
                task.status, task.last_error = "failed", str(exc); await self.storage.save(session)
                logger.exception("card_create_failed user_id=%s task_uuid=%s error_class=%s", session.user_id, task.uuid, type(exc).__name__)
                await update.effective_message.reply_text(f"Не удалось создать карточку в Trello.\n\nПричина: {exc}", reply_markup=retry_keyboard()); return
            task.status, task.card_id, task.card_url, task.created_at, task.last_error = "created", card["id"], card.get("url") or card.get("shortUrl"), datetime.now(self.settings.timezone).isoformat(), None
            await self.storage.save(session); logger.info("card_created user_id=%s card_id=%s", session.user_id, task.card_id)
            await update.effective_message.reply_text("Карточка создана ✅")
            await self._advance(update, session)

    async def _advance(self, update: Update, session: Session) -> None:
        session.current_index += 1
        if session.current_index < len(session.tasks): await self.storage.save(session); await self.show_task(update, session); return
        created = [t for t in session.tasks if t.status == "created"]; skipped = sum(t.status == "skipped" for t in session.tasks); errors = sum(t.status == "failed" for t in session.tasks)
        lines = ["Готово ✅", "", f"Встреча: {session.meeting_title}", f"Найдено задач: {len(session.tasks)}", f"Создано карточек: {len(created)}", f"Пропущено: {skipped}", f"Ошибок: {errors}"]
        lines += [f"• <a href=\"{escape(t.card_url)}\">{escape(card_title(t.text))}</a>" for t in created if t.card_url]
        await self.storage.cancel(session.user_id)
        text = "\n".join(lines)
        for start in range(0, len(text), 3900): await update.effective_message.reply_text(text[start:start + 3900], parse_mode="HTML", disable_web_page_preview=True)
