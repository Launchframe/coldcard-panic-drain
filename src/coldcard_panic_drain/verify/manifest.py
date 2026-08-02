"""Verify signed PSBTs against generated manifest."""

from __future__ import annotations

import json
from pathlib import Path

from embit import script
from embit.psbt import PSBT

from coldcard_panic_drain.plan.mapper import validate_dest_address
from coldcard_panic_drain.sparrow.models import KeystoreInfo, WalletSnapshot


def _load_manifest(output_dir: Path) -> tuple[list[dict], str, str]:
    manifest_path = output_dir / "psbts" / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("Missing psbts/manifest.json — run generate first.")
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw, "", ""
    entries = raw.get("entries") or []
    return entries, raw.get("dest_xpub", ""), raw.get("dest_fingerprint", "")


def verify_signed_psbts(output_dir: Path) -> list[str]:
    errors: list[str] = []
    try:
        manifest, dest_xpub, dest_fingerprint = _load_manifest(output_dir)
    except FileNotFoundError as e:
        return [str(e)]

    dest_wallet: WalletSnapshot | None = None
    if dest_xpub and dest_fingerprint:
        dest_wallet = WalletSnapshot(
            path="",
            name="manifest",
            chain_tip_height=0,
            keystore=KeystoreInfo(
                fingerprint=dest_fingerprint,
                derivation_path="m/84'/0'/0'",
                xpub=dest_xpub,
                origin="",
            ),
        )

    signed_dir = output_dir / "psbts_signed"
    for entry in manifest:
        unsigned_name = entry["psbt_file"]
        signed_name = unsigned_name.replace(".psbt", "-signed.psbt")
        signed_path = signed_dir / signed_name
        if not signed_path.is_file():
            errors.append(f"Missing signed PSBT: {signed_path}")
            continue
        try:
            psbt = PSBT.parse(signed_path.read_bytes())
        except Exception as e:
            errors.append(f"Failed to parse {signed_name}: {e}")
            continue
        if len(psbt.inputs) != 1:
            errors.append(f"{signed_name}: expected 1 input, got {len(psbt.inputs)}")
        if len(psbt.outputs) != 1:
            errors.append(f"{signed_name}: expected 1 output, got {len(psbt.outputs)}")
        expected = entry["dest_address"]
        dest_index = entry.get("dest_index")
        out = psbt.tx.vout[0]
        out_script = out.script_pubkey
        addr = out_script.address()
        if addr != expected:
            errors.append(f"{signed_name}: output address {addr} != expected {expected}")
        expected_spk = script.address_to_scriptpubkey(expected)
        if out_script.serialize() != expected_spk.serialize():
            errors.append(f"{signed_name}: output script does not match destination address")
        if dest_wallet is not None and dest_index is not None:
            try:
                validate_dest_address(dest_wallet, dest_index, expected)
            except ValueError as e:
                errors.append(f"{signed_name}: {e}")
    return errors
