"""Verify signed PSBTs against generated manifest."""

from __future__ import annotations

import json
from pathlib import Path

from embit import script
from embit.psbt import PSBT


def verify_signed_psbts(output_dir: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = output_dir / "psbts" / "manifest.json"
    if not manifest_path.is_file():
        return ["Missing psbts/manifest.json — run generate first."]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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
        out = psbt.tx.vout[0]
        out_script = out.script_pubkey
        addr = out_script.address()
        if addr != expected:
            errors.append(f"{signed_name}: output address {addr} != expected {expected}")
        expected_spk = script.address_to_scriptpubkey(expected)
        if out_script.serialize() != expected_spk.serialize():
            errors.append(f"{signed_name}: output script does not match destination address")
    return errors
