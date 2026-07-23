"""
Telegram-бот: разбирает текст с итогами встречи на отдельные задачи
и создаёт по каждой карточку в Trello, уточняя недостающие данные
(дедлайн и ответственного) прямо в диалоге.

Установка:
    pip install python-telegram-bot==21.* requests

Перед запуском впишите BOT_TOKEN ниже (остальное уже заполнено).
"""

import re
import logging
from datetime import datetime

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)

# ======================= CONFIG =======================

BOT_TOKEN = "ВАШ_TELEGRAM_BOT_TOKEN"  # впишите новый токен (старый был скомпрометирован - перевыпустите через @BotFather)

TRELLO_KEY = "2093aa14fc250820779b3373f7e0e62f"
TRELLO_TOKEN = "ВАШ_TRELLO_TOKEN"  # впишите свой токен (в чат его присылать не нужно)
TRELLO_LIST_ID = "6979ed820aeacb7d2dab3fb2"  # список "Нужно сделать"

# Ответственные: имя -> Trello member ID
TEAM = {
    "Владислав": "66cc2b6234f1510f6962cc7e",
    "Эго": "69bcf0c00ab47d36b1c11dcf",
    "Эндуро": "6a0f0bc0a820f985e8484364",
    "Контекст": "6a1d2d9a1bd445140bd5c0c2",
    "Арчи": "6a101b90a82d7a48944c7f94",
    "Агент": "69aa7cbe0ae205cd7f31ff03",
    "Шарлотт": "698f3852204275a99a2a83fa",
    "Вектор": "69393d1bbe03cf40caf049a3",
    "Мелисса": "69a923c10b79c9eb41811bba",
}

# ======================= СОСТОЯНИЯ =======================

ASK_DEADLINE, CONFIRM_DEADLINE, ASK_ASSIGNEE, ASK_ASSIGNEE_MANUAL = range(4)

# ======================= ПАРСИНГ ТЕКСТА =======================

def parse_tasks(text: str):
    """Первая строка — заголовок встречи, дальше — нумерованные задачи."""
    lines = text.strip().split("\n", 1)
    title = lines[0].strip()
    body = lines[1] if len(lines) > 1 else ""

    raw_items = re.split(r"\n?\s*\d+\.\s+", body)
    tasks = [t.strip().replace("\n", " ") for t in raw_items if t.strip()]

    parsed = []
    for t in tasks:
        date_match = re.search(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\b", t)
        deadline = None
        if date_match:
            day, month, year = date_match.groups()
            year = year or datetime.now().year
            try:
                deadline = datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
            except ValueError:
                deadline = None
        parsed.append({"text": t, "deadline": deadline, "assignee": None})

    return title, parsed

# ======================= TRELLO =======================

def create_trello_card(name: str, due, member_id, desc: str = ""):
    url = "https://api.trello.com/1/cards"
    params = {
        "key": TRELLO_KEY,
        "token": TRELLO_TOKEN,
        "idList": TRELLO_LIST_ID,
        "name": name,
        "desc": desc,
    }
    if due:
        params["due"] = due
    if member_id:
        params["idMembers"] = member_id
    resp = requests.post(url, params=params)
    resp.raise_for_status()
    return resp.json()

# ======================= ЛОГИКА ДИАЛОГА =======================

def team_keyboard():
    buttons = [[InlineKeyboardButton(name, callback_data=f"assignee::{name}")] for name in TEAM]
    buttons.append([InlineKeyboardButton("Указать вручную", callback_data="assignee::manual")])
    return InlineKeyboardMarkup(buttons)


async def start_processing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title, tasks = parse_tasks(update.message.text)
    if not tasks:
        await update.message.reply_text(
            "Не нашёл нумерованных задач в сообщении. Формат: заголовок, "
            "потом пункты «1. ...», «2. ...» и т.д."
        )
        return ConversationHandler.END

    context.user_data["meeting_title"] = title
    context.user_data["tasks"] = tasks
    context.user_data["current"] = 0

    await update.message.reply_text(f"Нашёл {len(tasks)} задач(и). Разбираю по порядку.")
    return await process_current_task(update, context)


async def process_current_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = context.user_data["tasks"]
    idx = context.user_data["current"]

    if idx >= len(tasks):
        await (update.message or update.callback_query.message).reply_text(
            "Готово, все задачи занесены в Trello ✅"
        )
        return ConversationHandler.END

    task = tasks[idx]
    chat = update.message or update.callback_query.message

    if task["deadline"] is None:
        await chat.reply_text(
            f"Задача {idx + 1}: «{task['text']}»\n\nДедлайн не указан. Когда дедлайн? (в формате ДД.ММ, или напишите «нет»)"
        )
        return ASK_DEADLINE
    else:
        await chat.reply_text(
            f"Задача {idx + 1}: «{task['text']}»\n\nВ тексте нашёл дедлайн: {task['deadline']}. Всё верно?",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Да", callback_data="deadline_ok::yes"),
                  InlineKeyboardButton("Изменить", callback_data="deadline_ok::no")]]
            ),
        )
        return CONFIRM_DEADLINE


async def handle_deadline_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    idx = context.user_data["current"]
    task = context.user_data["tasks"][idx]

    if text.lower() != "нет":
        m = re.match(r"(\d{1,2})\.(\d{1,2})", text)
        if m:
            day, month = m.groups()
            task["deadline"] = datetime(datetime.now().year, int(month), int(day)).strftime("%Y-%m-%d")
        else:
            await update.message.reply_text("Не понял дату, формат ДД.ММ. Попробуйте ещё раз.")
            return ASK_DEADLINE

    await update.message.reply_text("Кто ответственный за эту задачу?", reply_markup=team_keyboard())
    return ASK_ASSIGNEE


async def handle_deadline_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = context.user_data["current"]
    task = context.user_data["tasks"][idx]

    if query.data == "deadline_ok::no":
        task["deadline"] = None
        await query.message.reply_text("Когда дедлайн? (ДД.ММ, или «нет»)")
        return ASK_DEADLINE

    await query.message.reply_text("Кто ответственный за эту задачу?", reply_markup=team_keyboard())
    return ASK_ASSIGNEE


async def handle_assignee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "assignee::manual":
        await query.message.reply_text("Напишите имя ответственного (просто текстом).")
        return ASK_ASSIGNEE_MANUAL

    _, name = query.data.split("::", 1)
    member_id = TEAM.get(name)
    return await finalize_task(update, context, name, member_id, chat=query.message)


async def handle_assignee_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    member_id = TEAM.get(name)  # если имя не заведено в TEAM - карточка создастся без назначения в Trello
    return await finalize_task(update, context, name, member_id, chat=update.message)


async def finalize_task(update, context, name, member_id, chat):
    idx = context.user_data["current"]
    task = context.user_data["tasks"][idx]
    task["assignee"] = name

    create_trello_card(
        name=task["text"],
        due=task["deadline"],
        member_id=member_id,
        desc=f"Из встречи: {context.user_data['meeting_title']}",
    )

    note = "" if member_id else " (не найден в TEAM, назначение в Trello не проставлено)"
    await chat.reply_text(
        f"✅ Карточка создана. Ответственный: {name}{note}, дедлайн: {task['deadline'] or 'не задан'}"
    )

    context.user_data["current"] += 1
    return await process_current_task(update, context)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END

# ======================= ЗАПУСК =======================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, start_processing)],
        states={
            ASK_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_deadline_text)],
            CONFIRM_DEADLINE: [CallbackQueryHandler(handle_deadline_confirm, pattern="^deadline_ok::")],
            ASK_ASSIGNEE: [CallbackQueryHandler(handle_assignee, pattern="^assignee::")],
            ASK_ASSIGNEE_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_assignee_manual)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    app.run_polling()


if __name__ == "__main__":
    main()
