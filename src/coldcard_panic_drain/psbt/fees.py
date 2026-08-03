"""PSBT fee estimation for single-input P2WPKH drains."""

from __future__ import annotations

import random

from coldcard_panic_drain.sparrow.models import DestinationAssignment

# P2WPKH vsize estimates (conservative)
VBYTES_1IN_1OUT = 140
MIN_FEE_SAT_VB = 1


def min_psbt_fee_sats() -> int:
    """Minimum absolute fee: 1 sat/vB × estimated vsize."""
    return VBYTES_1IN_1OUT * MIN_FEE_SAT_VB


def estimate_psbt_fee_sats(fee_sat_vb: int) -> int:
    """Estimated absolute fee for a single-input P2WPKH PSBT at the given rate."""
    return max(min_psbt_fee_sats(), VBYTES_1IN_1OUT * max(MIN_FEE_SAT_VB, fee_sat_vb))


def jittered_assignment_fees(
    fee_base: int,
    fee_jitter: float,
    rng: random.Random,
) -> tuple[int, int]:
    """Return (fee_sats, fee_sat_vb) with jitter applied to the absolute PSBT fee.

    Normally uses a multiplicative jitter draw. When the 1 sat/vB floor would absorb
    most of the lower tail (e.g. ``fee-base 1`` with moderate jitter), fees are drawn
    uniformly across the admissible integer range instead of piling up at the floor.
    """
    rate_sat_vb = max(MIN_FEE_SAT_VB, fee_base)
    base_fee_sats = VBYTES_1IN_1OUT * rate_sat_vb
    floor_sats = min_psbt_fee_sats()
    raw_min = round(base_fee_sats * (1 - fee_jitter))
    raw_max = round(base_fee_sats * (1 + fee_jitter))
    min_fee = max(floor_sats, raw_min)
    max_fee = max(min_fee, raw_max)

    if min_fee >= base_fee_sats:
        fee_sats = rng.randint(min_fee, max_fee)
    else:
        jitter = rng.uniform(-fee_jitter, fee_jitter)
        fee_sats = max(min_fee, round(base_fee_sats * (1 + jitter)))

    fee_sat_vb = max(MIN_FEE_SAT_VB, (fee_sats + VBYTES_1IN_1OUT - 1) // VBYTES_1IN_1OUT)
    return fee_sats, fee_sat_vb


def assignment_fee_sats(assignment: DestinationAssignment) -> int:
    """Absolute fee locked into the PSBT for this assignment."""
    if assignment.fee_sats > 0:
        return assignment.fee_sats
    return estimate_psbt_fee_sats(assignment.fee_sat_vb)
