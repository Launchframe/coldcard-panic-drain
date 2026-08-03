"""Path helpers for broadcast workflow."""

from __future__ import annotations

from pathlib import Path

SIGNED_PSBT_SUBDIR = "psbts_signed"


def signed_psbt_dir(output_dir: Path) -> Path:
    """Directory where operators place Coldcard-signed PSBTs after signing."""
    return output_dir / SIGNED_PSBT_SUBDIR


def signed_psbt_relpath(unsigned_filename: str) -> str:
    """Relative path under the output dir for a signed PSBT matching an unsigned name."""
    signed_name = unsigned_filename.replace(".psbt", "-signed.psbt")
    return f"{SIGNED_PSBT_SUBDIR}/{signed_name}"


def ensure_signed_psbt_dir_ready(output_dir: Path) -> Path:
    """Require psbts_signed/ to exist with at least one signed PSBT before broadcasting."""
    signed_dir = signed_psbt_dir(output_dir)
    if not signed_dir.is_dir():
        raise ValueError(
            f"Missing {SIGNED_PSBT_SUBDIR}/ directory under {output_dir}. "
            "Run `generate`, sign PSBTs on Coldcard, then copy *-signed.psbt files "
            f"into {signed_dir}/"
        )
    if not any(signed_dir.glob("*.psbt")):
        raise ValueError(
            f"{SIGNED_PSBT_SUBDIR}/ exists but contains no .psbt files. "
            f"Copy signed PSBTs from Coldcard into {signed_dir}/ before running broadcast-due."
        )
    return signed_dir


def signed_path_under_output(output_dir: Path, signed_rel: str) -> Path:
    """Resolve signed PSBT path; reject absolute paths and traversal outside output_dir."""
    rel = (signed_rel or "").strip()
    if not rel:
        raise ValueError("schedule entry missing signed PSBT path")
    rel_path = Path(rel)
    if rel_path.is_absolute():
        raise ValueError(f"signed path must be relative to output dir: {rel!r}")
    resolved = (output_dir / rel_path).resolve()
    base = output_dir.resolve()
    if base not in resolved.parents and resolved != base:
        raise ValueError(f"signed PSBT path escapes output directory: {rel!r}")
    return resolved
