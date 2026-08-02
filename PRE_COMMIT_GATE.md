# PRE_COMMIT_GATE.md

Qualitative checks and ordered commands to run before every commit or push in this repository.

## Qualitative rules

- Preserve the zero-network contract (`network_guard.py` must stay enabled in production paths).
- Do not commit wallet artifacts: `.mv.db`, drain output dirs, PSBTs, or real `labels-session.json`.
- Tests must use synthetic keys from `tests/conftest.py` only.
- Do not commit `.cursor/real-steel/` run logs.

## Gates

Run from the repository root with the project venv activated (`pip install -e ".[dev]"`).

### 1. Tests

```bash
pytest -q
```

All tests must pass on current `HEAD`.
