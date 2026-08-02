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
            "Signing: copy psbts/*.psbt to Coldcard microSD → Ready to Sign.",
            "Signed: place files in psbts_signed/ → follow schedule.yaml.",
            "",
            "Broadcast: only Sparrow communicates over the wire.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
