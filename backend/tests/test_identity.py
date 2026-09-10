"""Unit tests for age gate and identity helpers."""

from __future__ import annotations

from datetime import date

import pytest

from liftcam.core.identity import is_at_least_age


def test_exactly_thirteen_today_is_accepted() -> None:
    today = date(2026, 9, 10)
    dob = date(2013, 9, 10)
    assert is_at_least_age(dob, 13, today=today)


def test_day_before_thirteenth_birthday_is_rejected() -> None:
    today = date(2026, 9, 10)
    dob = date(2013, 9, 11)
    assert not is_at_least_age(dob, 13, today=today)


def test_leap_day_birthday_uses_march_first() -> None:
    dob = date(2012, 2, 29)
    assert not is_at_least_age(dob, 13, today=date(2025, 2, 28))
    assert is_at_least_age(dob, 13, today=date(2025, 3, 1))


def test_negative_min_age_raises() -> None:
    with pytest.raises(ValueError):
        is_at_least_age(date(2000, 1, 1), -1)
