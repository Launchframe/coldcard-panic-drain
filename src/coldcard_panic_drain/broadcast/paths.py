"""Path helpers for broadcast workflow."""

from __future__ import annotations

from pathlib import Path


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
