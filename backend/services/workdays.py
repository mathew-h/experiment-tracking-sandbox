from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

LAB_TZ = ZoneInfo("America/New_York")


def last_n_workdays(n: int = 7, *, today: date | None = None) -> list[date]:
    """The last `n` Mon-Fri dates, oldest first, including `today` if it is a workday.

    `today` defaults to the current date in the lab's local timezone.
    Holidays are treated as workdays (deliberately not skipped — see issue #85).
    """
    cursor = today or datetime.now(LAB_TZ).date()
    days: list[date] = []
    while len(days) < n:
        if cursor.weekday() < 5:        # Mon=0 .. Fri=4
            days.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(days))


def workday_window(n: int = 7, *, today: date | None = None) -> tuple[date, date, datetime, datetime]:
    """Return (first_date, last_date, start_utc, end_utc) for the last `n` workdays.

    The UTC bounds are half-open [start, end) at UTC midnight, because the
    date-bearing columns this filters on (`gc_run_date`, `Experiment.date`) are
    stored as midnight-UTC date values, not true instants.
    """
    days = last_n_workdays(n, today=today)
    first, last = days[0], days[-1]
    start = datetime.combine(first, datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(last + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    return first, last, start, end
