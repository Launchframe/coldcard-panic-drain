"""CLI registration tests."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from typer.main import get_command
from typer.testing import CliRunner

from coldcard_panic_drain.cli import app


def test_typer_registers_plan_without_annotation_name_error():
    """plan/broadcast-due use Optional[...] annotations; typer evaluates them at import."""
    command = get_command(app)
    assert "plan" in command.commands
    assert "broadcast-due" in command.commands


def test_typer_registers_reschedule():
    command = get_command(app)
    assert "reschedule" in command.commands


def _write_synthetic_schedule(output: Path) -> None:
    base = datetime(2020, 1, 1, tzinfo=timezone.utc)
    doc = {
        "generated_at": base.isoformat(),
        "spread_hours": 6.0,
        "schedule_jitter": 0.35,
        "entries": [
            {
                "order": i + 1,
                "label": f"coin-{i}",
                "unsigned": f"psbts/{i}.psbt",
                "signed": f"psbts_signed/{i}-signed.psbt",
                "broadcast_not_before": (base + timedelta(hours=i)).isoformat(),
                "fee_sat_vb": 10,
                "nlocktime": 890_000,
                "utxo_ref": f"ref-{i}",
            }
            for i in range(2)
        ],
    }
    (output / "schedule.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def test_reschedule_dry_run_prints_table_and_writes_no_files(tmp_path: Path):
    _write_synthetic_schedule(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app, ["reschedule", "-o", str(tmp_path), "--spread-hours", "2", "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert "Would reschedule 2 pending" in result.output
    assert "Dry run: no files written." in result.output
    assert not (tmp_path / "broadcast-state.yaml").exists()


def test_reschedule_missing_schedule_file_errors(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(app, ["reschedule", "-o", str(tmp_path), "--spread-hours", "2"])
    assert result.exit_code == 1
