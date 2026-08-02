"""Quiet hours scheduling tests."""

from datetime import datetime, timezone

from coldcard_panic_drain.schedule.quiet_hours import (
    QuietHours,
    in_quiet_hours,
    next_allowed_time,
    parse_quiet_hours,
)


def test_overnight_quiet_hours():
    qh = QuietHours(start="22:00", end="08:00", timezone="UTC")
    # 23:00 UTC is quiet
    late = datetime(2026, 8, 2, 23, 0, tzinfo=timezone.utc)
    assert in_quiet_hours(late, qh)
    bumped = next_allowed_time(late, qh)
    assert bumped.hour == 8
    assert bumped.day == 3


def test_daytime_not_quiet():
    qh = QuietHours(start="22:00", end="08:00", timezone="UTC")
    noon = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
    assert not in_quiet_hours(noon, qh)
    assert next_allowed_time(noon, qh) == noon


def test_parse_requires_all_fields():
    assert parse_quiet_hours(None, None, None) is None
    try:
        parse_quiet_hours("22:00", None, None)
        assert False, "expected ValueError"
    except ValueError:
        pass
