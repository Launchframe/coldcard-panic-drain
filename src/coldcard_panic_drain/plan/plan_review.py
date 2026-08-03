"""Interactive mapping review and plan options during ``plan``."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable, Protocol, Sequence, TextIO

import typer

from coldcard_panic_drain.plan.mapper import build_assignments
from coldcard_panic_drain.sparrow.models import DestinationAssignment, UtxoRecord, WalletSnapshot
from coldcard_panic_drain.util import normalize_display_unit
from coldcard_panic_drain.verify.mapping import MAPPING_ACK, OPTIONS_ACK, PLAN_EXIT_WORDS


class MappingTablePrinter(Protocol):
    def __call__(self, assignments: Sequence[DestinationAssignment], *, unit: str) -> None: ...


@dataclass
class PlanReviewState:
    assignments: list[DestinationAssignment]
    fee_base: int
    fee_jitter: float
    amount_unit: str
    utxos: Sequence[UtxoRecord]
    dest_wallet: WalletSnapshot
    chain_tip: int
    min_blocks_apart: int

    def rebuild_assignments(self) -> None:
        self.assignments = build_assignments(
            self.utxos,
            self.dest_wallet,
            fee_base=self.fee_base,
            fee_jitter=self.fee_jitter,
            chain_tip=self.chain_tip,
            min_blocks_apart=self.min_blocks_apart,
        )


def _run_options_menu(
    state: PlanReviewState,
    *,
    print_mapping_table: MappingTablePrinter,
    prompt: Callable[..., str],
    echo: Callable[..., None],
) -> None:
    """Adjust fees, display unit, and other plan knobs until operator returns."""
    while True:
        echo(
            "\n=== Plan options ===\n"
            f"  display: {state.amount_unit.upper()}\n"
            f"  fee-base: {state.fee_base} sat/vB\n"
            f"  fee-jitter: {state.fee_jitter} (±{state.fee_jitter:.0%} per UTXO)\n"
            "\n"
            "  [d] change display unit (btc/sats)\n"
            "  [b] change fee-base\n"
            "  [j] change fee-jitter\n"
            "  [r] redraw mapping table\n"
            "  [c] return to mapping review"
        )
        choice = prompt("Plan option", default="c").strip().lower()
        if choice in ("c", "", "continue", "done", "return"):
            return
        if choice in ("d", "display"):
            raw = prompt("Display amounts in", default=state.amount_unit).strip()
            try:
                state.amount_unit = normalize_display_unit(raw)
            except ValueError as e:
                echo(str(e), err=True)
                continue
        elif choice in ("b", "base", "fee-base"):
            raw = prompt("fee-base (sat/vB)", default=str(state.fee_base)).strip()
            try:
                new_base = int(raw)
            except ValueError:
                echo("fee-base must be a whole number (sat/vB).", err=True)
                continue
            if new_base < 0:
                echo("fee-base must be >= 0.", err=True)
                continue
            state.fee_base = new_base
            state.rebuild_assignments()
        elif choice in ("j", "jitter", "fee-jitter"):
            raw = prompt("fee-jitter (fraction)", default=str(state.fee_jitter)).strip()
            try:
                new_jitter = float(raw)
            except ValueError:
                echo("fee-jitter must be a number.", err=True)
                continue
            if new_jitter < 0:
                echo("fee-jitter must be >= 0.", err=True)
                continue
            state.fee_jitter = new_jitter
            state.rebuild_assignments()
        elif choice in ("r", "redraw", "table"):
            print_mapping_table(state.assignments, unit=state.amount_unit)
        else:
            echo("Enter d, b, j, r, or c.", err=True)


def _write_mapping_review_prompt(
    assignment_count: int,
    *,
    stdout: TextIO,
    retry: bool,
) -> None:
    if retry:
        stdout.write(
            f"\nNot recognized. Type {MAPPING_ACK} to save, {OPTIONS_ACK} to adjust "
            "fees or display, or exit/q to abort: "
        )
        return

    stdout.write(
        "\n"
        "=== Mapping review ===\n"
        "Review the table above. This tool cannot verify destination addresses at "
        "signing time — a wrong address would cause irreversible loss.\n\n"
        "After `generate`, sign each PSBT on Wallet A's Coldcard. Before signing "
        "each transaction, verify the destination address on the device and confirm "
        "it appears as a receive address in Sparrow Wallet B.\n"
        f"({assignment_count} PSBTs will be generated.)\n\n"
        f"Type {MAPPING_ACK} to save this mapping, {OPTIONS_ACK} to adjust fees "
        "or display, exit/q to abort, or Ctrl+C to abort: "
    )


def run_mapping_review(
    state: PlanReviewState,
    *,
    print_mapping_table: MappingTablePrinter,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    prompt: Callable[..., str] = typer.prompt,
    echo: Callable[..., None] = typer.echo,
) -> PlanReviewState:
    """Show mapping table and prompt for PROCEED or OPTIONS until mapping is accepted."""
    while True:
        print_mapping_table(state.assignments, unit=state.amount_unit)
        assignment_count = len(state.assignments)
        retry = False
        while True:
            _write_mapping_review_prompt(
                assignment_count,
                stdout=stdout,
                retry=retry,
            )
            stdout.flush()
            raw = stdin.readline()
            if raw == "":
                # EOF (closed/exhausted stdin) — never treat as "just retry" or
                # the loop would spin forever re-printing the prompt with no
                # way for a non-interactive caller to make progress.
                raise ValueError("Aborted: mapping not confirmed (no input received).")
            line = raw.strip()
            if line == MAPPING_ACK:
                return state
            if line.lower() in PLAN_EXIT_WORDS:
                raise ValueError("Aborted: mapping not confirmed.")
            if line == OPTIONS_ACK:
                _run_options_menu(
                    state,
                    print_mapping_table=print_mapping_table,
                    prompt=prompt,
                    echo=echo,
                )
                break
            retry = True
