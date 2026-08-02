"""Remind logic tests."""

from datetime import datetime, timezone
from pathlib import Path

import yaml

from coldcard_panic_drain.schedule.remind_logic import compute_remind_status


def test_remind_ignores_escaping_signed_path(tmp_path: Path):
    doc = {
        "entries": [
            {
                "order": 1,
                "label": "coin",
                "signed": "../../../etc/passwd",
                "broadcast_not_before": datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat(),
            }
        ]
    }
    (tmp_path / "schedule.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    status = compute_remind_status(tmp_path, now=datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert "Waiting for signature" in status.message
