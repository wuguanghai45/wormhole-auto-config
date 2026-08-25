#!/usr/bin/env bash
# @file install.sh
# @brief Install dependencies and register wormhole-auto-config for login autostart.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_NAME="wormhole-auto-config"
LAUNCH_LABEL="com.wormhole.auto-config"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

log() {
  printf '[install] %s\n' "$*"
}

die() {
  printf '[install] ERROR: %s\n' "$*" >&2
  exit 1
}

require_python() {
  command -v "${PYTHON_BIN}" >/dev/null 2>&1 || die "Python not found: ${PYTHON_BIN}"
  local version
  version="$("${PYTHON_BIN}" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  "${PYTHON_BIN}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
    || die "Python 3.10+ required (found ${version})"
}

setup_venv() {
  log "Project root: ${ROOT_DIR}"
  cd "${ROOT_DIR}"
  if [[ ! -d .venv ]]; then
    log "Creating virtualenv (.venv)"
    "${PYTHON_BIN}" -m venv .venv
  else
    log "Virtualenv already exists"
  fi
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.venv/bin/activate"
  log "Installing Python dependencies"
  pip install --upgrade pip >/dev/null
  pip install -r "${ROOT_DIR}/requirements.txt"
  mkdir -p "${ROOT_DIR}/data" "${ROOT_DIR}/logs"
}

uvicorn_bin() {
  printf '%s' "${ROOT_DIR}/.venv/bin/uvicorn"
}

install_macos() {
  local plist_dir="${HOME}/Library/LaunchAgents"
  local plist_path="${plist_dir}/${LAUNCH_LABEL}.plist"
  local log_out="${ROOT_DIR}/logs/service.out.log"
  local log_err="${ROOT_DIR}/logs/service.err.log"
  local uv
  uv="$(uvicorn_bin)"
  [[ -x "${uv}" ]] || die "uvicorn not found at ${uv}"

  mkdir -p "${plist_dir}"
  if launchctl print "gui/$(id -u)/${LAUNCH_LABEL}" >/dev/null 2>&1; then
    log "Unloading existing LaunchAgent"
    launchctl bootout "gui/$(id -u)" "${plist_path}" >/dev/null 2>&1 || true
  fi

  cat >"${plist_path}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LAUNCH_LABEL}</string>
  <key>WorkingDirectory</key>
  <string>${ROOT_DIR}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${uv}</string>
    <string>app.main:app</string>
    <string>--host</string>
    <string>${HOST}</string>
    <string>--port</string>
    <string>${PORT}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${log_out}</string>
  <key>StandardErrorPath</key>
  <string>${log_err}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:${ROOT_DIR}/.venv/bin</string>
  </dict>
</dict>
</plist>
EOF

  log "Loading LaunchAgent: ${plist_path}"
  launchctl bootstrap "gui/$(id -u)" "${plist_path}"
  launchctl enable "gui/$(id -u)/${LAUNCH_LABEL}" >/dev/null 2>&1 || true
  log "macOS login autostart enabled (${LAUNCH_LABEL})"
}

install_linux() {
  local unit_dir="${HOME}/.config/systemd/user"
  local unit_path="${unit_dir}/${SERVICE_NAME}.service"
  local uv
  uv="$(uvicorn_bin)"
  [[ -x "${uv}" ]] || die "uvicorn not found at ${uv}"

  mkdir -p "${unit_dir}" "${ROOT_DIR}/logs"
  cat >"${unit_path}" <<EOF
[Unit]
Description=Wormhole Auto-Config Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${ROOT_DIR}
ExecStart=${uv} app.main:app --host ${HOST} --port ${PORT}
Restart=on-failure
RestartSec=3
StandardOutput=append:${ROOT_DIR}/logs/service.out.log
StandardError=append:${ROOT_DIR}/logs/service.err.log

[Install]
WantedBy=default.target
EOF

  systemctl --user daemon-reload
  systemctl --user enable --now "${SERVICE_NAME}.service"
  log "Linux systemd user service enabled (${SERVICE_NAME})"
  if ! systemctl --user show-environment >/dev/null 2>&1; then
    log "Tip: enable lingering for boot without login: loginctl enable-linger $(whoami)"
  fi
}

print_done() {
  log "Install complete"
  log "UI: http://127.0.0.1:${PORT}"
  log "Logs: ${ROOT_DIR}/logs/"
  log "Uninstall: ${SCRIPT_DIR}/uninstall.sh"
}

main() {
  require_python
  setup_venv

  case "$(uname -s)" in
    Darwin)
      install_macos
      ;;
    Linux)
      install_linux
      ;;
    *)
      die "Unsupported OS: $(uname -s). Supported: macOS, Linux"
      ;;
  esac

  print_done
}

main "$@"
