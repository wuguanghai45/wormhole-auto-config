# Wormhole Auto-Config Service

Local operator tool that waits for a LAN link to the Wormhole device, clears stale WiFi sections over SSH, then configures WiFi (and optional MQTT bridge mode) via device CGI and verifies STA connectivity.

## Features

- Web UI to set WiFi SSID / password and MQTT bridge mode (`proxy` / `direct`)
- One-click auto-config job with live progress (SSE)
- Monitors host LAN for IPv4, then talks to `http://192.168.40.1` CGI endpoints
- Before each WiFi update, uses SSH to delete `wireless.wifinet0`, `wireless.wifinet1`, and `wireless.wifinet2`
- Verifies success when `get-network-status` reports `wifi.ip0` or `wifi.ip1`

## Requirements

- Python 3.10+
- Host machine Ethernet-connected to the device LAN
- Device reachable at `192.168.40.1` (configurable)
- SSH key authentication for the device (defaults: `root`, port `22`); configure the matching key in the local OpenSSH agent or configuration

## Setup (recommended)

One-shot install: create venv, install deps, and enable **login/boot autostart**.

```bash
cd wormhole-auto-config
chmod +x scripts/*.sh
./scripts/install.sh
```

Then open [http://localhost:8080](http://localhost:8080).

| Platform | Autostart mechanism |
|----------|---------------------|
| macOS | LaunchAgent `~/Library/LaunchAgents/com.wormhole.auto-config.plist` |
| Linux | systemd user unit `~/.config/systemd/user/wormhole-auto-config.service` |

Optional environment overrides when installing:

```bash
HOST=0.0.0.0 PORT=8080 ./scripts/install.sh
```

Uninstall autostart (keeps project files):

```bash
./scripts/uninstall.sh
```

Foreground run without touching autostart:

```bash
./scripts/run.sh
```

Service logs: `logs/service.out.log`, `logs/service.err.log`.

### Manual setup

```bash
cd wormhole-auto-config
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Run

After `./scripts/install.sh`, the service starts automatically on login.

Manual foreground:

```bash
./scripts/run.sh
```

Open [http://localhost:8080](http://localhost:8080).

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/config` | Load saved settings |
| PUT | `/api/config` | Save settings |
| POST | `/api/jobs/start` | Start auto-config (body optional `AppConfig`) |
| POST | `/api/jobs/stop` | Cancel running job |
| GET | `/api/jobs/current` | Current job snapshot |
| GET | `/api/jobs/events` | SSE job progress stream |
| GET | `/api/health` | Liveness |

## Device CGI used

- `POST /cgi-bin/save-wifi-config` — `{"ssid","password"}`
- `GET /cgi-bin/get-services-info` — read MQTT links / `connection_mode`
- `POST /cgi-bin/save-mqtt-config` — rewrite links with desired `connection_mode`
- `GET /cgi-bin/get-network-status` — WiFi STA IP check

Before `save-wifi-config`, the service runs the following on the same device IP over SSH:

```sh
uci -q delete wireless.wifinet0
uci -q delete wireless.wifinet1
uci -q delete wireless.wifinet2
uci commit wireless
```

## i18n

- UI and job progress messages support **zh-CN** (default) and **en**.
- Switch language with the **中文 / EN** control in the header.
- Locale is persisted in `data/config.json` (`locale` field) and `localStorage`.

## Notes

- Settings are stored in `data/config.json`.
- Bridge mode maps to MQTT `connection_mode=proxy` (on) or `direct` (off).
- SSH is non-interactive and uses the host's existing OpenSSH keys/configuration. Host-key fingerprint verification and `known_hosts` updates are disabled so new or reflashed robots do not block automatic configuration.
