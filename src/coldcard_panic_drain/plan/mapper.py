"""Map source UTXOs to destination receive addresses."""

from __future__ import annotations

import random
from typing import Sequence

from embit.descriptor import Descriptor

from coldcard_panic_drain.sparrow.models import DestinationAssignment, UtxoRecord, WalletSnapshot
from coldcard_panic_drain.util import path_to_hardened, sanitize_label


def _account_descriptor(wallet: WalletSnapshot) -> Descriptor:
    ks = wallet.keystore
    account = ks.derivation_path.rstrip("/")
    desc_str = f"wpkh([{ks.fingerprint}/{path_to_hardened(account)}]{ks.xpub}/0/*)"
    return Descriptor.from_string(desc_str)


def derive_receive_address(wallet: WalletSnapshot, index: int) -> str:
    return _account_descriptor(wallet).derive(0, index).address()


def validate_dest_address(wallet: WalletSnapshot, index: int, address: str) -> None:
    """Ensure address derives from Wallet B xpub at the given receive index."""
    expected = derive_receive_address(wallet, index)
    if expected != address:
        raise ValueError(
            f"Destination address at index {index} does not match Wallet B xpub "
            f"(session/plan mismatch — aborting to prevent wrong outputs)"
        )


def compare_assignment_mapping(
    session_assignments: Sequence[DestinationAssignment],
    rebuilt: Sequence[DestinationAssignment],
) -> list[str]:
    """Compare utxo→(index, address) mapping; ignore fee jitter differences."""
    errors: list[str] = []
    if len(session_assignments) != len(rebuilt):
        errors.append(
            f"Assignment count mismatch: session={len(session_assignments)}, "
            f"rebuilt={len(rebuilt)}"
        )
        return errors
    sess_by_ref = {a.utxo.ref: a for a in session_assignments}
    reb_by_ref = {a.utxo.ref: a for a in rebuilt}
    if sess_by_ref.keys() != reb_by_ref.keys():
        errors.append("UTXO set changed between session and current wallet state")
        return errors
    for ref, sa in sess_by_ref.items():
        ra = reb_by_ref[ref]
        if sa.receive_index != ra.receive_index:
            errors.append(
                f"{ref}: receive index changed ({sa.receive_index} vs {ra.receive_index})"
            )
        if sa.address != ra.address:
            errors.append(f"{ref}: destination address changed since plan")
    return errors


def build_assignments(
    source_utxos: Sequence[UtxoRecord],
    dest_wallet: WalletSnapshot,
    *,
    fee_base: int,
    fee_jitter: float,
    chain_tip: int,
    min_blocks_apart: int,
    rng: random.Random | None = None,
) -> list[DestinationAssignment]:
    rng = rng or random.Random()
    included = [u for u in source_utxos if u.included and not u.frozen]
    included.sort(key=lambda u: u.value_sats, reverse=True)

    start_index = dest_wallet.next_receive_index
    # avoid collision with already-used indices
    used = set(dest_wallet.used_receive_indices)
    assignments: list[DestinationAssignment] = []
    slug_counts: dict[str, int] = {}

    idx = start_index
    for order, utxo in enumerate(included):
        while idx in used:
            idx += 1
        address = derive_receive_address(dest_wallet, idx)
        jitter = rng.uniform(-fee_jitter, fee_jitter)
        fee_sat_vb = max(1, round(fee_base * (1 + jitter)))
        nlocktime = chain_tip + (order + 1) * min_blocks_apart
        base_slug = sanitize_label(utxo.label)
        n = slug_counts.get(base_slug, 0)
        slug_counts[base_slug] = n + 1
        slug = base_slug if n == 0 else f"{base_slug}-{n + 1}"
        psbt_name = f"{order + 1:03d}-{slug}.psbt"
        assignments.append(
            DestinationAssignment(
                utxo=utxo,
                receive_index=idx,
                address=address,
                fee_sat_vb=fee_sat_vb,
                nlocktime=nlocktime,
                psbt_filename=psbt_name,
            )
        )
        used.add(idx)
        idx += 1
    return assignments
