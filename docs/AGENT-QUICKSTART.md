# Agent quickstart

**Read [AGENTS.md](../AGENTS.md) first** before any other work in this repository.

## Privacy (summary)

- Allowed over the wire: user questions, **file paths**, and **source code** / synthetic fixtures.
- Never transmit: wallet DB contents, addresses, txids, amounts, labels, xpubs, seeds, PSBTs, or real drain outputs.
- Prefer paths and redacted error codes over pasting CLI output from real wallets.

## Local gate

```bash
source .venv/bin/activate
pytest -q
# or
bash scripts/verify-env.sh
```

Report exit codes and test counts only — not wallet fields.

## Roadmap / docs

- Platform install: [docs/runbooks/](runbooks/)
- Product FAQs: [FAQS.md](../FAQS.md)
- If `docs/issues/` is present on the branch you are on, use it for enhancement specs; otherwise track work via GitHub issues.
