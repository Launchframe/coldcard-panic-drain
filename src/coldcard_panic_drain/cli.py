"""coldcard-panic-drain CLI."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from coldcard_panic_drain.broadcast.core_rpc import CoreRpcClient
from coldcard_panic_drain.broadcast.runner import FEE_URGENCY_BANNER, run_broadcast_due
from coldcard_panic_drain.export.bip329 import write_wallet_a_labels, write_wallet_b_labels
from coldcard_panic_drain.export.mapping_csv import write_mapping_csv
from coldcard_panic_drain.export.post_flow import write_post_flow_checklist
from coldcard_panic_drain.export.warnings import (
    print_incomplete_banner,
    require_incomplete_acknowledgment,
    summarize_skips,
    write_skipped_utxos,
)
from coldcard_panic_drain.network_guard import enable_localhost_guard
from coldcard_panic_drain.plan.labeling import (
    apply_frozen_exclusions,
    prompt_for_labels,
    validate_ready_for_generate,
)
from coldcard_panic_drain.plan.mapper import (
    build_assignments,
    compare_assignment_mapping,
    validate_dest_address,
    validate_source_utxos,
)
from coldcard_panic_drain.plan.session import DrainSession, session_path
from coldcard_panic_drain.psbt.builder import write_psbt_bundle
from coldcard_panic_drain.schedule.ics_export import write_ics_calendar
from coldcard_panic_drain.schedule.load import load_schedule
from coldcard_panic_drain.schedule.quiet_hours import parse_quiet_hours
from coldcard_panic_drain.schedule.remind_logic import compute_remind_status
from coldcard_panic_drain.schedule.yaml_manifest import write_schedule
from coldcard_panic_drain.sparrow.h2_reader import load_wallet
from coldcard_panic_drain.sparrow.models import LabelSource
from coldcard_panic_drain.util import sats_to_btc_str
from coldcard_panic_drain.verify.checklist import write_verification_checklist
from coldcard_panic_drain.verify.manifest import verify_signed_psbts
from coldcard_panic_drain.verify.ownership import confirm_dest_wallet_ownership
from coldcard_panic_drain.wipe import init_ram_workspace, wipe_workspace

app = typer.Typer(
    name="coldcard-panic-drain",
    help="Offline Sparrow panic drain: labels + batch PSBTs for Coldcard signing.",
    no_args_is_help=True,
    add_completion=False,
)


def _common_options(
    source: Path = typer.Option(..., "--source", "-s", help="Wallet A Sparrow .mv.db"),
    dest: Path = typer.Option(..., "--dest", "-d", help="Wallet B Sparrow .mv.db"),
    output: Path = typer.Option(..., "--output", "-o", help="Output directory (e.g. microSD)"),
    fee_base: int = typer.Option(25, "--fee-base", help="Base fee rate (sat/vB)"),
    fee_jitter: float = typer.Option(0.15, "--fee-jitter", help="Fee jitter fraction"),
    min_blocks_apart: int = typer.Option(2, "--min-blocks-apart", help="nLockTime spacing"),
    spread_hours: float = typer.Option(48.0, "--spread-hours", help="Broadcast schedule spread"),
) -> dict:
    return {
        "source": source,
        "dest": dest,
        "output": output,
        "fee_base": fee_base,
        "fee_jitter": fee_jitter,
        "min_blocks_apart": min_blocks_apart,
        "spread_hours": spread_hours,
    }


def _mark_existing_labels(utxos) -> None:
    for u in utxos:
        if u.label.strip() and u.label_source is None:
            u.label_source = LabelSource.EXISTING


def _load_pair(source: Path, dest: Path):
    source_wallet = load_wallet(source)
    dest_wallet = load_wallet(dest)
    return source_wallet, dest_wallet


def _print_mapping_table(assignments) -> None:
    typer.echo("\nMapping (Wallet A UTXO → Wallet B receive):")
    typer.echo(f"{'Label':<24} {'Amount (BTC)':>14}  {'Dest index':>10}  Address")
    typer.echo("-" * 90)
    for a in assignments:
        typer.echo(
            f"{a.utxo.label[:24]:<24} {sats_to_btc_str(a.utxo.value_sats):>14}  "
            f"{a.receive_index:>10}  {a.address}"
        )


def _confirm_addresses(assignments, *, batch_after: int = 3) -> None:
    if not assignments:
        return
    typer.echo("\nColdcard verification (Wallet B):")
    typer.echo("Advanced → View Identity → Address — confirm each index matches.\n")
    for i, a in enumerate(assignments):
        typer.echo(f'Index {a.receive_index} | Label: "{a.utxo.label}"')
        typer.echo(f"Address: {a.address}")
        if i + 1 >= batch_after and i + 1 < len(assignments):
            typer.echo(
                f"\n({len(assignments) - i - 1} addresses remain. "
                "Type CONFIRM to accept all remaining after verification on device.)"
            )
            reply = typer.prompt("Type CONFIRM", default="")
            if reply.strip() != "CONFIRM":
                raise typer.Exit("Aborted: address verification not confirmed.")
            return
        reply = typer.prompt("Type CONFIRM after verifying on Coldcard", default="")
        if reply.strip() != "CONFIRM":
            raise typer.Exit("Aborted: address verification not confirmed.")


@app.callback()
def main() -> None:
    """Entry: localhost-only network guard and RAM workspace."""
    enable_localhost_guard()
    init_ram_workspace()


@app.command()
def plan(
    source: Path = typer.Option(..., "--source", "-s"),
    dest: Path = typer.Option(..., "--dest", "-d"),
    output: Path = typer.Option(..., "--output", "-o"),
    fee_base: int = typer.Option(25, "--fee-base"),
    fee_jitter: float = typer.Option(0.15, "--fee-jitter"),
    min_blocks_apart: int = typer.Option(2, "--min-blocks-apart"),
    spread_hours: float = typer.Option(48.0, "--spread-hours"),
    dnd_start: Optional[str] = typer.Option(None, "--dnd-start", help="Quiet hours start HH:MM"),
    dnd_end: Optional[str] = typer.Option(None, "--dnd-end", help="Quiet hours end HH:MM"),
    timezone: Optional[str] = typer.Option(None, "--timezone", help="IANA tz for quiet hours"),
    calendar_alarm_minutes: int = typer.Option(15, "--calendar-alarm-minutes"),
) -> None:
    """Read wallets, label UTXOs, preview mapping — no PSBT writes."""
    try:
        quiet_hours = parse_quiet_hours(dnd_start, dnd_end, timezone)
    except ValueError as e:
        typer.echo(f"ERROR: {e}", err=True)
        raise typer.Exit(1) from e
    output.mkdir(parents=True, exist_ok=True)
    source_wallet, dest_wallet = _load_pair(source, dest)

    try:
        ownership_index = confirm_dest_wallet_ownership(dest_wallet)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from e

    utxos = source_wallet.utxos
    _mark_existing_labels(utxos)
    apply_frozen_exclusions(utxos)
    prompt_for_labels(utxos)

    summary = summarize_skips(utxos)
    print_incomplete_banner(summary)

    assignments = build_assignments(
        utxos,
        dest_wallet,
        fee_base=fee_base,
        fee_jitter=fee_jitter,
        chain_tip=source_wallet.chain_tip_height,
        min_blocks_apart=min_blocks_apart,
    )
    if not assignments:
        typer.echo("No UTXOs in batch. Unfreeze or label coins, then re-run plan.", err=True)
        raise typer.Exit(1)

    _print_mapping_table(assignments)
    _confirm_addresses(assignments)

    session = DrainSession.from_wallets(
        source_wallet,
        dest_wallet,
        fee_base,
        fee_jitter,
        min_blocks_apart,
        spread_hours,
        quiet_hours_start=dnd_start,
        quiet_hours_end=dnd_end,
        quiet_hours_timezone=timezone,
        calendar_alarm_minutes=calendar_alarm_minutes,
    )
    for u in utxos:
        session.update_utxo(u)
    session.set_assignments(assignments)
    session.dest_ownership_confirmed = True
    session.dest_ownership_checked_index = ownership_index
    session.addresses_confirmed = True
    session.save(session_path(output))

    typer.echo(f"\nSession saved to {session_path(output)}")
    typer.echo("Run `generate` with the same --output to write PSBTs and labels.")


@app.command()
def generate(
    output: Path = typer.Option(..., "--output", "-o"),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip I UNDERSTAND gate for incomplete drains",
    ),
) -> None:
    """Write PSBTs, BIP-329 labels, schedule, and checklists."""
    output.mkdir(parents=True, exist_ok=True)
    sp = session_path(output)
    if not sp.is_file():
        typer.echo(f"Missing {sp}. Run `plan` first.", err=True)
        raise typer.Exit(1)

    session = DrainSession.load(sp)
    try:
        session.require_plan_gates()
    except ValueError as e:
        typer.echo(f"ERROR: {e}", err=True)
        raise typer.Exit(1) from e

    source_wallet, dest_wallet = _load_pair(Path(session.source_path), Path(session.dest_path))

    try:
        session.verify_dest_wallet(dest_wallet)
        session.verify_source_wallet(source_wallet)
    except ValueError as e:
        typer.echo(f"ERROR: {e}", err=True)
        raise typer.Exit(1) from e

    utxos = session.utxo_objects()
    validate_ready_for_generate(utxos)

    source_utxo_errors = validate_source_utxos(source_wallet, utxos)
    if source_utxo_errors:
        for err in source_utxo_errors:
            typer.echo(f"ERROR: {err}", err=True)
        typer.echo(
            "Source wallet state changed since plan (spent, swapped, or tampered "
            "UTXOs). Re-run `plan` — do not generate PSBTs from a stale source snapshot.",
            err=True,
        )
        raise typer.Exit(1)

    summary = summarize_skips(utxos)
    if summary.incomplete and not yes:
        require_incomplete_acknowledgment(summary)

    try:
        assignments = session.assignment_objects(utxos)
    except ValueError as e:
        typer.echo(f"ERROR: {e}", err=True)
        raise typer.Exit(1) from e

    # Defense in depth: rebuild mapping and abort if dest wallet state drifted.
    rebuilt = build_assignments(
        utxos,
        dest_wallet,
        fee_base=session.fee_base,
        fee_jitter=session.fee_jitter,
        chain_tip=session.chain_tip_height,
        min_blocks_apart=session.min_blocks_apart,
    )
    mapping_errors = compare_assignment_mapping(assignments, rebuilt)
    if mapping_errors:
        for err in mapping_errors:
            typer.echo(f"ERROR: {err}", err=True)
        typer.echo(
            "Destination wallet state changed since plan (indices/addresses differ). "
            "Re-run `plan` — do not generate PSBTs with stale assignments.",
            err=True,
        )
        raise typer.Exit(1)

    for a in assignments:
        try:
            validate_dest_address(dest_wallet, a.receive_index, a.address)
        except ValueError as e:
            typer.echo(f"ERROR: {e}", err=True)
            raise typer.Exit(1) from e

    write_psbt_bundle(output, assignments, source_wallet, dest_wallet)
    write_wallet_a_labels(output / "wallet-a-labels.jsonl", assignments, source_wallet)
    write_wallet_b_labels(output / "wallet-b-labels.jsonl", assignments, dest_wallet)
    write_mapping_csv(output / "mapping.csv", assignments, utxos)
    schedule_entries = write_schedule(
        output / "schedule.yaml",
        assignments,
        spread_hours=float(session.spread_hours),
        quiet_hours=session.quiet_hours(),
    )
    write_ics_calendar(
        output / "reminders.ics",
        schedule_entries,
        batch_name=output.name,
        alarm_minutes=session.calendar_alarm_minutes,
        timezone=session.quiet_hours_timezone,
    )
    write_verification_checklist(
        output / "verify" / "coldcard-checklist.txt",
        assignments,
        dest_wallet,
        ownership_checked_index=session.dest_ownership_checked_index,
    )
    write_skipped_utxos(output / "SKIPPED-UTXOS.txt", utxos)
    write_post_flow_checklist(output / "POST-FLOW-CHECKLIST.txt", summary)
    session.set_assignments(assignments)
    session.save(sp)

    typer.echo(f"\nGenerated {len(assignments)} PSBTs in {output / 'psbts'}")
    print_incomplete_banner(summary, out=sys.stdout)
    typer.echo("\n" + (output / "POST-FLOW-CHECKLIST.txt").read_text(encoding="utf-8"))


@app.command("verify-manifest")
def verify_manifest(
    output: Path = typer.Option(..., "--output", "-o"),
) -> None:
    """Validate signed PSBTs in psbts_signed/ against manifest."""
    errors = verify_signed_psbts(output)
    if errors:
        for e in errors:
            typer.echo(f"ERROR: {e}", err=True)
        raise typer.Exit(1)
    typer.echo("All signed PSBTs match the generated manifest.")


@app.command("export-calendar")
def export_calendar(
    output: Path = typer.Option(..., "--output", "-o"),
    alarm_minutes: int = typer.Option(15, "--calendar-alarm-minutes"),
) -> None:
    """Regenerate reminders.ics from schedule.yaml."""
    sched_path = output / "schedule.yaml"
    if not sched_path.is_file():
        typer.echo(f"Missing {sched_path}", err=True)
        raise typer.Exit(1)
    doc = load_schedule(sched_path)
    qh = doc.get("quiet_hours") or {}
    write_ics_calendar(
        output / "reminders.ics",
        doc.get("entries") or [],
        batch_name=output.name,
        alarm_minutes=alarm_minutes,
        timezone=qh.get("timezone"),
    )
    typer.echo(f"Wrote {output / 'reminders.ics'}")


@app.command("broadcast-due")
def broadcast_due(
    output: Path = typer.Option(..., "--output", "-o"),
    rpc_url: str = typer.Option("http://127.0.0.1:8332", "--rpc-url"),
    rpc_cookie_file: Optional[Path] = typer.Option(
        Path("~/.bitcoin/.cookie"), "--rpc-cookie-file"
    ),
    rpc_user: Optional[str] = typer.Option(None, "--rpc-user"),
    rpc_password: Optional[str] = typer.Option(None, "--rpc-password"),
    max_count: int = typer.Option(1, "--max-count"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    skip_failed: bool = typer.Option(False, "--skip-failed"),
) -> None:
    """Broadcast due signed PSBTs via local Bitcoin Core (localhost RPC only)."""
    typer.echo(FEE_URGENCY_BANNER, err=True)
    try:
        if rpc_user and rpc_password:
            rpc = CoreRpcClient(rpc_url, user=rpc_user, password=rpc_password)
        else:
            rpc = CoreRpcClient(
                rpc_url,
                cookie_file=rpc_cookie_file.expanduser() if rpc_cookie_file else None,
            )
    except ValueError as e:
        typer.echo(f"ERROR: {e}", err=True)
        raise typer.Exit(1) from e
    results = run_broadcast_due(
        output,
        rpc,
        max_count=max_count,
        dry_run=dry_run,
        skip_failed=skip_failed,
    )
    if not results:
        typer.echo("No due entries to broadcast.")
        return
    for r in results:
        typer.echo(f"[{r.action}] order {r.order} {r.label}: {r.txid or r.detail}")


@app.command()
def remind(
    output: Path = typer.Option(..., "--output", "-o"),
) -> None:
    """Print next broadcast reminder (respects quiet hours for manual mode)."""
    sched_path = output / "schedule.yaml"
    if not sched_path.is_file():
        typer.echo(f"Missing {sched_path}", err=True)
        raise typer.Exit(1)
    typer.echo(compute_remind_status(output).message)


@app.command()
def wipe() -> None:
    """Secure-delete RAM workspace."""
    wipe_workspace()
    typer.echo("Workspace wiped.")


if __name__ == "__main__":
    app()
