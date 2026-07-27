from __future__ import annotations
from datetime import date, timedelta, timezone

from backend.services.workdays import last_n_workdays, workday_window


def test_last_n_workdays_wednesday():
    # 2026-07-29 is a Wednesday
    days = last_n_workdays(7, today=date(2026, 7, 29))
    assert days[0] == date(2026, 7, 21)
    assert days[-1] == date(2026, 7, 29)
    assert (days[-1] - days[0]).days == 8  # 9 calendar days span
    for d in days:
        assert d.weekday() < 5


def test_last_n_workdays_monday():
    # 2026-07-27 is a Monday
    days = last_n_workdays(7, today=date(2026, 7, 27))
    assert days[0] == date(2026, 7, 17)
    assert days[-1] == date(2026, 7, 27)
    assert (days[-1] - days[0]).days == 10  # 11 calendar days span


def test_last_n_workdays_saturday_excludes_today():
    # 2026-08-01 is a Saturday
    days = last_n_workdays(7, today=date(2026, 8, 1))
    assert days[-1] == date(2026, 7, 31)  # ends the preceding Friday
    assert date(2026, 8, 1) not in days
    assert days[0] == date(2026, 7, 23)


def test_last_n_workdays_sunday_matches_saturday():
    # 2026-08-02 is a Sunday — same result as the Saturday case
    days = last_n_workdays(7, today=date(2026, 8, 2))
    assert days[-1] == date(2026, 7, 31)
    assert days[0] == date(2026, 7, 23)


def test_last_n_workdays_no_weekend_days_in_result():
    days = last_n_workdays(7, today=date(2026, 7, 29))
    assert len(days) == 7
    assert all(d.weekday() < 5 for d in days)


def test_workday_window_bounds_are_half_open_utc():
    first, last, start, end = workday_window(7, today=date(2026, 7, 29))
    assert first == date(2026, 7, 21)
    assert last == date(2026, 7, 29)
    assert start.tzinfo is not None
    assert start.utcoffset() == timedelta(0)
    from datetime import datetime
    assert start == datetime(2026, 7, 21, 0, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 7, 30, 0, 0, tzinfo=timezone.utc)  # midnight of the day AFTER last


def test_workday_window_dst_crossing_still_returns_seven_dates():
    # 2026-03-08 is the US DST start (spring-forward); today a few days after.
    first, last, start, end = workday_window(7, today=date(2026, 3, 12))
    days = last_n_workdays(7, today=date(2026, 3, 12))
    assert len(days) == 7
    assert first == days[0]
    assert last == days[-1]
    assert start.tzinfo is not None and end.tzinfo is not None
