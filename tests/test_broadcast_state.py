"""Broadcast state persistence tests."""

from datetime import datetime, timezone
from pathlib import Path

from coldcard_panic_drain.broadcast.state import BroadcastState, state_path


def test_atomic_save_and_load(tmp_path: Path):
    path = state_path(tmp_path)
    state = BroadcastState()
    state.mark_broadcast(1, "abc" * 16)
    state.save_atomic(path)
    loaded = BroadcastState.load(path)
    assert loaded.is_broadcast(1)
    assert loaded.get(1)["txid"] == "abc" * 16


def test_clear_ready_at_removes_persisted_draw_without_clobbering_status(tmp_path: Path):
    state = BroadcastState()
    state.mark_failed(1, "mempool full")
    state.set_ready_at(1, datetime(2020, 1, 1, tzinfo=timezone.utc))

    state.clear_ready_at(1)

    assert state.get_ready_at(1) is None
    assert state.get(1)["status"] == "failed"
    assert state.get(1)["error"] == "mempool full"


def test_clear_ready_at_is_a_noop_for_unknown_order():
    state = BroadcastState()
    state.clear_ready_at(99)
    assert state.get_ready_at(99) is None
    assert 99 not in state.entries


def test_clear_all_ready_at(tmp_path: Path):
    state = BroadcastState()
    state.set_ready_at(1, datetime(2020, 1, 1, tzinfo=timezone.utc))
    state.set_ready_at(2, datetime(2020, 1, 1, tzinfo=timezone.utc))
    state.mark_broadcast(2, "aa" * 32)

    state.clear_all_ready_at()

    assert state.get_ready_at(1) is None
    assert state.get_ready_at(2) is None
    assert state.is_broadcast(2)
