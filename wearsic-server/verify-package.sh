#!/usr/bin/env bash
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
BIN="$SCRIPT_DIR/bin/wearsic-server"
LIB="$SCRIPT_DIR/lib"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[ -f "$SCRIPT_DIR/run-termux.sh" ] || fail "missing run-termux.sh"
[ -x "$SCRIPT_DIR/run-termux.sh" ] || fail "run-termux.sh is not executable; run chmod +x run-termux.sh"
[ -f "$BIN" ] || fail "missing bin/wearsic-server"
[ -x "$BIN" ] || fail "bin/wearsic-server is not executable; run chmod +x bin/wearsic-server"
[ -d "$LIB" ] || fail "missing lib directory"
[ -f "$LIB/wearsic-server-1.0.0.jar" ] || fail "missing server JAR"

command -v java >/dev/null 2>&1 || fail "Java is missing; install with pkg install -y openjdk-17"
command -v unzip >/dev/null 2>&1 || fail "unzip is missing; install with pkg install -y unzip"

java_major=$(java -version 2>&1 | sed -n '1s/.*version "\([0-9][0-9]*\).*/\1/p')
[ -n "$java_major" ] || fail "could not determine Java version"
[ "$java_major" -ge 17 ] || fail "Java 17 or newer is required; found Java $java_major"

classpath=$(sed -n 's/^CLASSPATH=\(.*\)$/\1/p' "$BIN" | head -1)
[ -n "$classpath" ] || fail "could not read launcher classpath"

old_ifs=$IFS
IFS=:
for jar in $classpath; do
  jar_path=${jar#\$APP_HOME/}
  case "$jar_path" in
    lib/*) [ -f "$LIB/${jar_path#lib/}" ] || fail "launcher references missing $jar_path" ;;
  esac
done
IFS=$old_ifs

printf 'Package OK\n'
printf '  Java: %s\n' "$(java -version 2>&1 | head -1)"
printf '  Server JAR: %s bytes\n' "$(wc -c < "$LIB/wearsic-server-1.0.0.jar")"
printf '  Files: %s\n' "$(find "$LIB" -maxdepth 1 -type f | wc -l) dependency JARs"
