"""Persistent broadcast-state.yaml with atomic writes."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class BroadcastState:
    entries: dict[int, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "BroadcastState":
        if not path.is_file():
            return cls()
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        entries: dict[int, dict[str, Any]] = {}
        for item in doc.get("entries") or []:
            entries[int(item["order"])] = item
        return cls(entries=entries)

    def get(self, order: int) -> dict[str, Any]:
        return self.entries.get(order, {"order": order, "status": "pending", "ready_at": None})

    def is_broadcast(self, order: int) -> bool:
        return self.get(order).get("status") == "broadcast"

    def mark_broadcast(self, order: int, txid: str) -> None:
        ready_at = self.entries.get(order, {}).get("ready_at")
        self.entries[order] = {
            "order": order,
            "status": "broadcast",
            "txid": txid,
            "broadcast_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
            "ready_at": ready_at,
        }

    def mark_failed(self, order: int, error: str) -> None:
        ready_at = self.entries.get(order, {}).get("ready_at")
        self.entries[order] = {
            "order": order,
            "status": "failed",
            "txid": None,
            "broadcast_at": None,
            "error": error,
            "ready_at": ready_at,
        }

    def set_ready_at(self, order: int, ready_at: datetime) -> None:
        """Persist the jittered broadcast time drawn for `order` (runtime jitter).

        Preserves any existing status fields so a jitter draw made while an
        entry is still pending doesn't clobber later broadcast/failed bookkeeping.
        """
        entry = dict(self.get(order))
        entry["order"] = order
        entry["ready_at"] = ready_at.isoformat()
        self.entries[order] = entry

    def get_ready_at(self, order: int) -> Optional[datetime]:
        raw = self.entries.get(order, {}).get("ready_at")
        if not raw:
            return None
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def save_atomic(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        doc = {"entries": [self.entries[k] for k in sorted(self.entries)]}
        tmp.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
        os.replace(tmp, path)


def state_path(output_dir: Path) -> Path:
    return output_dir / "broadcast-state.yaml"
