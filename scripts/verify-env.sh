#!/usr/bin/env bash
# Verify local toolchain for coldcard-panic-drain (Python, Java, H2 JARs, deps, tests).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SKIP_TESTS=0
for arg in "$@"; do
  case "$arg" in
    --skip-tests) SKIP_TESTS=1 ;;
    -h|--help)
      echo "Usage: $0 [--skip-tests]"
      echo "  Checks Python >= 3.11, java on PATH, vendor H2 JARs,"
      echo "  pip install -e \".[dev]\", and pytest -q (unless --skip-tests)."
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $arg" >&2
      echo "Usage: $0 [--skip-tests]" >&2
      exit 1
      ;;
  esac
done

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

ok() {
  echo "OK: $*"
}

# Prefer activated venv, then project .venv, then python3/python on PATH.
if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
  PYTHON="${VIRTUAL_ENV}/bin/python"
elif [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON="$(command -v python)"
else
  fail "Python not found on PATH (need >= 3.11)"
fi

PY_VERSION="$("$PYTHON" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
"$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
  || fail "Python ${PY_VERSION} is too old (need >= 3.11). Found: ${PYTHON}"
ok "Python ${PY_VERSION} (${PYTHON})"

command -v java >/dev/null 2>&1 || fail "java not found on PATH (need JRE/JDK 11+)"
JAVA_LINE="$(java -version 2>&1 | head -n 1 || true)"
ok "java on PATH (${JAVA_LINE})"

H2_214="${ROOT}/vendor/h2-2.1.214.jar"
H2_224="${ROOT}/vendor/h2-2.2.224.jar"
[[ -f "$H2_214" ]] || fail "missing ${H2_214}"
[[ -f "$H2_224" ]] || fail "missing ${H2_224}"
ok "vendor H2 JARs present (2.1.214 and 2.2.224)"

echo "Installing package: ${PYTHON} -m pip install -e \".[dev]\""
"$PYTHON" -m pip install -e ".[dev]"
ok "pip install -e \".[dev]\""

if [[ "$SKIP_TESTS" -eq 1 ]]; then
  ok "skipped pytest (--skip-tests)"
else
  echo "Running: ${PYTHON} -m pytest -q"
  "$PYTHON" -m pytest -q
  ok "pytest -q"
fi

echo
echo "Environment verification passed."
exit 0
