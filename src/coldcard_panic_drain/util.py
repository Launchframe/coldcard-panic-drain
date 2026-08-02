"""Path / descriptor helpers."""

from __future__ import annotations


def path_to_hardened(derivation_path: str) -> str:
    parts = derivation_path.strip().lower().replace("m/", "").split("/")
    return "/".join(f"{p.replace(chr(39), '')}h" for p in parts if p)


def sanitize_label(label: str, max_len: int = 40) -> str:
    import re

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", label.strip().lower()).strip("-")
    return (slug[:max_len] or "utxo")


def sats_to_btc_str(sats: int) -> str:
    return f"{sats / 100_000_000:.8f}"
