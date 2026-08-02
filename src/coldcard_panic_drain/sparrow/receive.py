"""External receive chain helpers for Wallet B destination allocation."""

from __future__ import annotations

from coldcard_panic_drain.sparrow.models import KeystoreInfo, WalletSnapshot
from coldcard_panic_drain.util import derive_address_for_chain_index


def receive_index_from_path(derivation_path: str) -> int | None:
    """Parse BIP84 external receive index from a wallet node path (…/0/i)."""
    parts = derivation_path.strip().split("/")
    if len(parts) < 2:
        return None
    if parts[-2] != "0":
        return None
    try:
        return int(parts[-1])
    except ValueError:
        return None


def derive_receive_address_for_path(keystore: KeystoreInfo, derivation_path: str) -> str | None:
    idx = receive_index_from_path(derivation_path)
    if idx is None:
        return None
    return derive_address_for_chain_index(keystore, 0, idx)


def collect_used_receive_state(
    keystore: KeystoreInfo,
    derivation_paths: list[str],
) -> tuple[list[int], list[str]]:
    """Return sorted used external receive indices and their derived addresses."""
    indices: set[int] = set()
    addresses: set[str] = set()
    for path in derivation_paths:
        idx = receive_index_from_path(path)
        if idx is None:
            continue
        indices.add(idx)
        addresses.add(derive_address_for_chain_index(keystore, 0, idx))
    return sorted(indices), sorted(addresses)


def used_receive_sets(wallet: WalletSnapshot) -> tuple[set[int], set[str]]:
    return set(wallet.used_receive_indices), set(wallet.used_receive_addresses)


def next_free_receive_index(wallet: WalletSnapshot) -> int:
    used_indices, used_addresses = used_receive_sets(wallet)
    idx = 0
    while idx in used_indices or derive_address_for_chain_index(wallet.keystore, 0, idx) in used_addresses:
        idx += 1
    return idx
