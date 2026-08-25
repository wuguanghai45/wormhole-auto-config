"""Application defaults and persisted local configuration helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.i18n import DEFAULT_LOCALE, normalize_locale

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
CONFIG_PATH = DATA_DIR / "config.json"

DEFAULT_ROUTER_IP = "192.168.40.1"
DEFAULT_LAN_WAIT_TIMEOUT_SEC = 300
DEFAULT_WIFI_VERIFY_TIMEOUT_SEC = 120
DEFAULT_POLL_INTERVAL_SEC = 2.0
DEFAULT_HTTP_TIMEOUT_SEC = 10.0


class AppConfig(BaseModel):
    """Local auto-config settings persisted on the host."""

    ssid: str = ""
    password: str = ""
    bridge_mode: bool = True
    locale: str = DEFAULT_LOCALE
    router_ip: str = DEFAULT_ROUTER_IP
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


def ensure_data_dir() -> None:
    """Create the data directory if it does not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    """Load persisted config from disk, or return defaults."""
    ensure_data_dir()
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
