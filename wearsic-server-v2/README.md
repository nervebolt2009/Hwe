# Wearsic Server V2

Source-based FastAPI gateway for the Wearsic app. The existing `wearsic-server/` package is unchanged.

## Install on Termux

```bash
pkg update -y
pkg install -y python curl
pkg install -y ffmpeg
unzip wearsic-server-v2.zip
cd wearsic-server-v2
cp .env.example .env
chmod 600 .env
# Edit .env and set WEARSIC_API_KEY
./run-termux.sh
```

The launcher creates a local virtual environment, installs pinned dependencies, keeps the service alive after crashes, and exposes the API on port `8081` by default. Set `WEARSIC_SKIP_INSTALL=1` after dependencies are installed to avoid checking PyPI at every start.

## Architecture

- Existing Wearsic server: primary provider at `WEARSIC_PRIMARY_URL`.
- yt-dlp: backup provider, limited by `WEARSIC_MAX_CONCURRENT_EXTRACTIONS`.
- Three consecutive primary failures switch requests to yt-dlp.
- Primary recovery is only promoted after `WEARSIC_RECOVERY_THRESHOLD` successful probes.
- SQLite stores favorites and playlists.
- Resolved responses are cached in memory for `WEARSIC_CACHE_TTL_SECONDS`.

This is process-level failover, not zero-downtime JVM replacement: the primary remains untouched and the V2 gateway routes new requests. Existing stream connections cannot be migrated mid-stream.

## Configuration

See `.env.example`. Never commit `.env`; it contains the API key. The gateway accepts `X-Wearsic-Key` on protected API endpoints. `/health` is intentionally unauthenticated for local supervision.

## Smoke test

```bash
curl -fsS http://127.0.0.1:8081/health
curl -fsS -H "X-Wearsic-Key: $WEARSIC_API_KEY" \
  --get --data-urlencode 'q=test' \
  http://127.0.0.1:8081/api/search
```

## Important limitations

The primary JAR is opaque and the V2 gateway cannot inspect its internal extraction engine. yt-dlp must be installed and available in the environment or configured with `WEARSIC_YTDLP_BIN`. Test real search and streaming before relying on the backup path.
