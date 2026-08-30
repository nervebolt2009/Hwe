# Wearsic Server

Standalone Ktor + NewPipe Extractor backend for the Wearsic Wear OS app. This project is intentionally separate from the Android app and can run on an old Android phone through Termux.

## Requirements

- Java 17
- Termux packages: `pkg install -y openjdk-17 curl unzip`
- A Cloudflare Tunnel pointed at the server port

## Build and run

### From the ready-made Termux ZIP (`wearsic-server-termux-FIXED.zip`)

1. Install Termux packages:
   ```bash
   pkg update -y && pkg upgrade -y
   pkg install -y openjdk-17 curl unzip
   java -version
   ```
2. Allow storage access once:
   ```bash
   termux-setup-storage
   ```
3. Copy the fixed ZIP from Downloads and extract it:
   ```bash
   cp ~/storage/downloads/wearsic-server-termux-FIXED.zip ~/
   cd ~
   unzip -o wearsic-server-termux-FIXED.zip
   ```
4. Start the auto-healing supervisor:
   ```bash
   cd ~/wearsic-server
   chmod +x run-termux.sh bin/wearsic-server
   ./run-termux.sh
   ```

The ZIP is self-contained: `run-termux.sh` sits next to `bin/` and `lib/` and launches the server with a small heap. Your favorites/playlists are stored in `wearsic.db` next to the script — keep a copy of an old `wearsic.db` if you want to carry data over.

`run-termux.sh` uses a small heap and Serial GC by default. Override `JAVA_OPTS` when the phone has more memory.

## Environment

- `PORT` — defaults to `8080`
- `WEARSIC_DB_PATH` — defaults to `wearsic.db`
- `WEARSIC_API_KEY` — optional. If set, every `/api/*` request must include `X-Wearsic-Key`; `/health` remains public.
- `WEARSIC_YOUTUBE_COOKIE` — optional browser cookie string fallback. Required when YouTube returns `Sign in to confirm that you're not a bot` for the server IP. Keep it private and export it only at runtime. The watch app can also push a cookie at runtime (see below).

## API

Public:

- `GET /health`

Authenticated when `WEARSIC_API_KEY` is set:

- `GET /api/search?q=` — maximum 10 results
- `GET /api/suggestions?q=` — maximum 5 suggestions
- `GET /api/related/{videoId}` — maximum 10 results
- `GET /api/stream/{videoId}` — proxied audio with Range forwarding; the FIXED release prefers WebM/Opus near 70 kbps
- `GET|POST|DELETE /api/favorites[/{videoId}]`
- `GET|POST /api/playlists`
- `GET /api/playlists/{id}`
- `POST|DELETE /api/playlists/{id}/tracks[/{videoId}]`
- `GET /api/playlist?url=` — maximum 10 tracks
- `GET /api/channel?url=` — maximum 10 tracks from the first channel tab
- `GET /api/config/youtube-cookie` — returns `{"configured": true|false}`
- `POST /api/config/youtube-cookie` — body `{"cookie": "SID=...; HSID=..."}`; saves the cookie in SQLite and applies it to every YouTube request immediately. Send `{"cookie":""}` to clear it.

The server caches search results and resolved stream targets in small bounded in-memory caches. SQLite uses WAL mode and `synchronous=NORMAL` for good performance on a phone.

Stream extraction is resilient:

- If the default YouTube client fails (bot check, throttling, player/API changes), the server automatically retries the extraction with the **iOS Innertube client** before reporting an error.
- NewPipe failures map to clean JSON errors instead of empty 500 responses: `404` when a video is unavailable, `503` for bot/ReCaptcha challenges (with a hint to configure the YouTube cookie), and `502` for other extraction failures.

## Cloudflare Tunnel

Keep the tunnel URL out of source code. In the watch app Settings screen, enter the public HTTPS URL, for example:

```text
https://your-tunnel.trycloudflare.com
```

The Android client sends `X-Wearsic-Key` centrally on API, stream, cache, and download requests when an API key is configured.

The packaged `run-termux.sh` is a foreground auto-healing supervisor: it checks
`/health` every 30 seconds, retries failures, restarts crashed or unhealthy
servers, rotates logs near 2 MB, uses a PID file, and shuts down the child
cleanly on `Ctrl+C`. See `TERMUX_SERVER_GUIDE.md` for setup and Termux:Boot
instructions.
