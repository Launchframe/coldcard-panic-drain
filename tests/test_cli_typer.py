"""CLI registration tests."""

from typer.main import get_command

from coldcard_panic_drain.cli import app


def test_typer_registers_plan_without_annotation_name_error():
    """plan/broadcast-due use Optional[...] annotations; typer evaluates them at import."""
    command = get_command(app)
    assert "plan" in command.commands
    assert "broadcast-due" in command.commands
