# Wearsic Server Termux Guide

This guide covers both server editions:

- **V1 (`wearsic-server/`)** — the original compiled Ktor server containing the NewPipe Extractor.
- **V2 (`wearsic-server-v2/`)** — a source-based FastAPI gateway that keeps V1 as the primary provider and uses yt-dlp as a backup.

For failover, run both services on the phone and configure the watch to use **V2 only**.

```text
Wear OS app
    │ HTTP + X-Wearsic-Key
    ▼
V2 gateway :8081
    ├── normal requests → V1/NewPipe :8080
    └── repeated primary failures → yt-dlp backup
```

The app never switches ports. V2 performs the provider switch internally. Existing streams cannot be migrated mid-playback; a new request or retry is routed using the current provider.

## 1. Install Termux

Install Termux from F-Droid. Avoid the obsolete Play Store build:

<https://f-droid.org/en/packages/com.termux/>

Then install the required tools:

```bash
pkg update -y && pkg upgrade -y
pkg install -y git python curl unzip ffmpeg
termux-setup-storage
python --version
```

Python 3.11 or newer is recommended. Keep Termux battery usage set to **Unrestricted** in Android settings.

## 2. Download V2

Download the `wearsic-server-v2.zip` asset from the repository's Releases page, or clone the repository:

```bash
cd ~
git clone https://github.com/nervebolt2009/Hwe.git wearsic-source
cp ~/storage/downloads/wearsic-server-v2.zip ~/
unzip -o ~/wearsic-server-v2.zip -d ~/
```

If cloning instead of using the release archive:

```bash
cp -r ~/wearsic-source/wearsic-server-v2 ~/wearsic-server-v2
```

The V2 directory must contain `app/`, `requirements.txt`, `.env.example`, `run-termux.sh`, and `README.md`.

## 3. Install the original NewPipe server (V1)

Download `wearsic-server-termux-FIXED.zip` from the same release and extract it:

```bash
unzip -o ~/wearsic-server-termux-FIXED.zip -d ~/
cd ~/wearsic-server
chmod +x run-termux.sh bin/wearsic-server
```

V1 runs on port `8080` by default and contains the NewPipe Extractor. V2 cannot replace this component; it calls V1 over localhost.

## 4. Configure both servers

Create a shared API key. A random key can be generated with:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Configure V1:

```bash
cd ~/wearsic-server
touch .env
sed -i '/^WEARSIC_API_KEY=/d' .env
printf '%s\n' 'PORT=8080' >> .env
printf '%s\n' 'WEARSIC_API_KEY=PASTE_THE_SAME_KEY_HERE' >> .env
chmod 600 .env
```

Configure V2:

```bash
cd ~/wearsic-server-v2
cp .env.example .env
sed -i 's|^WEARSIC_API_KEY=.*|WEARSIC_API_KEY=PASTE_THE_SAME_KEY_HERE|' .env
sed -i 's|^WEARSIC_PRIMARY_URL=.*|WEARSIC_PRIMARY_URL=http://127.0.0.1:8080|' .env
chmod 600 .env
```

V2's important defaults are:

```text
V1/NewPipe primary: 127.0.0.1:8080
V2 gateway:         0.0.0.0:8081
Failure threshold:  3 consecutive failures
Recovery threshold: 3 successful primary probes
yt-dlp concurrency: 2 processes maximum
```

Never commit or share either `.env` file.

## 5. Start the services

Start V1 first in one Termux session:

```bash
cd ~/wearsic-server
./run-termux.sh
```

Verify it:

```bash
curl --fail --max-time 10 http://127.0.0.1:8080/health
```

Start V2 in another Termux session:

```bash
cd ~/wearsic-server-v2
chmod +x run-termux.sh
./run-termux.sh
```

The V2 launcher creates `.venv`, installs pinned Python dependencies, starts uvicorn, checks `/health`, and restarts the process after crashes. Set `WEARSIC_SKIP_INSTALL=1` in `.env` after the first successful installation to avoid checking packages on every restart.

## 6. Verify V2 and failover

Check V2 health:

```bash
curl --fail http://127.0.0.1:8081/health
```

Expected normal state:

```json
{"status":"ok","version":"2.0.0","serverName":"Wearsic Engine V2","engine":"primary","healing":false}
```

Test an authenticated search:

```bash
curl --fail --max-time 30 \
  -H 'X-Wearsic-Key: PASTE_THE_SAME_KEY_HERE' \
  --get --data-urlencode 'q=crowded house' \
  http://127.0.0.1:8081/api/search
```

When V1 fails three consecutive provider requests, V2 reports `engine: "ytdlp"` and routes new extraction requests through yt-dlp. V2 probes V1 before failing back; it requires the configured recovery threshold, preventing rapid flapping.

The backup requires yt-dlp to be installed and available. The Python requirements install the `yt-dlp` package into V2's virtual environment. Test it directly if needed:

```bash
~/wearsic-server-v2/.venv/bin/yt-dlp --version
```

## 7. Configure the watch

Set the server URL in the Android app to **V2's port 8081**.

For same Wi-Fi, find the phone address:

```bash
ip -4 addr show wlan0
```

Use the `inet` address, for example:

```text
http://192.168.1.42:8081
```

The watch and phone must be on the same network. For Tailscale, use the phone's `tun0` address and still use port `8081`:

```bash
ip -4 addr show tun0
# http://100.x.y.z:8081
```

Configure the same API key in the app. Do not expose port 8080 publicly; only V2 should be reachable from the watch.

## 8. Automatic startup after reboot

Install Termux:Boot from F-Droid. Then:

```bash
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/start-wearsic.sh <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
cd "$HOME/wearsic-server"
./run-termux.sh >> "$HOME/wearsic-v1-boot.log" 2>&1 &
sleep 5
cd "$HOME/wearsic-server-v2"
exec ./run-termux.sh >> "$HOME/wearsic-v2-boot.log" 2>&1
EOF
chmod +x ~/.termux/boot/start-wearsic.sh
```

V1 is started first, then V2 after a short delay. Both launchers are foreground supervisors; the boot script backgrounds V1 and keeps V2 attached to the boot job.

## 9. Logs, data, and backups

V1:

```bash
tail -f ~/wearsic-server/wearsic-server.log
```

V2:

```bash
tail -f ~/wearsic-server-v2/server.log
```

V2 data is stored in `wearsic-server-v2.db` unless `WEARSIC_DB_PATH` is changed. Back up the database and secrets:

```bash
cp ~/wearsic-server-v2/wearsic-server-v2.db ~/wearsic-server-v2/wearsic-server-v2.db.backup
cp ~/wearsic-server-v2/.env ~/wearsic-server-v2/.env.backup
chmod 600 ~/wearsic-server-v2/.env.backup
```

## 10. Troubleshooting

### V2 says primary is unavailable

Check V1 first:

```bash
curl -v http://127.0.0.1:8080/health
ps -ef | grep -E 'wearsic|uvicorn' | grep -v grep
```

### V2 backup does not work

Check yt-dlp and network access:

```bash
~/wearsic-server-v2/.venv/bin/yt-dlp --version
~/wearsic-server-v2/.venv/bin/yt-dlp --no-playlist --get-title 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
```

### HTTP 401

The app, V1, and V2 must use the exact same `WEARSIC_API_KEY`. The header name is:

```text
X-Wearsic-Key
```

### Repeated restarts

Inspect both logs, check storage, and check ports:

```bash
df -h ~
tail -200 ~/wearsic-server/wearsic-server.log
tail -200 ~/wearsic-server-v2/server.log
```

### Port conflict

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8081/health
```

Run only one supervisor for each port.

## Reliability notes

V2 provides request-level failover, bounded yt-dlp concurrency, timeouts, caching, hysteresis, and process restart supervision. It cannot guarantee YouTube availability, migrate an already-open stream, or prove that a provider's returned media URL will remain valid after resolution. Test the complete setup on the target phone before depending on it.
