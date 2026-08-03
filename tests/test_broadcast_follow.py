"""--follow mode: next-wake computation and graceful shutdown tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from coldcard_panic_drain.broadcast.follow import (
    DEFAULT_POLL_INTERVAL,
    MAX_SLEEP_CHUNK_SECONDS,
    ShutdownFlag,
    compute_next_broadcast_wake,
    run_broadcast_follow,
)
from coldcard_panic_drain.broadcast.state import BroadcastState, state_path


def _write_schedule(tmp_path: Path, entries: list[dict]) -> None:
    (tmp_path / "schedule.yaml").write_text(
        yaml.safe_dump({"entries": entries}), encoding="utf-8"
    )


def _entry(order: int, not_before: datetime, label: str = "coin") -> dict:
    return {
        "order": order,
        "label": label,
        "signed": f"psbts_signed/{label}-signed.psbt",
        "broadcast_not_before": not_before.isoformat(),
    }


def test_compute_next_wake_falls_back_to_poll_interval_without_schedule(tmp_path: Path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert compute_next_broadcast_wake(tmp_path, now) == now + DEFAULT_POLL_INTERVAL


def test_compute_next_wake_uses_not_before_when_in_future(tmp_path: Path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    not_before = now + timedelta(hours=3)
    _write_schedule(tmp_path, [_entry(1, not_before)])
    assert compute_next_broadcast_wake(tmp_path, now) == not_before


def test_compute_next_wake_prefers_later_persisted_ready_at(tmp_path: Path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    not_before = now + timedelta(hours=1)
    ready_at = now + timedelta(hours=2)
    _write_schedule(tmp_path, [_entry(1, not_before)])
    state = BroadcastState()
    state.set_ready_at(1, ready_at)
    state.save_atomic(state_path(tmp_path))

    assert compute_next_broadcast_wake(tmp_path, now) == ready_at


def test_compute_next_wake_ignores_ready_at_earlier_than_not_before(tmp_path: Path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    not_before = now + timedelta(hours=2)
    ready_at = now + timedelta(hours=1)  # stale/earlier draw; not_before wins
    _write_schedule(tmp_path, [_entry(1, not_before)])
    state = BroadcastState()
    state.set_ready_at(1, ready_at)
    state.save_atomic(state_path(tmp_path))

    assert compute_next_broadcast_wake(tmp_path, now) == not_before


def test_compute_next_wake_falls_back_when_due_but_blocked(tmp_path: Path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Already due (e.g. blocked on missing signature, quiet hours, or a jitter
    # draw not yet made) — must not return a past/now timestamp.
    _write_schedule(tmp_path, [_entry(1, now - timedelta(minutes=5))])
    assert compute_next_broadcast_wake(tmp_path, now) == now + DEFAULT_POLL_INTERVAL


def test_compute_next_wake_ignores_already_broadcast_entries(tmp_path: Path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    not_before = now + timedelta(hours=1)
    _write_schedule(tmp_path, [_entry(1, not_before)])
    state = BroadcastState()
    state.mark_broadcast(1, "aa" * 32)
    state.save_atomic(state_path(tmp_path))

    assert compute_next_broadcast_wake(tmp_path, now) == now + DEFAULT_POLL_INTERVAL


def test_compute_next_wake_picks_earliest_of_multiple_pending_entries(tmp_path: Path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    soon = now + timedelta(minutes=30)
    later = now + timedelta(hours=5)
    _write_schedule(tmp_path, [_entry(1, later, "b"), _entry(2, soon, "a")])
    assert compute_next_broadcast_wake(tmp_path, now) == soon


def test_run_broadcast_follow_stops_on_shutdown_flag(tmp_path: Path, monkeypatch):
    calls = {"run": 0, "sleep": 0}

    def fake_run_broadcast_due(output_dir, rpc, **kwargs):
        calls["run"] += 1
        return []

    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.follow.run_broadcast_due", fake_run_broadcast_due
    )
    flag = ShutdownFlag()

    def fake_sleep(seconds: float) -> None:
        calls["sleep"] += 1
        flag.requested = True

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run_broadcast_follow(
        tmp_path,
        MagicMock(),
        shutdown_flag=flag,
        now_fn=lambda: now,
        sleep_fn=fake_sleep,
    )
    assert calls["run"] == 1
    assert calls["sleep"] == 1


def test_run_broadcast_follow_skips_run_broadcast_due_if_already_shutdown(
    tmp_path: Path, monkeypatch
):
    called = {"run": False}

    def fake_run_broadcast_due(*args, **kwargs):
        called["run"] = True
        return []

    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.follow.run_broadcast_due", fake_run_broadcast_due
    )
    flag = ShutdownFlag()
    flag.requested = True

    run_broadcast_follow(tmp_path, MagicMock(), shutdown_flag=flag)

    assert called["run"] is False


def test_run_broadcast_follow_sleeps_in_chunks_of_at_most_60s(tmp_path: Path, monkeypatch):
    clock = {"now": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    not_before = clock["now"] + timedelta(seconds=150)
    _write_schedule(tmp_path, [_entry(1, not_before)])

    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.follow.run_broadcast_due",
        lambda output_dir, rpc, **kwargs: [],
    )

    flag = ShutdownFlag()
    sleep_calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        clock["now"] += timedelta(seconds=seconds)
        if len(sleep_calls) >= 5:
            flag.requested = True

    run_broadcast_follow(
        tmp_path,
        MagicMock(),
        shutdown_flag=flag,
        now_fn=lambda: clock["now"],
        sleep_fn=fake_sleep,
    )

    assert sleep_calls, "expected at least one sleep chunk before shutdown"
    assert all(s <= MAX_SLEEP_CHUNK_SECONDS for s in sleep_calls)
    # The 150s wake cannot be reached in a single <=60s chunk.
    assert len(sleep_calls) >= 2


def test_run_broadcast_follow_forwards_results_to_on_results(tmp_path: Path, monkeypatch):
    seen: list[list] = []
    monkeypatch.setattr(
        "coldcard_panic_drain.broadcast.follow.run_broadcast_due",
        lambda output_dir, rpc, **kwargs: ["fake-result"],
    )
    flag = ShutdownFlag()

    def fake_sleep(_seconds: float) -> None:
        flag.requested = True

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run_broadcast_follow(
        tmp_path,
        MagicMock(),
        shutdown_flag=flag,
        now_fn=lambda: now,
        sleep_fn=fake_sleep,
        on_results=seen.append,
    )
    assert seen == [["fake-result"]]
