#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"
ENV_FILE="${WEARSIC_ENV_FILE:-$ROOT/.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

: "${PORT:=8081}"
: "${WEARSIC_RESTART_DELAY_SECONDS:=5}"
: "${WEARSIC_MAX_RESTART_DELAY_SECONDS:=300}"
: "${WEARSIC_LOG_FILE:=$ROOT/server.log}"
: "${WEARSIC_PYTHON:=python}"
export PORT

command -v "$WEARSIC_PYTHON" >/dev/null || { echo "Python is required: pkg install python" >&2; exit 1; }
command -v curl >/dev/null || { echo "curl is required: pkg install curl" >&2; exit 1; }

if [[ ! -d "$ROOT/.venv" ]]; then
  "$WEARSIC_PYTHON" -m venv "$ROOT/.venv"
fi
PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Virtual environment creation failed" >&2
  exit 1
fi
if [[ "${WEARSIC_SKIP_INSTALL:-0}" != 1 ]]; then
  "$PYTHON" -m pip install --disable-pip-version-check -q -r requirements.txt
fi

termux-wake-lock 2>/dev/null || true
child=""
stop() {
  trap - TERM INT EXIT
  if [[ -n "$child" ]] && kill -0 "$child" 2>/dev/null; then
    kill -TERM "$child" 2>/dev/null || true
    wait "$child" 2>/dev/null || true
  fi
  termux-wake-unlock 2>/dev/null || true
}
trap stop TERM INT EXIT

delay="$WEARSIC_RESTART_DELAY_SECONDS"
while true; do
  echo "$(date -Is) starting Wearsic Server V2 on :$PORT" >> "$WEARSIC_LOG_FILE"
  "$PYTHON" -m uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "$PORT" >> "$WEARSIC_LOG_FILE" 2>&1 &
  child=$!
  healthy=0
  for _ in {1..30}; do
    if curl -fsS --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null; then healthy=1; break; fi
    kill -0 "$child" 2>/dev/null || break
    sleep 1
  done
  if (( healthy == 0 )); then
    echo "$(date -Is) health check failed" >> "$WEARSIC_LOG_FILE"
  fi
  wait "$child" || true
  child=""
  echo "$(date -Is) server stopped; restarting in ${delay}s" >> "$WEARSIC_LOG_FILE"
  sleep "$delay"
  (( delay < WEARSIC_MAX_RESTART_DELAY_SECONDS )) && delay=$((delay * 2))
done
