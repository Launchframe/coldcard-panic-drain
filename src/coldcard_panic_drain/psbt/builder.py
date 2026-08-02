"""PSBT construction for single-UTXO drains."""

from __future__ import annotations

import hashlib
from pathlib import Path

from embit import script
from embit.psbt import PSBT
from embit.transaction import Transaction, TransactionInput, TransactionOutput

from coldcard_panic_drain.sparrow.models import DestinationAssignment, WalletSnapshot

# P2WPKH vsize estimates (conservative)
VBYTES_1IN_1OUT = 140


def _txid_bytes_le(txid_hex: str) -> bytes:
    return bytes.fromhex(txid_hex)[::-1]


def build_psbt(
    assignment: DestinationAssignment,
    source_wallet: WalletSnapshot,
) -> bytes:
    utxo = assignment.utxo
    fee_sats = max(1, VBYTES_1IN_1OUT * assignment.fee_sat_vb)
    if fee_sats >= utxo.value_sats:
        raise ValueError(
            f"Fee {fee_sats} sats >= UTXO value {utxo.value_sats} for {utxo.ref}"
        )
    out_value = utxo.value_sats - fee_sats

    spk_in = script.address_to_scriptpubkey(utxo.address)
    spk_out = script.address_to_scriptpubkey(assignment.address)

    vin = TransactionInput(
        _txid_bytes_le(utxo.txid),
        utxo.vout,
        sequence=0xFFFFFFFD,  # RBF enabled
    )
    vout = TransactionOutput(out_value, spk_out)
    tx = Transaction(vin=[vin], vout=[vout], version=2, locktime=assignment.nlocktime)

    psbt = PSBT(tx=tx)
    psbt.inputs[0].witness_utxo = TransactionOutput(utxo.value_sats, spk_in)

    return psbt.serialize()

def psbt_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_psbt_bundle(
    output_dir: Path,
    assignments: list[DestinationAssignment],
    source_wallet: WalletSnapshot,
) -> list[dict]:
    psbt_dir = output_dir / "psbts"
    psbt_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries = []
    for a in assignments:
        raw = build_psbt(a, source_wallet)
        out_path = psbt_dir / a.psbt_filename
        out_path.write_bytes(raw)
        manifest_entries.append(
            {
                "label": a.utxo.label,
                "utxo_ref": a.utxo.ref,
                "dest_address": a.address,
                "dest_index": a.receive_index,
                "fee_sat_vb": a.fee_sat_vb,
                "nlocktime": a.nlocktime,
                "psbt_file": a.psbt_filename,
                "sha256": psbt_sha256(raw),
                "value_sats": a.utxo.value_sats,
            }
        )
    import json

    (psbt_dir / "manifest.json").write_text(
        json.dumps(manifest_entries, indent=2), encoding="utf-8"
    )
    return manifest_entries
