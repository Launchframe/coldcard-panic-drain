#!/usr/bin/env bash
# File wallet-support enhancement issues from docs/issues/*.md
# Requires: gh auth with issue-create permission on Launchframe/coldcard-panic-drain
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ISSUES_DIR="$ROOT/docs/issues"
REPO="${GITHUB_REPOSITORY:-Launchframe/coldcard-panic-drain}"

cd "$ROOT"

if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: gh CLI not found" >&2
  exit 1
fi

# Optional label; create if missing (ignore failure if no label permission).
gh label create wallet-support --description "Wallet format / import expansion" --color "1D76DB" 2>/dev/null || true

file_issue() {
  local spec="$1"
  local title
  title="$(sed -n '1s/^# //p' "$spec")"
  if [[ -z "$title" ]]; then
    echo "ERROR: could not parse title from $spec" >&2
    exit 1
  fi
  local body
  body="$(tail -n +2 "$spec")"
  echo "Creating: $title"
  gh issue create \
    --repo "$REPO" \
    --title "$title" \
    --label enhancement \
    --label wallet-support \
    --body "$body"
}

echo "Filing wallet-support issues to $REPO ..."
echo

file_issue "$ISSUES_DIR/electrum-wallet-import.md"
file_issue "$ISSUES_DIR/additional-script-types.md"
file_issue "$ISSUES_DIR/multisig-miniscript.md"
file_issue "$ISSUES_DIR/nunchuk-wallet-import.md"

echo
echo "Done. Update docs/issues/README.md with issue numbers from:"
echo "  gh issue list --label wallet-support --limit 10"
