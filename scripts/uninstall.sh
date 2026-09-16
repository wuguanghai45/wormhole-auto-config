#!/usr/bin/env bash
# @file uninstall.sh
# @brief Remove wormhole-auto-config from login/boot autostart.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -x "${ROOT_DIR}/.venv/bin/wormhole-auto-config" ]]; then
  exec "${ROOT_DIR}/.venv/bin/wormhole-auto-config" uninstall
fi

if command -v wormhole-auto-config >/dev/null 2>&1; then
  exec wormhole-auto-config uninstall
fi

printf '[uninstall] ERROR: wormhole-auto-config not found. Activate the install venv or PATH.\n' >&2
exit 1
