from datetime import date

import pytest

from meridian_service.periods import InvalidPeriod, iso_week_of, parse_period

ANCHOR = date(2026, 9, 28)  # data window end-exclusive


def test_last_7_days_anchored_to_window_end():
    r = parse_period("last_7_days", ANCHOR)
    assert (r.start, r.end_exclusive) == (date(2026, 9, 21), date(2026, 9, 28))


def test_last_30_days():
    r = parse_period("last_30_days", ANCHOR)
    assert (r.start, r.end_exclusive) == (date(2026, 8, 29), date(2026, 9, 28))


def test_iso_week():
    r = parse_period("2026-W36", ANCHOR)
    assert r.start == date(2026, 8, 31)  # Monday of W36
    assert r.end_exclusive == date(2026, 9, 7)


def test_month_rolls_over_year_on_december():
    r = parse_period("2026-12", ANCHOR)
    assert (r.start, r.end_exclusive) == (date(2026, 12, 1), date(2027, 1, 1))


def test_contains_is_half_open():
    r = parse_period("2026-09", ANCHOR)
    assert r.contains(date(2026, 9, 1))
    assert r.contains(date(2026, 9, 30))
    assert not r.contains(date(2026, 10, 1))


@pytest.mark.parametrize("bad", ["", "2026-13", "2026-W99", "yesterday", "2026/09"])
def test_invalid_periods_rejected(bad):
    with pytest.raises(InvalidPeriod):
        parse_period(bad, ANCHOR)


def test_iso_week_of_roundtrips():
    assert iso_week_of(date(2026, 8, 31)) == "2026-W36"
