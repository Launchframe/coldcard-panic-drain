"""ICS export tests."""

from datetime import datetime, timezone
from pathlib import Path

from coldcard_panic_drain.schedule.ics_export import count_vevents, write_ics_calendar


def test_write_ics_calendar(tmp_path: Path):
    entries = [
        {
            "order": 1,
            "label": "Test Coin",
            "signed": "psbts_signed/001-test-signed.psbt",
            "broadcast_not_before": datetime(2026, 8, 2, 14, 0, tzinfo=timezone.utc).isoformat(),
        }
    ]
    out = tmp_path / "reminders.ics"
    write_ics_calendar(out, entries, batch_name="batch", alarm_minutes=15)
    text = out.read_text(encoding="utf-8")
    assert count_vevents(text) == 1
    assert "BEGIN:VALARM" in text
    assert "Broadcast: Test Coin" in text
