"""Secure temp workspace cleanup."""

from __future__ import annotations

import atexit
import os
import shutil
import signal
import tempfile
from pathlib import Path
from typing import Optional

_TEMP_DIR: Optional[Path] = None


def init_ram_workspace() -> Path:
    global _TEMP_DIR
    if _TEMP_DIR is not None:
        return _TEMP_DIR
    _TEMP_DIR = Path(tempfile.mkdtemp(prefix="coldcard-panic-drain-"))
    os.environ["TMPDIR"] = str(_TEMP_DIR)
    atexit.register(wipe_workspace)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _signal_handler)
        except (ValueError, OSError):
            pass
    return _TEMP_DIR


def _signal_handler(signum, frame) -> None:  # noqa: ARG001
    wipe_workspace()
    raise SystemExit(128 + signum)


def wipe_workspace() -> None:
    global _TEMP_DIR
    if _TEMP_DIR and _TEMP_DIR.exists():
        shutil.rmtree(_TEMP_DIR, ignore_errors=True)
    _TEMP_DIR = None
