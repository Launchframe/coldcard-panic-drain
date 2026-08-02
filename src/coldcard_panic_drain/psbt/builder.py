"""PSBT construction for single-UTXO drains."""

from __future__ import annotations

import hashlib
from pathlib import Path

from embit import bip32, script
from embit.psbt import PSBT, DerivationPath
from embit.transaction import Transaction, TransactionInput, TransactionOutput

from coldcard_panic_drain.plan.mapper import validate_dest_address, validate_source_utxo
from coldcard_panic_drain.sparrow.models import DestinationAssignment, WalletSnapshot
from coldcard_panic_drain.util import parse_bip32_path

# P2WPKH vsize estimates (conservative)
VBYTES_1IN_1OUT = 140


def _txid_bytes_le(txid_hex: str) -> bytes:
    return bytes.fromhex(txid_hex)[::-1]


def _input_bip32_derivation(source_wallet: WalletSnapshot, utxo) -> tuple[object, DerivationPath]:
    """Compute the (pubkey, DerivationPath) pair for a UTXO's signing key.

    Without this, a PSBT input carries only a `witness_utxo` and no key-origin
    metadata — Coldcard has no declared way to know which of its own keys signs
    this input. Attaching it lets the device verify (and display) that the input
    truly belongs to its own seed/fingerprint at this path, rather than blindly
    matching scriptPubkeys.
    """
    ks = source_wallet.keystore
    path_ints = parse_bip32_path(utxo.derivation_path)
    if len(path_ints) < 2:
        raise ValueError(f"Malformed derivation path for {utxo.ref}: {utxo.derivation_path!r}")
    chain, idx = path_ints[-2], path_ints[-1]
    # `.get_public_key()` (not `.sec()`) — bip32_derivations keys must be EmbitKey
    # objects with their own `.serialize()`/`.write_to()`, not raw bytes. Explicitly
    # normalizing to a PublicKey also guards against ever signing with private key
    # material here: Sparrow watch-only wallets should only ever hand us an xpub.
    pubkey = bip32.HDKey.from_base58(ks.xpub).derive([chain, idx]).get_public_key()
    fingerprint = bytes.fromhex(ks.fingerprint)
    return pubkey, DerivationPath(fingerprint, path_ints)


def build_psbt(
    assignment: DestinationAssignment,
    source_wallet: WalletSnapshot,
) -> bytes:
    utxo = assignment.utxo
    # Defense in depth: the input we are about to spend must actually derive
    # from Wallet A's own xpub — closes the gap left by the prior pass, which
    # only validated the destination side.
    validate_source_utxo(source_wallet, utxo)

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
    pubkey, derivation = _input_bip32_derivation(source_wallet, utxo)
    psbt.inputs[0].bip32_derivations[pubkey] = derivation

    return psbt.serialize()

def psbt_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_psbt_bundle(
    output_dir: Path,
    assignments: list[DestinationAssignment],
    source_wallet: WalletSnapshot,
    dest_wallet: WalletSnapshot,
) -> list[dict]:
    psbt_dir = output_dir / "psbts"
    psbt_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries = []
    for a in assignments:
        validate_dest_address(dest_wallet, a.receive_index, a.address)
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

    manifest = {
        "dest_xpub": dest_wallet.keystore.xpub,
        "dest_fingerprint": dest_wallet.keystore.fingerprint,
        "entries": manifest_entries,
    }
    (psbt_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest_entries
