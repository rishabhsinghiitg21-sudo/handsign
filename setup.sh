#!/usr/bin/env bash
# One-command setup: in-repo .venv, Python deps, web console build, MediaPipe models.
#   ./setup.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

[ "$(uname -s)" = "Darwin" ] || { echo "handsign is macOS-only." >&2; exit 1; }
command -v node >/dev/null && command -v npm >/dev/null || { echo "Node.js 18+ and npm are required (https://nodejs.org)." >&2; exit 1; }
[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 18 ] || { echo "Node.js 18+ is required (found $(node --version))." >&2; exit 1; }

# Prefer Python 3.13 (what it was built on), then newer/older supported ones.
PY=""
for c in python3.13 python3.12 python3.11 python3.14 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "Python 3.11+ is required (the pinned numpy needs it). Try: brew install python@3.13" >&2; exit 1; }
echo "==> Python: $($PY --version) ($PY)"

echo "==> Creating .venv and installing requirements"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "==> Building the web console"
(cd web && npm ci --no-audit --no-fund && npm run build)

echo "==> Downloading models"
bash scripts/download_models.sh

cat <<MSG

Setup done. Start the console with:

  ./handsign.sh console      # then open http://127.0.0.1:8000

Start in Dry-Run (the default) to see what would fire without firing it.
Read the security note in the README before binding shell commands.
MSG
