#!/usr/bin/env bash
# @file uninstall.sh
# @brief Remove wormhole-auto-config from login/boot autostart.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_NAME="wormhole-auto-config"
LAUNCH_LABEL="com.wormhole.auto-config"

log() {
  printf '[uninstall] %s\n' "$*"
}

uninstall_macos() {
  local plist_path="${HOME}/Library/LaunchAgents/${LAUNCH_LABEL}.plist"
  if launchctl print "gui/$(id -u)/${LAUNCH_LABEL}" >/dev/null 2>&1; then
    log "Stopping LaunchAgent ${LAUNCH_LABEL}"
    launchctl bootout "gui/$(id -u)" "${plist_path}" >/dev/null 2>&1 \
      || launchctl bootout "gui/$(id -u)/${LAUNCH_LABEL}" >/dev/null 2>&1 \
      || true
  fi
  if [[ -f "${plist_path}" ]]; then
    rm -f "${plist_path}"
    log "Removed ${plist_path}"
  else
    log "LaunchAgent plist not found (already removed)"
  fi
}

uninstall_linux() {
  local unit_path="${HOME}/.config/systemd/user/${SERVICE_NAME}.service"
  if systemctl --user list-unit-files "${SERVICE_NAME}.service" >/dev/null 2>&1; then
    systemctl --user disable --now "${SERVICE_NAME}.service" >/dev/null 2>&1 || true
  fi
  if [[ -f "${unit_path}" ]]; then
    rm -f "${unit_path}"
    systemctl --user daemon-reload || true
    log "Removed ${unit_path}"
  else
    log "systemd unit not found (already removed)"
  fi
}

main() {
  case "$(uname -s)" in
    Darwin)
      uninstall_macos
      ;;
    Linux)
      uninstall_linux
      ;;
    *)
      log "Unsupported OS: $(uname -s)"
      exit 1
      ;;
  esac
  log "Autostart removed. Project files kept at ${ROOT_DIR}"
  log "To also delete the venv: rm -rf ${ROOT_DIR}/.venv"
}

main "$@"
