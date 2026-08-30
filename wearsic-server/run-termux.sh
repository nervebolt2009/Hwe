#!/data/data/com.termux/files/usr/bin/bash
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/wearsic-server.log"
PID_FILE="$SCRIPT_DIR/wearsic-server.pid"
PORT="${PORT:-8080}"
HEALTH_INTERVAL="${WEARSIC_HEALTH_INTERVAL:-30}"
HEALTH_TIMEOUT="${WEARSIC_HEALTH_TIMEOUT:-10}"
MAX_LOG_BYTES=$((2 * 1024 * 1024))

log() {
  printf '[wearsic %s] %s\n' "$(date '+%H:%M:%S')" "$*" | tee -a "$LOG_FILE"
}

fail() {
  log "ERROR: $*"
  exit 1
}

rotate_log() {
  if [ -f "$LOG_FILE" ]; then
    log_size=$(wc -c < "$LOG_FILE" 2>/dev/null || printf '0')
    if [ "$log_size" -ge "$MAX_LOG_BYTES" ]; then
      mv -f "$LOG_FILE" "$LOG_FILE.1"
      : > "$LOG_FILE"
      log "rotated server log"
    fi
  fi
}

find_app() {
  if [ -x "$SCRIPT_DIR/bin/wearsic-server" ]; then
    printf '%s\n' "$SCRIPT_DIR/bin/wearsic-server"
  elif [ -x "$SCRIPT_DIR/build/install/wearsic-server/bin/wearsic-server" ]; then
    printf '%s\n' "$SCRIPT_DIR/build/install/wearsic-server/bin/wearsic-server"
  else
    return 1
  fi
}

APP=$(find_app) || fail "Missing wearsic-server binary. Extract the complete package so bin/ and lib/ are next to this script."

if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$SCRIPT_DIR/.env"
  set +a
fi

PORT="${PORT:-8080}"
export PORT
export WEARSIC_DB_PATH="${WEARSIC_DB_PATH:-$SCRIPT_DIR/wearsic.db}"
export JAVA_OPTS="${JAVA_OPTS:--Xms32m -Xmx192m -XX:+UseSerialGC -XX:TieredStopAtLevel=1}"

command -v java >/dev/null 2>&1 || fail "Java is not installed. Run: pkg install -y openjdk-17"
command -v curl >/dev/null 2>&1 || fail "curl is not installed. Run: pkg install -y curl"
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock && log "wake lock acquired"

if [ -f "$PID_FILE" ]; then
  old_pid=$(cat "$PID_FILE" 2>/dev/null || true)
  if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
    fail "Supervisor already running with PID $old_pid"
  fi
  rm -f "$PID_FILE"
fi

touch "$LOG_FILE"
SUPERVISOR_PID=$$
printf '%s\n' "$SUPERVISOR_PID" > "$PID_FILE"

server_pid=""
stop_requested=0

cleanup() {
  stop_requested=1
  if [ -n "$server_pid" ] && kill -0 "$server_pid" 2>/dev/null; then
    log "stopping server (pid $server_pid)"
    kill "$server_pid" 2>/dev/null || true
    sleep 2
    kill -9 "$server_pid" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
  command -v termux-wake-unlock >/dev/null 2>&1 && termux-wake-unlock || true
  log "supervisor stopped"
}
trap cleanup INT TERM EXIT

start_server() {
  rotate_log
  log "starting server on port $PORT"
  (
    cd "$SCRIPT_DIR" || exit 1
    exec "$APP"
  ) >> "$LOG_FILE" 2>&1 &
  server_pid=$!
  log "server started (pid $server_pid)"
}

stop_server() {
  if [ -n "$server_pid" ] && kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  server_pid=""
}

health_ok() {
  curl -fsS --max-time "$HEALTH_TIMEOUT" "http://127.0.0.1:$PORT/health" >/dev/null 2>&1
}

log "auto-heal supervisor starting (health checks every ${HEALTH_INTERVAL}s)"

restart_count=0
while [ "$stop_requested" -eq 0 ]; do
  start_server
  sleep 3

  while [ "$stop_requested" -eq 0 ]; do
    if ! kill -0 "$server_pid" 2>/dev/null; then
      wait "$server_pid" 2>/dev/null || true
      log "server exited unexpectedly; restarting"
      server_pid=""
      restart_count=$((restart_count + 1))
      sleep $((restart_count < 10 ? restart_count : 10))
      break
    fi

    if ! health_ok; then
      log "health check failed; allowing 3 retries before restart"
      unhealthy=1
      retry=1
      while [ "$retry" -le 3 ] && [ "$stop_requested" -eq 0 ]; do
        sleep 5
        if health_ok; then
          unhealthy=0
          log "health check recovered"
          break
        fi
        retry=$((retry + 1))
      done
      if [ "$unhealthy" -eq 1 ]; then
        log "server unhealthy; restarting"
        stop_server
        restart_count=$((restart_count + 1))
        sleep $((restart_count < 10 ? restart_count : 10))
        break
      fi
    else
      restart_count=0
    fi

    rotate_log
    sleep "$HEALTH_INTERVAL"
  done
done
