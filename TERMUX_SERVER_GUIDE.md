# Wearsic Server — Termux Setup Guide

Run the Wearsic backend on an Android phone with Termux and connect a Wear OS
watch over the same Wi-Fi network, Tailscale, or a private HTTPS tunnel.

## 1. Install Termux

Install Termux from F-Droid, not the outdated Play Store build:

<https://f-droid.org/en/packages/com.termux/>

Then update packages:

```bash
pkg update -y && pkg upgrade -y
pkg install -y openjdk-17 curl unzip
java -version
```

Java 17 or newer is required.

## 2. Install the server package

Download `wearsic-server-termux-FIXED.zip` from the GitHub release, then either
copy it to Termux's home directory or copy it from Android shared storage:

```bash
termux-setup-storage
cp ~/storage/downloads/wearsic-server-termux-FIXED.zip ~/
```

Extract it:

```bash
cd ~
unzip -o wearsic-server-termux-FIXED.zip
cd ~/wearsic-server
chmod +x run-termux.sh bin/wearsic-server
```

The extracted directory must contain:

```text
~/wearsic-server/run-termux.sh
~/wearsic-server/bin/wearsic-server
~/wearsic-server/lib/
```

## 3. Configure the server

The defaults are:

- Port: `8080`
- Database: `~/wearsic-server/wearsic.db`
- API key: disabled

For a private server, create or edit `.env` without duplicating entries:

```bash
cd ~/wearsic-server
touch .env
sed -i '/^WEARSIC_API_KEY=/d' .env
printf '%s\n' 'WEARSIC_API_KEY=replace-with-a-long-random-secret' >> .env
chmod 600 .env
```

Optional settings:

```bash
printf '%s\n' 'PORT=8080' >> .env
printf '%s\n' 'WEARSIC_DB_PATH=/data/data/com.termux/files/home/wearsic-server/wearsic.db' >> .env
```

Do not share `.env`; it contains the API key.

## 4. Start the auto-healing server

Run this in a Termux session and leave the session alive:

```bash
cd ~/wearsic-server
./run-termux.sh
```

The supervisor now:

- acquires a Termux wake lock when available;
- starts the server;
- checks `http://127.0.0.1:8080/health` every 30 seconds;
- retries failed health checks three times;
- restarts the server after a crash or approximately 45 seconds of failure;
- applies a bounded restart backoff;
- rotates `wearsic-server.log` at approximately 2 MB;
- writes its PID to `wearsic-server.pid`;
- shuts down the child server cleanly on `Ctrl+C`.

Expected output includes:

```text
[wearsic HH:MM:SS] wake lock acquired
[wearsic HH:MM:SS] auto-heal supervisor starting (health checks every 30s)
[wearsic HH:MM:SS] starting server on port 8080
[wearsic HH:MM:SS] server started (pid XXXX)
```

The supervisor is intentionally foreground-based. Do not run multiple copies.
If one is already running, the script refuses to start a second supervisor.

## 5. Verify locally

Open a second Termux session:

```bash
curl --fail --max-time 10 http://127.0.0.1:8080/health
```

Expected response:

```json
{"status":"ok","version":"1.0.0","serverName":"Wearsic Engine"}
```

Test search:

```bash
curl --fail --max-time 30 'http://127.0.0.1:8080/api/search?q=crowded%20house'
```

If an API key is configured, include it:

```bash
curl --fail --max-time 30 \
  -H 'X-Wearsic-Key: replace-with-a-long-random-secret' \
  'http://127.0.0.1:8080/api/search?q=crowded%20house'
```

## 6. Connect the watch

### Same Wi-Fi

Find the phone's Wi-Fi address:

```bash
ip -4 addr show wlan0
```

Use the `inet` address, for example `192.168.1.42`, then set this in Wearsic:

```text
http://192.168.1.42:8080
```

Both devices must be on the same network, and the network must allow device-to-
device traffic.

### Tailscale

Install Tailscale on both devices, then find the phone's Tailscale address:

```bash
ip -4 addr show tun0
```

Set the watch server URL to:

```text
http://100.x.y.z:8080
```

Use an API key even on Tailscale.

### Public HTTPS tunnel

Use a private HTTPS tunnel pointing to `http://127.0.0.1:8080`. Set the watch
URL to the HTTPS hostname and always configure `WEARSIC_API_KEY`.

Do not expose an open Wearsic server to the public internet.

## 7. Useful commands

```bash
# Start / auto-heal
cd ~/wearsic-server && ./run-termux.sh

# Health check
curl --fail http://127.0.0.1:8080/health

# Follow logs
tail -f ~/wearsic-server/wearsic-server.log

# Check supervisor PID
cat ~/wearsic-server/wearsic-server.pid

# Stop cleanly
# Press Ctrl+C in the supervisor's Termux session
```

If the supervisor session was lost and you need to stop it, use the recorded
PID rather than a broad process-name kill:

```bash
kill "$(cat ~/wearsic-server/wearsic-server.pid)"
```

## 8. Data and backup

Important files:

- `wearsic.db` — favorites and playlists;
- `.env` — API key and server settings;
- `wearsic-server.log` — supervisor and server logs.

Back up the database and keep `.env` private:

```bash
cp ~/wearsic-server/wearsic.db ~/wearsic-server/wearsic.db.backup
cp ~/wearsic-server/.env ~/wearsic-server/.env.backup
chmod 600 ~/wearsic-server/.env.backup
```

## 9. Keep Termux alive

For long-running use:

1. Run `termux-wake-lock` if the supervisor did not acquire it automatically.
2. Set Termux battery usage to **Unrestricted** in Android settings.
3. Do not swipe the supervisor Termux session away.
4. For reboot-start support, install Termux:Boot from F-Droid and create:

```bash
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/start-wearsic.sh <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
exec "$HOME/wearsic-server/run-termux.sh"
EOF
chmod +x ~/.termux/boot/start-wearsic.sh
```

## 10. Troubleshooting

### Missing binary

```bash
cd ~/wearsic-server
ls -l bin/wearsic-server lib/
chmod +x bin/wearsic-server run-termux.sh
```

If `bin/` or `lib/` is missing, extract the complete release ZIP again.

### Port already in use

Check the process using the port:

```bash
curl http://127.0.0.1:8080/health
cat ~/wearsic-server/wearsic-server.pid 2>/dev/null || true
```

Stop the existing supervisor using its PID, then start one copy only.

### HTTP 401 or 403

Confirm the same key is present in `.env` and Wearsic Settings. The header is:

```text
X-Wearsic-Key
```

### Search or stream extraction fails

Inspect the log:

```bash
tail -100 ~/wearsic-server/wearsic-server.log
```

YouTube may require a cookie. The server README documents the optional
`WEARSIC_YOUTUBE_COOKIE` environment variable and cookie configuration route.

### Server restarts repeatedly

Check Java, storage, and logs:

```bash
java -version
df -h ~
tail -200 ~/wearsic-server/wearsic-server.log
```

The server needs free storage for SQLite and stream handling.
