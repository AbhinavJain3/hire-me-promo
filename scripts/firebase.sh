#!/usr/bin/env bash
# Run the project-local Firebase CLI (installed in .venv/node) with the project-local Java 21 (.venv/jdk).
# Nothing is installed system-wide (D-085). Examples:
#   scripts/firebase.sh emulators:start --only firestore --project demo-hireme-engage-dev
#   scripts/firebase.sh emulators:exec --only firestore --project demo-hireme-engage-dev ".venv/bin/python -m pytest tests"
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAVA_DIR="$(ls -d "$ROOT"/.venv/jdk/*/ 2>/dev/null | head -1)"
if [[ -z "$JAVA_DIR" || ! -x "$ROOT/.venv/node/node_modules/.bin/firebase" ]]; then
  echo "Missing .venv/jdk or .venv/node; see README 'Firestore emulator' to install." >&2
  exit 1
fi
export JAVA_HOME="${JAVA_DIR%/}"
export PATH="$JAVA_HOME/bin:$ROOT/.venv/node/node_modules/.bin:$PATH"
cd "$ROOT"
exec firebase "$@"
