"""Path / descriptor helpers."""

from __future__ import annotations


def path_to_hardened(derivation_path: str) -> str:
    parts = derivation_path.strip().lower().replace("m/", "").split("/")
    return "/".join(f"{p.replace(chr(39), '')}h" for p in parts if p)


def parse_bip32_path(derivation_path: str) -> list[int]:
    """Parse an absolute path like "m/84'/0'/0'/0/5" into BIP32 index ints."""
    parts = derivation_path.strip().lower().replace("m/", "").split("/")
    ints: list[int] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        hardened = p.endswith("'") or p.endswith("h")
        num = int(p.rstrip("'h"))
        ints.append(num + 0x80000000 if hardened else num)
    return ints


def derive_address_for_chain_index(keystore, chain: int, index: int) -> str:
    """Derive a bc1q address for an arbitrary (chain, index) pair from a keystore's xpub.

    `chain` is embedded directly in the descriptor string (not passed to
    ``Descriptor.derive``) because embit's ``derive(idx, branch_index)`` only fills
    the wildcard "*" from `idx`; `branch_index` is for multipath ``<0;1>`` descriptors
    and is otherwise silently ignored. Passing chain as `idx` and the real index as
    `branch_index` (as this codebase previously did) collapses every derived address
    to the wildcard's chain value, regardless of the real index.
    """
    from embit.descriptor import Descriptor

    account = keystore.derivation_path.rstrip("/")
    desc_str = (
        f"wpkh([{keystore.fingerprint}/{path_to_hardened(account)}]"
        f"{keystore.xpub}/{chain}/*)"
    )
    return Descriptor.from_string(desc_str).derive(index).address()


def sanitize_label(label: str, max_len: int = 40) -> str:
    import re

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", label.strip().lower()).strip("-")
    return (slug[:max_len] or "utxo")


def sats_to_btc_str(sats: int) -> str:
    return f"{sats / 100_000_000:.8f}"
