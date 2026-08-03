"""Reschedule command tests — synthetic labels/timestamps only (see AGENTS.md)."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from coldcard_panic_drain.broadcast.state import BroadcastState, state_path
from coldcard_panic_drain.schedule.reschedule import reschedule_schedule
from coldcard_panic_drain.schedule.timing import MIN_ENTRY_GAP

_BASE = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _write_schedule(
    tmp_path: Path, n: int, *, spread_hours: float = 6.0, schedule_jitter: float = 0.35
) -> None:
    doc = {
        "generated_at": _BASE.isoformat(),
        "spread_hours": spread_hours,
        "schedule_jitter": schedule_jitter,
        "entries": [
            {
                "order": i + 1,
                "label": f"coin-{i}",
                "unsigned": f"psbts/{i}.psbt",
                "signed": f"psbts_signed/{i}-signed.psbt",
                "broadcast_not_before": (_BASE + timedelta(hours=i)).isoformat(),
                "fee_sat_vb": 10,
                "nlocktime": 890_000,
                "utxo_ref": f"ref-{i}",
            }
            for i in range(n)
        ],
    }
    (tmp_path / "schedule.yaml").write_text(
        yaml.safe_dump(doc, sort_keys=False), encoding="utf-8"
    )


def _load_schedule(tmp_path: Path) -> dict:
    return yaml.safe_load((tmp_path / "schedule.yaml").read_text(encoding="utf-8"))


def test_reschedule_leaves_broadcast_entries_untouched(tmp_path: Path):
    _write_schedule(tmp_path, 4)
    state = BroadcastState()
    state.mark_broadcast(1, "aa" * 32)
    state.save_atomic(state_path(tmp_path))
    orig_time_1 = _load_schedule(tmp_path)["entries"][0]["broadcast_not_before"]

    result = reschedule_schedule(tmp_path, spread_hours=2.0, rng=random.Random(1))

    assert result.skipped_broadcast_count == 1
    assert result.rescheduled_count == 3
    assert 1 not in result.pending_orders
    assert sorted(result.pending_orders) == [2, 3, 4]

    doc = _load_schedule(tmp_path)
    entry_1 = next(e for e in doc["entries"] if e["order"] == 1)
    assert entry_1["broadcast_not_before"] == orig_time_1
    for order in (2, 3, 4):
        entry = next(e for e in doc["entries"] if e["order"] == order)
        assert entry["broadcast_not_before"] != (_BASE + timedelta(hours=order - 1)).isoformat()


def test_reschedule_clears_ready_at_on_rescheduled_orders(tmp_path: Path):
    _write_schedule(tmp_path, 2)
    state = BroadcastState()
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    state.set_ready_at(1, future)
    state.set_ready_at(2, future)
    state.save_atomic(state_path(tmp_path))

    reschedule_schedule(tmp_path, spread_hours=2.0, rng=random.Random(2))

    reloaded = BroadcastState.load(state_path(tmp_path))
    assert reloaded.get_ready_at(1) is None
    assert reloaded.get_ready_at(2) is None


def test_reschedule_does_not_disturb_broadcast_entry_ready_at(tmp_path: Path):
    """Already-broadcast entries are skipped entirely, including their ready_at."""
    _write_schedule(tmp_path, 2)
    state = BroadcastState()
    ready = datetime.now(timezone.utc) - timedelta(minutes=5)
    state.set_ready_at(1, ready)
    state.mark_broadcast(1, "aa" * 32)
    state.save_atomic(state_path(tmp_path))

    reschedule_schedule(tmp_path, spread_hours=2.0, rng=random.Random(3))

    reloaded = BroadcastState.load(state_path(tmp_path))
    assert reloaded.get_ready_at(1) == ready


def test_reschedule_reschedules_failed_entries_too(tmp_path: Path):
    _write_schedule(tmp_path, 2)
    state = BroadcastState()
    state.mark_failed(2, "mempool full")
    state.save_atomic(state_path(tmp_path))

    result = reschedule_schedule(tmp_path, spread_hours=2.0, rng=random.Random(4))

    assert 2 in result.pending_orders
    assert result.skipped_broadcast_count == 0
    # Failure status itself is untouched — reschedule only retimes, doesn't clear failures.
    reloaded = BroadcastState.load(state_path(tmp_path))
    assert reloaded.get(2)["status"] == "failed"


def test_reschedule_new_times_monotonic_with_min_gap(tmp_path: Path):
    _write_schedule(tmp_path, 8, spread_hours=1.0, schedule_jitter=1.0)
    for seed in range(25):
        result = reschedule_schedule(
            tmp_path,
            spread_hours=1.0,
            schedule_jitter=1.0,
            dry_run=True,
            rng=random.Random(seed),
        )
        times = [result.new_times[o] for o in result.pending_orders]
        for prev, cur in zip(times, times[1:]):
            assert cur - prev >= MIN_ENTRY_GAP, (seed, prev, cur)


def test_dry_run_does_not_write_any_files(tmp_path: Path):
    _write_schedule(tmp_path, 3)
    orig_bytes = (tmp_path / "schedule.yaml").read_bytes()

    result = reschedule_schedule(tmp_path, spread_hours=2.0, dry_run=True, rng=random.Random(5))

    assert result.rescheduled_count == 3
    assert (tmp_path / "schedule.yaml").read_bytes() == orig_bytes
    assert not (tmp_path / "broadcast-state.yaml").exists()


def test_dry_run_does_not_clear_ready_at(tmp_path: Path):
    _write_schedule(tmp_path, 2)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    state = BroadcastState()
    state.set_ready_at(1, future)
    state.save_atomic(state_path(tmp_path))

    reschedule_schedule(tmp_path, spread_hours=2.0, dry_run=True, rng=random.Random(6))

    reloaded = BroadcastState.load(state_path(tmp_path))
    assert reloaded.get_ready_at(1) == future


def test_shuffle_pending_changes_assignment_order_among_pending(tmp_path: Path):
    _write_schedule(tmp_path, 6, spread_hours=6.0, schedule_jitter=0.0)

    result = reschedule_schedule(
        tmp_path,
        spread_hours=6.0,
        schedule_jitter=0.0,
        shuffle_pending=True,
        dry_run=True,
        rng=random.Random(0),
    )

    # Same set of order numbers, but not assigned to time slots in original order.
    assert sorted(result.pending_orders) == [1, 2, 3, 4, 5, 6]
    assert result.pending_orders != [1, 2, 3, 4, 5, 6]


def test_shuffle_pending_off_keeps_original_order_for_zero_jitter(tmp_path: Path):
    _write_schedule(tmp_path, 6, spread_hours=6.0, schedule_jitter=0.0)

    result = reschedule_schedule(
        tmp_path,
        spread_hours=6.0,
        schedule_jitter=0.0,
        shuffle_pending=False,
        dry_run=True,
        rng=random.Random(0),
    )

    assert result.pending_orders == [1, 2, 3, 4, 5, 6]


def test_reschedule_updates_schedule_doc_metadata(tmp_path: Path):
    _write_schedule(tmp_path, 2, spread_hours=6.0, schedule_jitter=0.35)

    reschedule_schedule(
        tmp_path, spread_hours=9.0, schedule_jitter=0.1, rng=random.Random(8)
    )

    doc = _load_schedule(tmp_path)
    assert doc["spread_hours"] == 9.0
    assert doc["schedule_jitter"] == 0.1
    assert "rescheduled_at" in doc


def test_reschedule_defaults_jitter_from_existing_schedule_doc(tmp_path: Path):
    _write_schedule(tmp_path, 2, spread_hours=6.0, schedule_jitter=0.42)

    reschedule_schedule(tmp_path, spread_hours=6.0, rng=random.Random(9))

    doc = _load_schedule(tmp_path)
    assert doc["schedule_jitter"] == 0.42


def test_reschedule_with_no_pending_entries_is_a_noop_write(tmp_path: Path):
    _write_schedule(tmp_path, 1)
    state = BroadcastState()
    state.mark_broadcast(1, "aa" * 32)
    state.save_atomic(state_path(tmp_path))

    result = reschedule_schedule(tmp_path, spread_hours=2.0, rng=random.Random(10))

    assert result.rescheduled_count == 0
    assert result.skipped_broadcast_count == 1
