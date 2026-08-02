"""Manifest verification with xpub cross-check."""

import json
from pathlib import Path

from coldcard_panic_drain.plan.mapper import build_assignments, derive_receive_address
from coldcard_panic_drain.psbt.builder import write_psbt_bundle
from coldcard_panic_drain.sparrow.models import UtxoRecord
from coldcard_panic_drain.verify.manifest import verify_signed_psbts

from conftest import make_test_wallet


def _setup_bundle(tmp_path: Path):
    source = make_test_wallet(path="/tmp/a.mv.db", name="a")
    dest = make_test_wallet(path="/tmp/b.mv.db", name="b")
    utxo = UtxoRecord(
        txid="12" * 32,
        vout=0,
        value_sats=4_000_000,
        height=890_000,
        received_at=None,
        address=derive_receive_address(source, 0),
        derivation_path="m/84'/0'/0'/0/0",
        label="Drain",
        included=True,
    )
    assignments = build_assignments(
        [utxo],
        dest,
        fee_base=25,
        fee_jitter=0,
        chain_tip=900_000,
        min_blocks_apart=2,
    )
    write_psbt_bundle(tmp_path, assignments, source, dest)
    return tmp_path, assignments


def test_manifest_includes_dest_xpub(tmp_path: Path):
    out, _ = _setup_bundle(tmp_path)
    manifest = json.loads((out / "psbts" / "manifest.json").read_text(encoding="utf-8"))
    assert "dest_xpub" in manifest
    assert "dest_fingerprint" in manifest
    assert len(manifest["entries"]) == 1


def test_verify_manifest_missing_signed(tmp_path: Path):
    _setup_bundle(tmp_path)
    errors = verify_signed_psbts(tmp_path)
    assert any("Missing signed PSBT" in e for e in errors)
