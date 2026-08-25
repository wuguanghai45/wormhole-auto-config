# Wormhole Auto-Config Service

Local operator tool that waits for a LAN link to the Wormhole device, then configures WiFi (and optional MQTT bridge mode) via device CGI, and verifies STA connectivity.

## Features

- Web UI to set WiFi SSID / password and MQTT bridge mode (`proxy` / `direct`)
- One-click auto-config job with live progress (SSE)
- Monitors host LAN for IPv4, then talks to `http://192.168.40.1` CGI endpoints
- Verifies success when `get-network-status` reports `wifi.ip0` or `wifi.ip1`

## Requirements

- Python 3.10+
- Host machine Ethernet-connected to the device LAN
- Device reachable at `192.168.40.1` (configurable)

## Setup

```bash
cd wormhole-auto-config
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8080
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

## i18n

- UI and job progress messages support **zh-CN** (default) and **en**.
- Switch language with the **中文 / EN** control in the header.
- Locale is persisted in `data/config.json` (`locale` field) and `localStorage`.

## Notes

- Settings are stored in `data/config.json`.
- Bridge mode maps to MQTT `connection_mode=proxy` (on) or `direct` (off).
- No SSH is used; the service calls CGI over HTTP on the LAN.
