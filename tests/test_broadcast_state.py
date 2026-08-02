"""Broadcast state persistence tests."""

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
