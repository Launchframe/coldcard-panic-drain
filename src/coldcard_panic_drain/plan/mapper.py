"""Map source UTXOs to destination receive addresses."""

from __future__ import annotations

import random
from typing import Sequence

from coldcard_panic_drain.psbt.fees import jittered_assignment_fees
from coldcard_panic_drain.sparrow.models import DestinationAssignment, UtxoRecord, WalletSnapshot
from coldcard_panic_drain.sparrow.receive import next_free_receive_index, used_receive_sets
from coldcard_panic_drain.util import derive_address_for_chain_index, sanitize_label


def derive_receive_address(wallet: WalletSnapshot, index: int) -> str:
    return derive_address_for_chain_index(wallet.keystore, 0, index)


def derive_address_at_path(wallet: WalletSnapshot, derivation_path: str) -> str:
    """Derive the address a UTXO's own `derivation_path` should have under `wallet`'s xpub."""
    parts = derivation_path.strip().split("/")
    if len(parts) < 2:
        raise ValueError(f"Malformed derivation path: {derivation_path!r}")
    chain = int(parts[-2])
    idx = int(parts[-1])
    return derive_address_for_chain_index(wallet.keystore, chain, idx)


def validate_dest_address(wallet: WalletSnapshot, index: int, address: str) -> None:
    """Ensure address derives from Wallet B xpub at the given receive index."""
    expected = derive_receive_address(wallet, index)
    if expected != address:
        raise ValueError(
            f"Destination address at index {index} does not match Wallet B xpub "
            f"(session/plan mismatch — aborting to prevent wrong outputs)"
        )


def validate_source_utxo(wallet: WalletSnapshot, utxo: UtxoRecord) -> None:
    """Ensure a session-cached UTXO's address truly derives from Wallet A's own xpub.

    Defense-in-depth against a tampered/forged `labels-session.json`: without this,
    an attacker (or a corrupted file) could point an arbitrary txid:vout/address at
    Wallet A and have a PSBT built for it with no cross-check that it actually
    belongs to Wallet A's keystore.
    """
    expected = derive_address_at_path(wallet, utxo.derivation_path)
    if expected != utxo.address:
        raise ValueError(
            f"{utxo.ref}: address does not derive from Wallet A xpub at "
            f"{utxo.derivation_path} (session/tamper mismatch — aborting to avoid "
            "building a PSBT for a UTXO not owned by the source wallet)"
        )


def validate_source_utxos(
    source_wallet: WalletSnapshot, utxos: Sequence[UtxoRecord]
) -> list[str]:
    """Cross-check session-cached, in-batch UTXOs against a freshly loaded Wallet A.

    Catches three fund-safety gaps left open by the dest-only checks added in the
    prior pass: UTXOs already spent since `plan` (missing from the fresh unspent
    set), UTXOs whose cached value/address drifted (tampered or stale session), and
    UTXOs whose address does not actually derive from Wallet A's own xpub.
    """
    errors: list[str] = []
    fresh_by_ref = {u.ref: u for u in source_wallet.utxos}
    for u in utxos:
        if not u.included or u.frozen:
            continue
        fresh = fresh_by_ref.get(u.ref)
        if fresh is None:
            errors.append(
                f"{u.ref}: not found in current Wallet A unspent set "
                "(already spent, wrong wallet file, or tampered session)"
            )
            continue
        if fresh.value_sats != u.value_sats:
            errors.append(
                f"{u.ref}: value changed since plan "
                f"({u.value_sats} vs {fresh.value_sats} sats)"
            )
        if fresh.address != u.address:
            errors.append(f"{u.ref}: address changed since plan — possible tampered session")
        try:
            validate_source_utxo(source_wallet, u)
        except ValueError as e:
            errors.append(str(e))
    return errors


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

    used_indices, used_addresses = used_receive_sets(dest_wallet)
    assignments: list[DestinationAssignment] = []
    slug_counts: dict[str, int] = {}

    idx = next_free_receive_index(dest_wallet)
    for order, utxo in enumerate(included):
        while idx in used_indices or derive_receive_address(dest_wallet, idx) in used_addresses:
            idx += 1
        address = derive_receive_address(dest_wallet, idx)
        if address in used_addresses:
            raise RuntimeError(
                f"Wallet B receive index {idx} collides with a previously used address. "
                "Re-sync Wallet B in Sparrow, re-copy the .mv.db, and re-run plan."
            )
        fee_sats, fee_sat_vb = jittered_assignment_fees(fee_base, fee_jitter, rng)
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
                fee_sats=fee_sats,
                nlocktime=nlocktime,
                psbt_filename=psbt_name,
            )
        )
        used_indices.add(idx)
        used_addresses.add(address)
        idx += 1
    return assignments
