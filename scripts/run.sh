#!/usr/bin/env bash
# @file run.sh
# @brief Run the auto-config service in the foreground (no autostart).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"

if [[ -x "${ROOT_DIR}/.venv/bin/wormhole-auto-config" ]]; then
  exec "${ROOT_DIR}/.venv/bin/wormhole-auto-config" serve --host "${HOST}" --port "${PORT}"
fi

if command -v wormhole-auto-config >/dev/null 2>&1; then
  exec wormhole-auto-config serve --host "${HOST}" --port "${PORT}"
fi

printf '[run] ERROR: wormhole-auto-config not found. Run: %s/install.sh\n' "${SCRIPT_DIR}" >&2
exit 1
