# Windows runbook

Native Windows is best-effort and untested. **Prefer WSL2 (Ubuntu)** and follow the Linux-oriented steps below.

## Prefer WSL2

1. Install [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install) with Ubuntu.
2. Inside WSL:

   ```bash
   sudo apt update
   sudo apt install python3.12 python3.12-venv default-jre
   ```

3. Clone the repo into the Linux filesystem (not only `/mnt/c/...`) for better performance.
4. Create a venv and install:

   ```bash
   cd coldcard-panic-drain
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   bash scripts/verify-env.sh
   ```

## Sparrow wallet paths (WSL)

Sparrow on Windows typically stores wallets under:

```text
/mnt/c/Users/<user>/AppData/Roaming/Sparrow/wallets/
```

Or copy synced `.mv.db` files into your WSL home before an offline run.

## microSD / output paths (WSL)

Removable drives often appear as:

```text
/mnt/<drive>/
```

Confirm the mount is writable before `--output`.

## Native Windows (unsupported / best-effort)

If you must stay outside WSL:

| Item | Notes |
|------|--------|
| Python | `py -3.12` (Microsoft Store or python.org) ≥ 3.11 |
| Java | [Microsoft Build of OpenJDK 17](https://learn.microsoft.com/en-us/java/openjdk/download) or Temurin; `java` on PATH |
| venv | `py -3.12 -m venv .venv` then `.venv\Scripts\activate` |
| Sparrow wallets | `%APPDATA%\Sparrow\wallets\` |

Git Bash or PowerShell can run the CLI; prefer WSL for parity with CI and Linux docs.

## Next steps

- Dry-run with `plan` before `generate` — see [README.md](../../README.md).
- Read [DISCLAIMER.md](../../DISCLAIMER.md).
