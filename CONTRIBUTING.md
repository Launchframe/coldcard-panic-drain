# Contributing

Thanks for helping improve coldcard-panic-drain.

## Workflow

1. **Fork** the repository and clone your fork.
2. Create a **feature branch** from `main`.
3. Set up the environment (Python ≥ 3.11, Java on `PATH`, vendored H2 JARs). See [docs/runbooks/](docs/runbooks/) or run `bash scripts/verify-env.sh`.
4. Make a focused change. Prefer small PRs over drive-by refactors.
5. Run tests:

   ```bash
   source .venv/bin/activate
   pytest -q
   ```

6. Open a **pull request** against `main` with a clear description and test plan.

## Privacy — no real wallet data in PRs

This project handles high-sensitivity financial data. **Never** commit or paste into issues/PRs:

- Sparrow `.mv.db` files or query results
- Addresses, txids, outpoints, amounts, labels, xpubs, seeds, or PSBTs
- Real `mapping.csv`, `schedule.yaml`, `manifest.json`, or drain output directories

Use synthetic fixtures under `tests/fixtures/` and generated test keys from `tests/conftest.py` only.

Full agent and contributor privacy rules: **[AGENTS.md](AGENTS.md)**.

## Code expectations

- Match existing module layout (`sparrow/`, `plan/`, `psbt/`, `export/`, `schedule/`, `verify/`).
- Preserve the localhost-only network guard and real-wallet path guard.
- Keep incomplete-drain warnings and the `I UNDERSTAND` gate loud.
- Document user-facing steps in the README or runbooks — not with mainnet examples.
