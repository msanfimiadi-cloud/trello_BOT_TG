from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=data) for label, data in row] for row in rows])


def preview_keyboard() -> InlineKeyboardMarkup:
    return keyboard([[('Всё верно', 'preview:ok')], [('Отправить исправленный текст', 'preview:edit'), ('Отменить', 'all:cancel')]])


def deadline_keyboard(found: bool) -> InlineKeyboardMarkup:
    rows = [[('Подтвердить', 'due:confirm'), ('Изменить', 'due:input')], [('Без дедлайна', 'due:none')]] if found else [[('Сегодня', 'due:сегодня'), ('Завтра', 'due:завтра')], [('Послезавтра', 'due:послезавтра'), ('Без дедлайна', 'due:none')], [('Ввести дату', 'due:input')]]
    return keyboard(rows + [[('Пропустить задачу', 'task:skip'), ('Отменить всё', 'all:cancel')]])


def assignee_keyboard(team: dict[str, str]) -> InlineKeyboardMarkup:
    names = list(team)
    rows = [[(name, f'assignee:{name}') for name in names[i:i + 2]] for i in range(0, len(names), 2)]
    rows += [[('Указать вручную', 'assignee:manual'), ('Без ответственного', 'assignee:none')], [('Назад', 'assignee:back')], [('Пропустить задачу', 'task:skip'), ('Отменить всё', 'all:cancel')]]
    return keyboard(rows)


def confirmation_keyboard() -> InlineKeyboardMarkup:
    return keyboard([[('Создать карточку', 'card:create')], [('Изменить дедлайн', 'due:input'), ('Изменить ответственного', 'assignee:change')], [('Пропустить задачу', 'task:skip'), ('Отменить всё', 'all:cancel')]])


def retry_keyboard() -> InlineKeyboardMarkup:
    return keyboard([[('Повторить', 'card:create'), ('Изменить данные', 'card:edit')], [('Пропустить задачу', 'task:skip'), ('Отменить всё', 'all:cancel')]])
