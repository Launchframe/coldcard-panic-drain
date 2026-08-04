# macOS runbook

Primary development target (Apple Silicon and Intel).

## Install dependencies

```bash
brew install python@3.12 openjdk@17
```

Homebrew’s `python@3.12` formula is a common way to get a supported interpreter; any
Python ≥ 3.11 works. Ensure `java` is on `PATH` (Homebrew prints caveats for OpenJDK).
Confirm:

```bash
python3 --version   # must be ≥ 3.11
java -version       # 11+ (17 LTS recommended)
```

If `python3` is still the macOS stub or older than 3.11, use the Homebrew binary
(`python3.12` or the path `brew --prefix python@3.12` prints) for the checks and venv below.

## Project setup

```bash
cd coldcard-panic-drain
python3 -m venv .venv
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
