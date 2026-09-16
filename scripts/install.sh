#!/usr/bin/env bash
# @file install.sh
# @brief Create a local venv, install the package, and enable autostart.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
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
  log "Installing wormhole-auto-config (editable)"
  pip install --upgrade pip >/dev/null
  pip install -e "${ROOT_DIR}"
}

main() {
  require_python
  setup_venv
  exec "${ROOT_DIR}/.venv/bin/wormhole-auto-config" install --host "${HOST}" --port "${PORT}"
}

main "$@"
