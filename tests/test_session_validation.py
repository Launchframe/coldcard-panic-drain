"""Session wallet-swap detection and assignment loading."""

import json
from pathlib import Path

import pytest

from coldcard_panic_drain.plan.mapper import build_assignments, derive_receive_address
from coldcard_panic_drain.plan.session import DrainSession, session_path
from coldcard_panic_drain.sparrow.models import UtxoRecord

from conftest import TEST_FP, TEST_XPUB, make_test_wallet, make_test_wallet_b


def _sample_utxo(wallet) -> UtxoRecord:
    return UtxoRecord(
        txid="cd" * 32,
        vout=0,
        value_sats=2_000_000,
        height=890_000,
        received_at=None,
        address=derive_receive_address(wallet, 0),
        derivation_path="m/84'/0'/0'/0/0",
        label="Coin A",
        included=True,
    )


def test_verify_dest_wallet_rejects_xpub_swap():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    dest = make_test_wallet(path="/tmp/b.mv.db", name="b")
    utxo = _sample_utxo(source)
    source.utxos = [utxo]
    assignments = build_assignments(
        [utxo],
        dest,
        fee_base=25,
        fee_jitter=0,
        chain_tip=900_000,
        min_blocks_apart=2,
    )
    session = DrainSession.from_wallets(source, dest, 25, 0.0, 2, 48.0)
    session.set_assignments(assignments)

    swapped = make_test_wallet_b(path="/tmp/b.mv.db", name="b")
    with pytest.raises(ValueError, match="xpub changed"):
        session.verify_dest_wallet(swapped)


def test_verify_dest_wallet_rejects_fingerprint_swap():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    dest = make_test_wallet(path="/tmp/b.mv.db", name="b")
    session = DrainSession.from_wallets(source, dest, 25, 0.0, 2, 48.0)
    session.dest_fingerprint = "deadbeef"
    with pytest.raises(ValueError, match="fingerprint changed"):
        session.verify_dest_wallet(dest)


def test_verify_dest_wallet_requires_snapshot():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    dest = make_test_wallet(path="/tmp/b.mv.db", name="b")
    session = DrainSession(
        source_path=source.path,
        dest_path=dest.path,
        chain_tip_height=900_000,
        fee_base=25,
        fee_jitter=0.0,
        min_blocks_apart=2,
        spread_hours=48.0,
    )
    with pytest.raises(ValueError, match="missing destination wallet snapshot"):
        session.verify_dest_wallet(dest)


def test_assignment_objects_round_trip():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    dest = make_test_wallet(path="/tmp/b.mv.db", name="b")
    utxo = _sample_utxo(source)
    source.utxos = [utxo]
    assignments = build_assignments(
        [utxo],
        dest,
        fee_base=25,
        fee_jitter=0,
        chain_tip=900_000,
        min_blocks_apart=2,
    )
    session = DrainSession.from_wallets(source, dest, 25, 0.0, 2, 48.0)
    session.set_assignments(assignments)

    loaded = session.assignment_objects([utxo])
    assert len(loaded) == 1
    assert loaded[0].address == assignments[0].address
    assert loaded[0].fee_sat_vb == assignments[0].fee_sat_vb
    assert loaded[0].receive_index == assignments[0].receive_index


def test_assignment_objects_rejects_unknown_utxo():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    dest = make_test_wallet(path="/tmp/b.mv.db", name="b")
    utxo = _sample_utxo(source)
    assignments = build_assignments(
        [utxo],
        dest,
        fee_base=25,
        fee_jitter=0,
        chain_tip=900_000,
        min_blocks_apart=2,
    )
    session = DrainSession.from_wallets(source, dest, 25, 0.0, 2, 48.0)
    session.set_assignments(assignments)
    with pytest.raises(ValueError, match="unknown UTXO"):
        session.assignment_objects([])


def test_assignment_objects_requires_assignments():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    dest = make_test_wallet(path="/tmp/b.mv.db", name="b")
    session = DrainSession.from_wallets(source, dest, 25, 0.0, 2, 48.0)
    with pytest.raises(ValueError, match="no assignments"):
        session.assignment_objects([])


def test_session_save_includes_dest_snapshot(tmp_path: Path):
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    dest = make_test_wallet(path="/tmp/b.mv.db", name="b")
    session = DrainSession.from_wallets(source, dest, 25, 0.0, 2, 48.0)
    out = session_path(tmp_path)
    session.save(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["dest_xpub"] == TEST_XPUB
    assert data["dest_fingerprint"] == TEST_FP
