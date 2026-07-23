import json

import pytest

from app.config import ConfigurationError, Settings


REQUIRED = {
    "TELEGRAM_BOT_TOKEN": "telegram-secret",
    "TRELLO_API_KEY": "trello-key",
    "TRELLO_API_TOKEN": "trello-token",
    "TRELLO_LIST_ID": "list-id",
    "ALLOWED_TELEGRAM_USER_IDS": "10, 20",
}


def configure(monkeypatch, **overrides):
    for name in (*REQUIRED, "BOT_TIMEZONE", "DATABASE_PATH", "TEAM_JSON"):
        monkeypatch.delenv(name, raising=False)
    for name, value in (REQUIRED | overrides).items():
        monkeypatch.setenv(name, value)


def test_settings_parses_all_values(monkeypatch, tmp_path):
    configure(monkeypatch, TEAM_JSON=json.dumps({"Иван": "member"}), BOT_TIMEZONE="UTC", DATABASE_PATH=str(tmp_path / "db.sqlite"))
    settings = Settings.from_env()
    assert settings.allowed_user_ids == frozenset({10, 20})
    assert settings.team == {"Иван": "member"}
    assert settings.timezone.key == "UTC"
    assert settings.database_path == tmp_path / "db.sqlite"


@pytest.mark.parametrize("value", ["", "not-json", "[]", '{"name": 1}'])
def test_invalid_team_json_is_clear(monkeypatch, value):
    configure(monkeypatch, TEAM_JSON=value)
    if value == "":
        assert Settings.from_env().team == {}
    else:
        with pytest.raises(ConfigurationError, match="TEAM_JSON"):
            Settings.from_env()


@pytest.mark.parametrize("value", ["", " , "])
def test_empty_allowlist_never_opens_access(monkeypatch, value):
    configure(monkeypatch, ALLOWED_TELEGRAM_USER_IDS=value)
    with pytest.raises(ConfigurationError, match="ALLOWED_TELEGRAM_USER_IDS"):
        Settings.from_env()


def test_invalid_timezone(monkeypatch):
    configure(monkeypatch, BOT_TIMEZONE="Definitely/Invalid")
    with pytest.raises(ConfigurationError, match="таймзон"):
        Settings.from_env()


def test_missing_secret_has_no_default(monkeypatch):
    configure(monkeypatch, TELEGRAM_BOT_TOKEN="")
    with pytest.raises(ConfigurationError, match="TELEGRAM_BOT_TOKEN"):
        Settings.from_env()
