"""Schedule YAML jitter, monotonic spacing, and quiet-hours re-application tests."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from coldcard_panic_drain.schedule.quiet_hours import QuietHours, in_quiet_hours
from coldcard_panic_drain.schedule.yaml_manifest import MIN_ENTRY_GAP, write_schedule
from coldcard_panic_drain.sparrow.models import DestinationAssignment, UtxoRecord

# Synthetic-only fixture data (no real wallet material) — see AGENTS.md.
_SYNTHETIC_UTXO_ADDR = "bc1qtestfixtureutxoaddress0000000000000q"
_SYNTHETIC_DEST_ADDR = "bc1qtestfixturedestaddress0000000000000q"


def _assignment(value_sats: int, i: int) -> DestinationAssignment:
    utxo = UtxoRecord(
        txid=f"{i:02x}" * 32,
        vout=0,
        value_sats=value_sats,
        height=890_000,
        received_at=None,
        address=_SYNTHETIC_UTXO_ADDR,
        derivation_path="m/84'/0'/0'/0/0",
        label=f"coin-{i}",
    )
    return DestinationAssignment(
        utxo=utxo,
        receive_index=i,
        address=_SYNTHETIC_DEST_ADDR,
        fee_sat_vb=10,
        fee_sats=1400,
        nlocktime=890_002,
        psbt_filename=f"{i}.psbt",
    )


def _write(tmp_path: Path, n: int, **kwargs) -> list[dict]:
    assignments = [_assignment(100_000 + i, i) for i in range(n)]
    return write_schedule(tmp_path / "schedule.yaml", assignments, **kwargs)


def _times(entries: list[dict]) -> list[datetime]:
    return [datetime.fromisoformat(e["broadcast_not_before"]) for e in entries]


def test_entries_stay_monotonic_and_min_gap_apart_across_seeds(tmp_path: Path):
    # Tight spread + large jitter is the scenario most likely to push an entry
    # earlier than its predecessor if the min-gap floor were missing.
    for seed in range(25):
        seed_dir = tmp_path / f"seed-{seed}"
        seed_dir.mkdir()
        entries = _write(
            seed_dir,
            8,
            spread_hours=1.0,
            schedule_jitter=1.0,
            rng=random.Random(seed),
        )
        times = _times(entries)
        for prev, cur in zip(times, times[1:]):
            assert cur - prev >= MIN_ENTRY_GAP, (seed, prev, cur)


def test_zero_jitter_matches_unjittered_step(tmp_path: Path):
    entries = _write(tmp_path, 4, spread_hours=4.0, schedule_jitter=0.0, rng=random.Random(2))
    times = _times(entries)
    step = timedelta(hours=1.0)
    for i in range(1, len(times)):
        assert abs((times[i] - times[0]) - step * i) < timedelta(seconds=1)


def test_jitter_moves_entries_off_the_exact_fixed_cadence(tmp_path: Path):
    entries = _write(tmp_path, 6, spread_hours=6.0, schedule_jitter=0.35, rng=random.Random(4))
    times = _times(entries)
    step = timedelta(hours=1.0)
    offsets = [times[i] - (times[0] + step * i) for i in range(len(times))]
    assert any(abs(o) > timedelta(seconds=1) for o in offsets)


def test_schedule_jitter_persisted_in_doc(tmp_path: Path):
    _write(tmp_path, 2, spread_hours=2.0, schedule_jitter=0.42, rng=random.Random(3))
    doc = yaml.safe_load((tmp_path / "schedule.yaml").read_text(encoding="utf-8"))
    assert doc["schedule_jitter"] == 0.42


def test_quiet_hours_reapplied_after_jitter(tmp_path: Path):
    qh = QuietHours(start="22:00", end="08:00", timezone="UTC")
    for seed in range(10):
        seed_dir = tmp_path / f"seed-{seed}"
        seed_dir.mkdir()
        entries = _write(
            seed_dir,
            5,
            spread_hours=5.0,
            schedule_jitter=0.35,
            quiet_hours=qh,
            rng=random.Random(seed),
        )
        for e in entries:
            t = datetime.fromisoformat(e["broadcast_not_before"])
            assert not in_quiet_hours(t, qh), (seed, t)


def test_empty_assignments_write_empty_entries(tmp_path: Path):
    entries = write_schedule(
        tmp_path / "schedule.yaml", [], spread_hours=6.0, schedule_jitter=0.35
    )
    assert entries == []
