"""Application defaults and persisted local configuration helpers."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.i18n import DEFAULT_LOCALE, normalize_locale

APP_DIR_NAME = "wormhole-auto-config"


def _xdg_home(env_key: str, default_relative: Path) -> Path:
    """Resolve an XDG base directory, expanding a tilde-free absolute path."""
    override = os.environ.get(env_key, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / default_relative


def user_data_dir() -> Path:
    """Return the XDG data directory for persisted application config."""
    return _xdg_home("XDG_DATA_HOME", Path(".local/share")) / APP_DIR_NAME


def user_state_dir() -> Path:
    """Return the XDG state directory for runtime state and logs."""
    return _xdg_home("XDG_STATE_HOME", Path(".local/state")) / APP_DIR_NAME


DATA_DIR = user_data_dir()
STATE_DIR = user_state_dir()
LOG_DIR = STATE_DIR / "logs"
CONFIG_PATH = DATA_DIR / "config.json"

# Legacy checkout path used for one-time config migration.
_LEGACY_ROOT = Path(__file__).resolve().parent.parent
_LEGACY_CONFIG_PATH = _LEGACY_ROOT / "data" / "config.json"

DEFAULT_ROUTER_IP = "192.168.40.1"
DEFAULT_LAN_WAIT_TIMEOUT_SEC = 300
DEFAULT_WIFI_VERIFY_TIMEOUT_SEC = 120
DEFAULT_POLL_INTERVAL_SEC = 2.0
DEFAULT_HTTP_TIMEOUT_SEC = 10.0
DEFAULT_SSH_USERNAME = "root"
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_TIMEOUT_SEC = 10.0


class AppConfig(BaseModel):
    """Local auto-config settings persisted on the host."""

    ssid: str = ""
    password: str = ""
    mqtt_host: str = ""
    mqtt_port: str = "1883"
    mqtt_username: str = ""
    mqtt_password: str = ""
    bridge_mode: bool = True
    locale: str = DEFAULT_LOCALE
    router_ip: str = DEFAULT_ROUTER_IP
    ssh_username: str = DEFAULT_SSH_USERNAME
    ssh_port: int = Field(default=DEFAULT_SSH_PORT, ge=1, le=65535)
    ssh_timeout_sec: float = Field(default=DEFAULT_SSH_TIMEOUT_SEC, ge=1.0)
    lan_interface: str = ""
    lan_wait_timeout_sec: int = Field(default=DEFAULT_LAN_WAIT_TIMEOUT_SEC, ge=10)
    wifi_verify_timeout_sec: int = Field(default=DEFAULT_WIFI_VERIFY_TIMEOUT_SEC, ge=10)
    poll_interval_sec: float = Field(default=DEFAULT_POLL_INTERVAL_SEC, ge=0.5)
    http_timeout_sec: float = Field(default=DEFAULT_HTTP_TIMEOUT_SEC, ge=1.0)

    @field_validator("locale")
    @classmethod
    def _normalize_locale(cls, value: str) -> str:
        """Normalize persisted locale to a supported catalog key."""
        return normalize_locale(value)

    @field_validator("mqtt_port", mode="before")
    @classmethod
    def _coerce_mqtt_port(cls, value: Any) -> str:
        """Store MQTT port as a string for local persistence and form binding."""
        if value is None:
            return "1883"
        return str(value).strip() or "1883"


def ensure_data_dir() -> None:
    """Create the data directory if it does not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def ensure_state_dirs() -> None:
    """Create the state and log directories if they do not exist."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _migrate_legacy_config() -> None:
    """Copy checkout data/config.json into the XDG path once if needed."""
    if CONFIG_PATH.exists() or not _LEGACY_CONFIG_PATH.is_file():
        return
    ensure_data_dir()
    try:
        shutil.copy2(_LEGACY_CONFIG_PATH, CONFIG_PATH)
    except OSError:
        return


def load_config() -> AppConfig:
    """Load persisted config from disk, or return defaults."""
    ensure_data_dir()
    _migrate_legacy_config()
    if not CONFIG_PATH.exists():
        return AppConfig()
    try:
        raw: Any = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return AppConfig.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValueError):
        return AppConfig()


def save_config(config: AppConfig) -> AppConfig:
    """Persist config to disk and return the saved model."""
    ensure_data_dir()
    CONFIG_PATH.write_text(
        config.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return config
