"""Destination address validation and mapping comparison."""

import pytest

from coldcard_panic_drain.plan.mapper import (
    build_assignments,
    compare_assignment_mapping,
    derive_receive_address,
    validate_dest_address,
)
from coldcard_panic_drain.psbt.builder import write_psbt_bundle
from coldcard_panic_drain.sparrow.models import DestinationAssignment, UtxoRecord

from conftest import make_test_wallet


def _utxo(wallet, label="Test") -> UtxoRecord:
    return UtxoRecord(
        txid="ef" * 32,
        vout=0,
        value_sats=3_000_000,
        height=890_000,
        received_at=None,
        address=derive_receive_address(wallet, 0),
        derivation_path="m/84'/0'/0'/0/0",
        label=label,
        included=True,
    )


def test_validate_dest_address_accepts_derived():
    dest = make_test_wallet()
    addr = derive_receive_address(dest, 3)
    validate_dest_address(dest, 3, addr)


def test_validate_dest_address_rejects_wrong_address():
    dest = make_test_wallet()
    good = derive_receive_address(dest, 0)
    with pytest.raises(ValueError, match="does not match Wallet B xpub"):
        validate_dest_address(dest, 0, good[:-4] + "xxxx")


def test_compare_assignment_mapping_detects_index_drift():
    dest = make_test_wallet()
    utxo = _utxo(dest)
    a1 = build_assignments(
        [utxo], dest, fee_base=20, fee_jitter=0, chain_tip=900_000, min_blocks_apart=2
    )[0]
    a2 = DestinationAssignment(
        utxo=utxo,
        receive_index=a1.receive_index + 1,
        address=derive_receive_address(dest, a1.receive_index + 1),
        fee_sat_vb=a1.fee_sat_vb,
        fee_sats=a1.fee_sats,
        nlocktime=a1.nlocktime,
        psbt_filename=a1.psbt_filename,
    )
    errors = compare_assignment_mapping([a1], [a2])
    assert any("receive index changed" in e for e in errors)


def test_compare_assignment_mapping_ignores_fee_jitter():
    dest = make_test_wallet()
    utxo = _utxo(dest)
    base = build_assignments(
        [utxo],
        dest,
        fee_base=20,
        fee_jitter=0.2,
        chain_tip=900_000,
        min_blocks_apart=2,
        rng=__import__("random").Random(1),
    )[0]
    other = DestinationAssignment(
        utxo=utxo,
        receive_index=base.receive_index,
        address=base.address,
        fee_sat_vb=base.fee_sat_vb + 5,
        fee_sats=base.fee_sats + 700,
        nlocktime=base.nlocktime,
        psbt_filename=base.psbt_filename,
    )
    assert compare_assignment_mapping([base], [other]) == []


def test_compare_assignment_mapping_detects_address_drift():
    dest = make_test_wallet()
    utxo = _utxo(dest)
    a1 = build_assignments(
        [utxo], dest, fee_base=20, fee_jitter=0, chain_tip=900_000, min_blocks_apart=2
    )[0]
    a2 = DestinationAssignment(
        utxo=utxo,
        receive_index=a1.receive_index,
        address=a1.address[:-4] + "xxxx",
        fee_sat_vb=a1.fee_sat_vb,
        fee_sats=a1.fee_sats,
        nlocktime=a1.nlocktime,
        psbt_filename=a1.psbt_filename,
    )
    errors = compare_assignment_mapping([a1], [a2])
    assert any("destination address changed" in e for e in errors)


def test_compare_assignment_mapping_detects_count_mismatch():
    dest = make_test_wallet()
    utxo = _utxo(dest)
    a1 = build_assignments(
        [utxo], dest, fee_base=20, fee_jitter=0, chain_tip=900_000, min_blocks_apart=2
    )
    errors = compare_assignment_mapping(a1, [])
    assert any("Assignment count mismatch" in e for e in errors)


def test_compare_assignment_mapping_detects_utxo_set_change():
    dest = make_test_wallet()
    u1 = _utxo(dest, label="A")
    u2 = _utxo(dest, label="B")
    u2.txid = "aa" * 32
    a1 = build_assignments(
        [u1], dest, fee_base=20, fee_jitter=0, chain_tip=900_000, min_blocks_apart=2
    )
    a2 = build_assignments(
        [u2], dest, fee_base=20, fee_jitter=0, chain_tip=900_000, min_blocks_apart=2
    )
    errors = compare_assignment_mapping(a1, a2)
    assert any("UTXO set changed" in e for e in errors)


def test_write_psbt_bundle_rejects_tampered_address(tmp_path):
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    dest = make_test_wallet(path="/tmp/b.mv.db", name="b")
    utxo = _utxo(source)
    good = build_assignments(
        [utxo],
        dest,
        fee_base=25,
        fee_jitter=0,
        chain_tip=900_000,
        min_blocks_apart=2,
    )[0]
    tampered = DestinationAssignment(
        utxo=utxo,
        receive_index=good.receive_index,
        address=good.address[:-4] + "xxxx",
        fee_sat_vb=good.fee_sat_vb,
        fee_sats=good.fee_sats,
        nlocktime=good.nlocktime,
        psbt_filename=good.psbt_filename,
    )
    with pytest.raises(ValueError, match="does not match Wallet B xpub"):
        write_psbt_bundle(tmp_path, [tampered], source, dest)
