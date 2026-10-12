"""Period parsing.

The tool contract accepts four period shapes:

    last_7_days | last_30_days | ISO week (2026-W36) | month (2026-09)

Every period resolves to a half-open ``[start, end_exclusive)`` range of dates.
Relative periods ("last N days") are anchored to the end of the data window
(``2026-09-28`` exclusive) rather than wall-clock "today", so results are
deterministic and the newest day of data is always included.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

_WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")
_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


class InvalidPeriod(ValueError):
    """Raised when a period string does not match the contract grammar."""


@dataclass(frozen=True)
class DateRange:
    start: date           # inclusive
    end_exclusive: date   # exclusive

    def contains(self, day: date) -> bool:
        return self.start <= day < self.end_exclusive


def parse_period(period: str, anchor_end_exclusive: date) -> DateRange:
    period = period.strip()

    if period == "last_7_days":
        return DateRange(anchor_end_exclusive - timedelta(days=7), anchor_end_exclusive)
    if period == "last_30_days":
        return DateRange(anchor_end_exclusive - timedelta(days=30), anchor_end_exclusive)

    m = _WEEK_RE.match(period)
    if m:
        year, week = int(m.group(1)), int(m.group(2))
        if not 1 <= week <= 53:
            raise InvalidPeriod(f"ISO week out of range: {period!r}")
        try:
            start = date.fromisocalendar(year, week, 1)  # Monday
        except ValueError as exc:  # e.g. W53 in a 52-week year
            raise InvalidPeriod(f"No such ISO week: {period!r}") from exc
        return DateRange(start, start + timedelta(days=7))

    m = _MONTH_RE.match(period)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if not 1 <= month <= 12:
            raise InvalidPeriod(f"Month out of range: {period!r}")
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        return DateRange(start, end)

    raise InvalidPeriod(
        f"Unrecognised period {period!r}; expected last_7_days, last_30_days, "
        "an ISO week like 2026-W36, or a month like 2026-09."
    )


def iso_week_of(day: date) -> str:
    """Render the ISO week label (``2026-W36``) a given day falls in."""
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"
