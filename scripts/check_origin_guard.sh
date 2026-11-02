#!/usr/bin/env bash
# Starts the console on a spare port and checks that a foreign web page cannot reach it.
# Needs curl and a finished ./setup.sh. Exits non-zero on any failed check.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8765}"
BASE="http://127.0.0.1:$PORT"
"$HERE/.venv/bin/python" -m handsign console --port "$PORT" >/tmp/handsign-guard.log 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null' EXIT
for _ in $(seq 1 60); do curl -fs "$BASE/healthz" >/dev/null 2>&1 && break; sleep 1; done

fail=0
check() {  # description expected actual
  if [ "$2" = "$3" ]; then echo "ok    $1 -> $3"; else echo "FAIL  $1 -> $3 (wanted $2)"; fail=1; fi
}
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

check "GET  no Origin (curl)"            200 "$(code "$BASE/api/status")"
check "GET  own console origin"          200 "$(code -H "Origin: $BASE" "$BASE/api/status")"
check "GET  Vite dev origin"             200 "$(code -H "Origin: http://localhost:5173" "$BASE/api/status")"
check "GET  foreign origin"              403 "$(code -H "Origin: https://evil.example" "$BASE/api/status")"
check "PUT  foreign origin (config)"     403 "$(code -X PUT -H "Origin: https://evil.example" -H 'Content-Type: application/json' -d '{"poses":{"fist":{"action":{"type":"shell","value":"touch /tmp/pwned"}}}}' "$BASE/api/config")"
check "POST foreign origin (workflow)"   403 "$(code -X POST -H "Origin: https://evil.example" "$BASE/api/workflow/screenshot/trigger")"
check "GET  null origin (sandboxed page)" 403 "$(code -H "Origin: null" "$BASE/api/status")"
check "GET  rebinding Host header"       403 "$(code -H "Host: evil.example:$PORT" "$BASE/api/status")"
ws() { curl -s -o /dev/null -w '%{http_code}' --max-time 5 -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
        -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' "$@"; }
check "WS   foreign origin"              403 "$(ws -H "Origin: https://evil.example" "$BASE/ws/live")"
check "WS   own origin (handshake)"      101 "$(ws -H "Origin: $BASE" "$BASE/ws/live")"
[ -e /tmp/pwned ] && { echo "FAIL  /tmp/pwned exists"; fail=1; }
exit $fail
