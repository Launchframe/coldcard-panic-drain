"""Post-flow checklist for user."""

from __future__ import annotations

from pathlib import Path

from coldcard_panic_drain.export.warnings import SkipSummary


def write_post_flow_checklist(path: Path, skip_summary: SkipSummary) -> None:
    lines = []
    if skip_summary.incomplete:
        lines.extend(
            [
                "INCOMPLETE DRAIN WARNING",
                f"  {skip_summary.total_excluded} UTXOs were NOT included in this batch.",
                f"  {skip_summary.at_risk_sats:,} sats remain on the compromised seed.",
                "  See SKIPPED-UTXOS.txt for details.",
                "",
            ]
        )
    lines.extend(
        [
            "FEE URGENCY (especially if using broadcast-due cron)",
            "  You are racing an attacker with the compromised seed.",
            "  Set a competitive --fee-base at plan time — fees are fixed in signed PSBTs.",
            "  If fees spike mid-drain: see docs/FEE-SPIKE-RECOVERY.md",
            "",
            "CALENDAR: import reminders.ics into Google Calendar / Outlook for manual broadcasts.",
            "  Quiet hours (--dnd-start/--dnd-end) shift calendar alarms only.",
            "  broadcast-due ignores quiet hours and may send txs overnight.",
            "",
            "┌─────────────────────────────────────────────────────────────┐",
            "│  IMPORTANT: Re-import labels into Wallet A                  │",
            "│                                                             │",
            "│  File → Import Wallet → Labels                              │",
            "│  Select: wallet-a-labels.jsonl                              │",
            "│                                                             │",
            "│  Do this BEFORE wiping Wallet A or closing Sparrow.         │",
            "│  coldcard-panic-drain does not modify Sparrow wallet files. │",
            "└─────────────────────────────────────────────────────────────┘",
            "",
            "Wallet B labels: import wallet-b-labels.jsonl before broadcasting.",
            "",
            "Signing: copy each file from psbts/ to the ROOT of the Wallet A microSD card.",
            "Do not leave PSBTs in a subfolder on the card — Coldcard Ready to Sign only lists the card root.",
            "Before EACH signature: verify destination address on device and in Sparrow Wallet B.",
            "See verify/coldcard-checklist.txt for the per-PSBT reference mapping.",
            "Signed: place files in psbts_signed/ → follow schedule.yaml.",
            "",
            "Manual broadcast: open signed PSBT in Sparrow.",
            "Auto broadcast: broadcast-due (local Bitcoin Core on localhost or *.local).",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
