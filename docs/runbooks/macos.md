# macOS runbook

Primary development target (Apple Silicon and Intel).

## Install dependencies

```bash
brew install python@3.12 openjdk@17
```

Ensure `java` is on `PATH` (Homebrew prints caveats for OpenJDK). Confirm:

```bash
python3.12 --version   # ≥ 3.11
java -version          # 11+ (17 LTS recommended)
```

## Project setup

```bash
cd coldcard-panic-drain
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
bash scripts/verify-env.sh
```

H2 JARs ship under `vendor/` — do not download them at drain time.

## Sparrow wallet paths

```text
~/.sparrow/wallets/*.mv.db
```

Sync the wallet in Sparrow before copying the `.mv.db` for offline use.

## microSD / output paths

Typical removable volume mount:

```text
/Volumes/<NAME>/
```

Grant Full Disk Access if macOS blocks reads/writes to the card. Remount read-write if the volume is read-only.

## Next steps

- Dry-run with `plan` before `generate` — see [README.md](../../README.md).
- Read [DISCLAIMER.md](../../DISCLAIMER.md).
