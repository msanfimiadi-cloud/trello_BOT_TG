from app.keyboards import assignee_keyboard, confirmation_keyboard, deadline_keyboard, preview_keyboard, retry_keyboard


def test_all_callback_data_fits_telegram_limit():
    keyboards = [
        preview_keyboard(),
        deadline_keyboard(True),
        deadline_keyboard(False),
        assignee_keyboard({"Очень длинное имя сотрудника 🚀" * 20: "member"}),
        confirmation_keyboard(),
        retry_keyboard(),
    ]
    for keyboard in keyboards:
        for row in keyboard.inline_keyboard:
            for button in row:
                assert len(button.callback_data.encode("utf-8")) <= 64
