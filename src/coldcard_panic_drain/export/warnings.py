"""Incomplete-drain warnings and banners."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Iterable, TextIO

from coldcard_panic_drain.sparrow.models import SkipReason, UtxoRecord
from coldcard_panic_drain.util import sats_to_btc_str


@dataclass
class SkipSummary:
    frozen: int = 0
    user_skipped: int = 0
    at_risk_sats: int = 0
    total_excluded: int = 0
    total_utxos: int = 0

    @property
    def incomplete(self) -> bool:
        return self.total_excluded > 0


def summarize_skips(utxos: Iterable[UtxoRecord]) -> SkipSummary:
    utxos = list(utxos)
    summary = SkipSummary(total_utxos=len(utxos))
    for u in utxos:
        if u.included and not u.frozen:
            continue
        summary.total_excluded += 1
        summary.at_risk_sats += u.value_sats
        if u.skip_reason == SkipReason.FROZEN or u.frozen:
            summary.frozen += 1
        elif u.skip_reason == SkipReason.USER_SKIPPED:
            summary.user_skipped += 1
    return summary


def print_frozen_utxo_warning(utxo: UtxoRecord, out: TextIO = sys.stderr) -> None:
    out.write(
        "FROZEN UTXO DETECTED — will NOT be included in this batch.\n"
        f"  Ref: {utxo.ref}  Amount: {sats_to_btc_str(utxo.value_sats)} BTC\n"
        "  Action: Unfreeze in Sparrow → re-sync → re-copy wallet file → re-run plan\n\n"
    )


def print_incomplete_banner(summary: SkipSummary, out: TextIO = sys.stderr) -> None:
    if not summary.incomplete:
        return
    btc = sats_to_btc_str(summary.at_risk_sats)
    lines = [
        "╔══════════════════════════════════════════════════════════════╗",
        "║  WARNING: DRAIN WILL NOT BE 100% COMPLETE                   ║",
        f"║  {summary.total_excluded} of {summary.total_utxos} UTXOs excluded ({btc} BTC remains at risk)   ║"[:64]
        + " " * max(0, 64 - len(f"║  {summary.total_excluded} of {summary.total_utxos} UTXOs excluded ({btc} BTC remains at risk)   ║"[:64]))
        + "║",
    ]
    if summary.frozen:
        lines.append(f"║    • {summary.frozen} frozen (unfreeze in Sparrow to include)              ║"[:64] + "║"[0])
    if summary.user_skipped:
        lines.append(f"║    • {summary.user_skipped} user-skipped during labeling                   ║"[:64] + "║"[0])
    lines.append("╚══════════════════════════════════════════════════════════════╝")
    # simpler fixed width banner
    out.write("\n")
    out.write("=" * 64 + "\n")
    out.write("WARNING: DRAIN WILL NOT BE 100% COMPLETE\n")
    out.write(
        f"  {summary.total_excluded} of {summary.total_utxos} UTXOs excluded "
        f"({btc} BTC remains at risk)\n"
    )
    if summary.frozen:
        out.write(f"    • {summary.frozen} frozen (unfreeze in Sparrow to include)\n")
    if summary.user_skipped:
        out.write(f"    • {summary.user_skipped} user-skipped during labeling\n")
    out.write("=" * 64 + "\n\n")


def require_incomplete_acknowledgment(summary: SkipSummary, stdin=None, stdout=None) -> None:
    import sys

    stdin = stdin or sys.stdin
    stdout = stdout or sys.stderr
    if not summary.incomplete:
        return
    print_incomplete_banner(summary, out=stdout)
    stdout.write('Type "I UNDERSTAND" to proceed with an incomplete drain: ')
    stdout.flush()
    reply = stdin.readline().strip()
    if reply != "I UNDERSTAND":
        raise SystemExit("Aborted: incomplete drain not acknowledged.")


def write_skipped_utxos(path, utxos: Iterable[UtxoRecord]) -> None:
    from pathlib import Path

    path = Path(path)
    excluded = [u for u in utxos if not u.included or u.frozen]
    if not excluded:
        path.write_text("No UTXOs were excluded. Drain covers all spendable coins.\n", encoding="utf-8")
        return
    chunks = []
    for u in excluded:
        reason = u.skip_reason.value if u.skip_reason else ("frozen" if u.frozen else "unknown")
        hint = (
            "Unfreeze in Sparrow, re-sync, re-copy wallet file, re-run plan."
            if u.frozen or reason == "frozen"
            else "Re-run plan and do not skip this UTXO, or accept funds remain at risk."
        )
        chunks.append(
            f"Ref: {u.ref}\n"
            f"Amount: {sats_to_btc_str(u.value_sats)} BTC ({u.value_sats:,} sats)\n"
            f"Reason: {reason}\n"
            f"Label: {u.label or '(none)'}\n"
            f"Remediation: {hint}\n"
        )
    path.write_text("\n---\n".join(chunks), encoding="utf-8")
