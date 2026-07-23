from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.dates import extract_date, parse_date

TZ = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 7, 2, 12, tzinfo=TZ)


def test_extract_short_date():
    assert extract_date("Сдать 16.07", TZ, NOW).strftime("%d.%m.%Y") == "16.07.2026"


def test_extract_full_date():
    assert extract_date("до 03.01.2028 включительно", TZ, NOW).date().isoformat() == "2028-01-03"


def test_two_digit_year():
    assert parse_date("03.01.28", TZ, NOW).year == 2028


@pytest.mark.parametrize("value", ["31.02", "12.13", "16.07 потом", "abc"])
def test_invalid_date(value):
    with pytest.raises(ValueError): parse_date(value, TZ, NOW)


def test_short_date_rolls_to_next_year():
    assert parse_date("01.07", TZ, NOW).date().isoformat() == "2027-07-01"


def test_relative_dates():
    assert parse_date("послезавтра", TZ, NOW).date().isoformat() == "2026-07-04"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("31.12", "2026-12-31"), ("01.01", "2027-01-01"), ("29.02.2028", "2028-02-29"), ("02.07", "2026-07-02")],
)
def test_boundaries_and_leap_year(value, expected):
    result = parse_date(value, TZ, NOW)
    assert result.date().isoformat() == expected
    assert result.hour == 18
    assert result.isoformat().endswith("+03:00")


def test_non_leap_day_is_invalid():
    with pytest.raises(ValueError, match="не существует"):
        parse_date("29.02.2027", TZ, NOW)
