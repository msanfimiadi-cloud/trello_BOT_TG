from datetime import datetime
from zoneinfo import ZoneInfo

from app.parser import card_description, card_title, parse_meeting

TZ = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 7, 2, 12, tzinfo=TZ)


def test_numbering_variants():
    title, tasks = parse_meeting("Встреча\n1. Первая\n2) Вторая\n3 - Третья\n4.Четвёртая", TZ, NOW)
    assert title == "Встреча"
    assert [task.text for task in tasks] == ["Первая", "Вторая", "Третья", "Четвёртая"]


def test_multiline_is_preserved():
    _, tasks = parse_meeting("Встреча\n1. Первая строка\nпродолжение\n2. Вторая", TZ, NOW)
    assert tasks[0].text == "Первая строка\nпродолжение"


def test_numbers_inside_sentence_do_not_split():
    _, tasks = parse_meeting("Встреча\n1. Купить 2 пачки и версию 3.0 сегодня", TZ, NOW)
    assert len(tasks) == 1


def test_title_removes_leading_date():
    assert card_title("16.07 — провести созвон") == "провести созвон"


def test_title_limit_does_not_cut_word():
    title = card_title("слово " * 40, 30)
    assert len(title) <= 30
    assert title == "слово слово слово слово слово"


def test_description_with_and_without_manual_assignee():
    base = card_description("Митинг", "Полный\nтекст")
    assert base == "Из встречи: Митинг\n\nИсходный текст:\nПолный\nтекст"
    assert card_description("Митинг", "Текст", "Иван").endswith("Ответственный, указанный вручную:\nИван")


def test_description_can_include_stable_task_reference():
    description = card_description("Митинг", "Текст", task_reference="task-uuid")
    assert description.endswith("Системный ID задачи: task-uuid")
