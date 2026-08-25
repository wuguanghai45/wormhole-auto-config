#!/usr/bin/env bash
# @file run.sh
# @brief Run the auto-config service in the foreground (no autostart).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8080}"

cd "${ROOT_DIR}"
if [[ ! -x "${ROOT_DIR}/.venv/bin/uvicorn" ]]; then
  echo "Virtualenv missing. Run: ${SCRIPT_DIR}/install.sh" >&2
  exit 1
fi

exec "${ROOT_DIR}/.venv/bin/uvicorn" app.main:app --host "${HOST}" --port "${PORT}"
