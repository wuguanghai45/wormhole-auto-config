# Wormhole Auto-Config Service

Local operator tool that waits for a LAN link to the Wormhole device, clears stale WiFi sections over SSH, then configures WiFi (and optional MQTT bridge mode) via device CGI and verifies STA connectivity.

## Features

- Web UI to set WiFi SSID / password and MQTT bridge mode (`proxy` / `direct`)
- One-click auto-config job with live progress (SSE)
- Monitors host LAN for IPv4, then talks to `http://192.168.40.1` CGI endpoints
- Before each WiFi update, uses SSH to delete `wireless.wifinet0`, `wireless.wifinet1`, and `wireless.wifinet2`
- Verifies success when `get-network-status` reports `wifi.ip0` or `wifi.ip1`
- In-app update check against MinIO `versions.json` (download wheel and restart)

## Requirements

- Python 3.10+
- Host machine Ethernet-connected to the device LAN
- Device reachable at `192.168.40.1` (configurable)
- SSH key authentication for the device (defaults: `root`, port `22`); configure the matching key in the local OpenSSH agent or configuration

## Setup (recommended)

Install the wheel into a venv, then register **login/boot autostart**:

```bash
cd wormhole-auto-config
python3 -m venv .venv
source .venv/bin/activate
pip install .
wormhole-auto-config install
```

Or use the one-shot script (creates `.venv`, editable install, then `install`):

```bash
chmod +x scripts/*.sh
./scripts/install.sh
```

Then open [http://localhost:8080](http://localhost:8080).

| Platform | Autostart mechanism |
|----------|---------------------|
| macOS | LaunchAgent `~/Library/LaunchAgents/com.wormhole.auto-config.plist` |
| Linux | systemd user unit `~/.config/systemd/user/wormhole-auto-config.service` |

Optional environment / flag overrides:

```bash
HOST=0.0.0.0 PORT=8080 ./scripts/install.sh
# or
wormhole-auto-config install --host 0.0.0.0 --port 8080
```

Uninstall autostart (keeps config and logs):

```bash
wormhole-auto-config uninstall
# or
./scripts/uninstall.sh
```

Foreground run without touching autostart:

```bash
wormhole-auto-config serve
# or
./scripts/run.sh
```

### Build a wheel

```bash
pip install build
python -m build
# artifacts under dist/*.whl
```

### Release (CI/CD)

1. Bump `version` in `pyproject.toml` (for example `1.2.3`).
2. Commit the change.
3. Tag and push:

```bash
git tag v1.2.3
git push origin main --tags
```

GitHub Actions (`.github/workflows/release.yml`) builds the wheel on `main`/PRs, and on `v*` tags:

1. Publishes a GitHub Release with the `.whl` asset (backup channel).
2. Uploads the wheel and a **latest-only** `versions.json` to MinIO.

The tag (without `v`) must match `pyproject.toml`.

Required GitHub repository secrets:

| Secret | Purpose |
|--------|---------|
| `MINIO_ACCESS_KEY` | MinIO access key |
| `MINIO_SECRET_KEY` | MinIO secret key |

Artifact locations:

| Kind | URL |
|------|-----|
| Version manifest | `http://minio.hcrobots.com:9000/hc-release/wormhole-auto-config/versions.json` |
| Wheel | `http://minio.hcrobots.com:9000/hc-release/wormhole-auto-config/<tag>/*.whl` |

`versions.json` always contains a single entry for the newest release (history is not merged). CI runners and operator machines must be able to reach `minio.hcrobots.com:9000`.

### Online upgrade (Web UI)

After the service is installed from a wheel (`pip install` / Release asset), open the UI header:

1. Current version is shown automatically (and on **Check for updates**).
2. If a newer version is listed in MinIO `versions.json`, click **Upgrade to vX.Y.Z**.
3. The service downloads that wheel, runs `pip install --upgrade`, then restarts (LaunchAgent KeepAlive / systemd `Restart=always`).

Notes:

- Prefer an installed package environment; a loose uninstalled checkout may report `0.0.0` and cannot self-upgrade cleanly.
- Optional: `WORMHOLE_UPDATE_MANIFEST_URL` to override the default MinIO `versions.json` URL.

### Manual setup

```bash
cd wormhole-auto-config
python3 -m venv .venv
source .venv/bin/activate
pip install .
wormhole-auto-config serve --host 0.0.0.0 --port 8080
```

## Run

After `wormhole-auto-config install` (or `./scripts/install.sh`), the service starts automatically on login.

Manual foreground:

```bash
wormhole-auto-config serve
```

Open [http://localhost:8080](http://localhost:8080).

## Data locations

| Kind | Path |
|------|------|
| Config | `~/.local/share/wormhole-auto-config/config.json` (`$XDG_DATA_HOME` if set) |
| Logs | `~/.local/state/wormhole-auto-config/logs/` (`$XDG_STATE_HOME` if set) |

A one-time migration copies an old checkout `data/config.json` into the XDG path when present.

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
| GET | `/api/update/check` | Compare installed version to MinIO `versions.json` |
| POST | `/api/update/apply` | Download latest MinIO wheel, install, restart service |

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
- Locale is persisted in `config.json` (`locale` field) and `localStorage`.

## Notes

- Settings are stored under the XDG data directory (see above).
- Bridge mode maps to MQTT `connection_mode=proxy` (on) or `direct` (off).
- SSH is non-interactive and uses the host's existing OpenSSH keys/configuration. Host-key fingerprint verification and `known_hosts` updates are disabled so new or reflashed robots do not block automatic configuration.
