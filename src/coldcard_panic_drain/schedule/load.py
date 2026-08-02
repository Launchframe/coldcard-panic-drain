"""Load schedule.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from coldcard_panic_drain.schedule.quiet_hours import quiet_hours_from_dict


def load_schedule(path: Path) -> dict[str, Any]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"Invalid schedule file: {path}")
    return doc


def schedule_quiet_hours(doc: dict[str, Any]):
    return quiet_hours_from_dict(doc.get("quiet_hours"))
