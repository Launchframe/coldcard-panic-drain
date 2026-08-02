"""Source-side (Wallet A) fund-safety checks — Real Steel pass 2 (Sonnet).

Covers three gaps left open by the prior pass, which only snapshotted/validated
the destination wallet:

1. Address derivation must vary with index (regression for a critical bug where
   every UTXO collapsed onto the same address regardless of receive/change index).
2. Source wallet-swap detection (`verify_source_wallet`), mirroring the existing
   destination-side check.
3. Cross-checking session-cached UTXOs against a freshly loaded Wallet A snapshot
   (`validate_source_utxos` / `validate_source_utxo`) — catches spent, tampered,
   or forged UTXO entries in `labels-session.json`.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from embit.psbt import PSBT

from coldcard_panic_drain.plan.mapper import (
    build_assignments,
    derive_address_at_path,
    derive_receive_address,
    validate_source_utxo,
    validate_source_utxos,
)
from coldcard_panic_drain.plan.session import DrainSession, session_path
from coldcard_panic_drain.psbt.builder import build_psbt, write_psbt_bundle
from coldcard_panic_drain.sparrow.models import UtxoRecord
from coldcard_panic_drain.util import derive_address_for_chain_index, parse_bip32_path

from conftest import TEST_FP, TEST_XPUB, make_test_wallet, make_test_wallet_b


def _utxo(wallet, *, index=0, chain=0, label="Coin", txid="cd" * 32, vout=0, value=2_000_000):
    path = f"m/84'/0'/0'/{chain}/{index}"
    return UtxoRecord(
        txid=txid,
        vout=vout,
        value_sats=value,
        height=890_000,
        received_at=None,
        address=derive_address_for_chain_index(wallet.keystore, chain, index),
        derivation_path=path,
        label=label,
        included=True,
    )


# --- Regression: address must vary with index (critical bug fix) ------------


def test_derive_receive_address_varies_with_index():
    w = make_test_wallet()
    addrs = {derive_receive_address(w, i) for i in (0, 1, 5, 100)}
    assert len(addrs) == 4, "every index collapsed onto the same address"


def test_derive_address_for_chain_index_distinguishes_chains():
    w = make_test_wallet()
    external = derive_address_for_chain_index(w.keystore, 0, 3)
    internal = derive_address_for_chain_index(w.keystore, 1, 3)
    assert external != internal


def test_derive_address_at_path_matches_chain_index_helper():
    w = make_test_wallet()
    for chain, idx in [(0, 0), (0, 7), (1, 2)]:
        expected = derive_address_for_chain_index(w.keystore, chain, idx)
        got = derive_address_at_path(w, f"m/84'/0'/0'/{chain}/{idx}")
        assert got == expected


def test_parse_bip32_path_hardened_and_plain():
    assert parse_bip32_path("m/84'/0'/0'/0/5") == [
        84 + 0x80000000,
        0 + 0x80000000,
        0 + 0x80000000,
        0,
        5,
    ]


# --- validate_source_utxo / validate_source_utxos ----------------------------


def test_validate_source_utxo_accepts_correctly_derived():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    utxo = _utxo(source, index=4)
    validate_source_utxo(source, utxo)  # should not raise


def test_validate_source_utxo_rejects_tampered_address():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    utxo = _utxo(source, index=4)
    utxo.address = utxo.address[:-4] + "xxxx"
    with pytest.raises(ValueError, match="does not derive from Wallet A xpub"):
        validate_source_utxo(source, utxo)


def test_validate_source_utxos_accepts_clean_batch():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    utxo = _utxo(source, index=1)
    source.utxos = [utxo]
    assert validate_source_utxos(source, [utxo]) == []


def test_validate_source_utxos_detects_already_spent():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    cached = _utxo(source, index=1, txid="aa" * 32)
    # Fresh wallet no longer has this outpoint (spent since plan).
    source.utxos = []
    errors = validate_source_utxos(source, [cached])
    assert any("not found in current Wallet A unspent set" in e for e in errors)


def test_validate_source_utxos_detects_value_tamper():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    cached = _utxo(source, index=1, txid="bb" * 32, value=1_000_000)
    fresh = _utxo(source, index=1, txid="bb" * 32, value=9_000_000)
    source.utxos = [fresh]
    errors = validate_source_utxos(source, [cached])
    assert any("value changed since plan" in e for e in errors)


def test_validate_source_utxos_detects_forged_address():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    cached = _utxo(source, index=1, txid="cc" * 32)
    forged_address = cached.address[:-4] + "xxxx"
    cached.address = forged_address
    fresh = _utxo(source, index=1, txid="cc" * 32)
    fresh.address = forged_address  # matches session but not Wallet A's own xpub
    source.utxos = [fresh]
    errors = validate_source_utxos(source, [cached])
    assert any("does not derive from Wallet A xpub" in e for e in errors)


def test_validate_source_utxos_skips_excluded_utxos():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    frozen = _utxo(source, index=2, txid="dd" * 32)
    frozen.frozen = True
    source.utxos = []  # not present in fresh set at all
    assert validate_source_utxos(source, [frozen]) == []


# --- DrainSession.verify_source_wallet ---------------------------------------


def test_verify_source_wallet_rejects_xpub_swap():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    dest = make_test_wallet_b(path="/tmp/b.mv.db", name="b")
    session = DrainSession.from_wallets(source, dest, 25, 0.0, 2, 48.0)

    swapped = make_test_wallet_b(path="/tmp/a.mv.db", name="a")
    with pytest.raises(ValueError, match="xpub changed"):
        session.verify_source_wallet(swapped)


def test_verify_source_wallet_rejects_fingerprint_swap():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    dest = make_test_wallet_b(path="/tmp/b.mv.db", name="b")
    session = DrainSession.from_wallets(source, dest, 25, 0.0, 2, 48.0)
    session.source_fingerprint = "deadbeef"
    with pytest.raises(ValueError, match="fingerprint changed"):
        session.verify_source_wallet(source)


def test_verify_source_wallet_requires_snapshot():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    dest = make_test_wallet_b(path="/tmp/b.mv.db", name="b")
    session = DrainSession(
        source_path=source.path,
        dest_path=dest.path,
        chain_tip_height=900_000,
        fee_base=25,
        fee_jitter=0.0,
        min_blocks_apart=2,
        spread_hours=48.0,
    )
    with pytest.raises(ValueError, match="missing source wallet snapshot"):
        session.verify_source_wallet(source)


def test_verify_source_wallet_accepts_matching_snapshot():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    dest = make_test_wallet_b(path="/tmp/b.mv.db", name="b")
    session = DrainSession.from_wallets(source, dest, 25, 0.0, 2, 48.0)
    session.verify_source_wallet(source)  # should not raise


def test_session_save_includes_source_snapshot(tmp_path: Path):
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    dest = make_test_wallet_b(path="/tmp/b.mv.db", name="b")
    session = DrainSession.from_wallets(source, dest, 25, 0.0, 2, 48.0)
    out = session_path(tmp_path)
    session.save(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["source_xpub"] == TEST_XPUB
    assert data["source_fingerprint"] == TEST_FP


def test_legacy_session_without_source_snapshot_loads_and_fails_closed(tmp_path: Path):
    """Sessions saved before this pass lack source_xpub/fingerprint — must fail closed."""
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    dest = make_test_wallet_b(path="/tmp/b.mv.db", name="b")
    session = DrainSession.from_wallets(source, dest, 25, 0.0, 2, 48.0)
    data = asdict(session)
    del data["source_xpub"]
    del data["source_fingerprint"]
    out = session_path(tmp_path)
    out.write_text(json.dumps(data), encoding="utf-8")

    loaded = DrainSession.load(out)
    assert loaded.source_xpub == ""
    with pytest.raises(ValueError, match="missing source wallet snapshot"):
        loaded.verify_source_wallet(source)


# --- PSBT: bip32_derivation + defense-in-depth source check ------------------


def _bundle_fixture():
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    dest = make_test_wallet_b(path="/tmp/b.mv.db", name="b")
    utxo = _utxo(source, index=6, chain=1, txid="ee" * 32)  # exercise a change-chain UTXO
    source.utxos = [utxo]
    assignments = build_assignments(
        [utxo], dest, fee_base=25, fee_jitter=0, chain_tip=900_000, min_blocks_apart=2
    )
    return source, dest, utxo, assignments[0]


def test_build_psbt_includes_bip32_derivation():
    source, _dest, utxo, assignment = _bundle_fixture()
    raw = build_psbt(assignment, source)
    psbt = PSBT.parse(raw)
    derivations = psbt.inputs[0].bip32_derivations
    assert len(derivations) == 1
    (path,) = derivations.values()
    assert path.fingerprint == bytes.fromhex(source.keystore.fingerprint)
    assert path.derivation == parse_bip32_path(utxo.derivation_path)


def test_build_psbt_rejects_utxo_not_owned_by_source_wallet():
    source, _dest, utxo, assignment = _bundle_fixture()
    assignment.utxo.address = assignment.utxo.address[:-4] + "xxxx"
    with pytest.raises(ValueError, match="does not derive from Wallet A xpub"):
        build_psbt(assignment, source)


def test_write_psbt_bundle_rejects_forged_source_utxo(tmp_path: Path):
    source, dest, utxo, assignment = _bundle_fixture()
    # Address claims to be Wallet A's, but doesn't actually derive from its xpub
    # at the recorded path — e.g. a forged/edited session entry.
    assignment.utxo.address = assignment.utxo.address[:-4] + "xxxx"
    with pytest.raises(ValueError, match="does not derive from Wallet A xpub"):
        write_psbt_bundle(tmp_path, [assignment], source, dest)
