"""Block accidental reads of real Sparrow wallet files outside test fixtures.

Agents debugging this repo must not invoke H2 against user wallet paths and paste
query output into the agent router. The CLI opts in explicitly when the user runs
plan/generate; tests disable the guard via conftest.
"""

from __future__ import annotations

import os
from pathlib import Path

REAL_WALLET_ENV = "COLDCARD_PANIC_DRAIN_ALLOW_REAL_WALLET"

_GUARD_ENABLED = True
_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_ROOT = _REPO_ROOT / "tests" / "fixtures"


class RealWalletBlockedError(RuntimeError):
    """Raised when code attempts to read a non-fixture Sparrow .mv.db."""


def _is_fixture_wallet(path: Path) -> bool:
    resolved = path.resolve()
    if not _FIXTURE_ROOT.is_dir():
        return False
    try:
        resolved.relative_to(_FIXTURE_ROOT.resolve())
    except ValueError:
        return False
    return resolved.suffix == ".db" or resolved.name.endswith(".mv.db")


def _real_wallet_allowed() -> bool:
    return os.environ.get(REAL_WALLET_ENV) == "1"


def assert_wallet_path_allowed(wallet_path: Path) -> None:
    """Refuse H2 reads unless path is under tests/fixtures or CLI opted in."""
    if not _GUARD_ENABLED:
        return
    path = Path(wallet_path)
    if _is_fixture_wallet(path):
        return
    if _real_wallet_allowed():
        return
    raise RealWalletBlockedError(
        f"Refusing to read Sparrow wallet {path.name!r} outside tests/fixtures. "
        f"Run via `coldcard-panic-drain plan` / `generate` for real wallets, or set "
        f"{REAL_WALLET_ENV}=1 locally (never for agent debugging). "
        "See AGENTS.md — do not query real .mv.db files or paste H2 output to the agent router."
    )


def enable_cli_wallet_access() -> None:
    """Called from the Typer CLI entry so user-invoked drains can load real wallets."""
    os.environ[REAL_WALLET_ENV] = "1"


def disable_wallet_path_guard() -> None:
    """Disable the guard (unit tests only)."""
    global _GUARD_ENABLED
    _GUARD_ENABLED = False


def enable_wallet_path_guard() -> None:
    """Re-enable the guard after tests."""
    global _GUARD_ENABLED
    _GUARD_ENABLED = True
