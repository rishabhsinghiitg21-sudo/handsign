#!/usr/bin/env bash
# Convenience launcher: runs the handsign CLI inside the in-repo .venv.
#   ./handsign.sh console          web console on http://127.0.0.1:8000
#   ./handsign.sh run --dry-run    command-line runner (opens the camera itself)
#   ./handsign.sh list
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYBIN="$HERE/.venv/bin/python"
if [ ! -x "$PYBIN" ]; then
  echo "No .venv found. Run ./setup.sh first." >&2
  exit 1
fi
cd "$HERE"
exec "$PYBIN" -m handsign "$@"
