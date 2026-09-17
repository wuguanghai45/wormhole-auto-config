"""Pydantic models for API payloads and job state."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.config import AppConfig
from app.i18n import DEFAULT_LOCALE, t


class JobPhase(str, Enum):
    """Lifecycle phases for an auto-config job."""

    IDLE = "idle"
    WAITING_LAN = "waiting_lan"
    WAITING_RECONNECT = "waiting_reconnect"
    APPLYING_WIFI = "applying_wifi"
    APPLYING_BRIDGE = "applying_bridge"
    VERIFYING_WIFI = "verifying_wifi"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


def utc_now() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


class JobState(BaseModel):
    """Snapshot of the current (or last) auto-config job."""

    phase: JobPhase = JobPhase.IDLE
    message: str = Field(default_factory=lambda: t(DEFAULT_LOCALE, "job.idle"))
    locale: str = DEFAULT_LOCALE
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    lan_ip: Optional[str] = None
    lan_interface: Optional[str] = None
    wifi_ip0: Optional[str] = None
    wifi_ip1: Optional[str] = None
    error: Optional[str] = None
    logs: list[str] = Field(default_factory=list)

    def append_log(self, line: str) -> None:
        """Append a timestamped log line and refresh updated_at."""
        stamp = utc_now().strftime("%H:%M:%S")
        self.logs.append(f"[{stamp}] {line}")
        if len(self.logs) > 200:
            self.logs = self.logs[-200:]
        self.updated_at = utc_now()


class JobEvent(BaseModel):
    """Server-sent event payload for job progress."""

    type: str = "state"
    state: JobState


class StartJobResponse(BaseModel):
    """Response returned when a job is accepted."""

    ok: bool
    message: str
    state: JobState


class ApiMessage(BaseModel):
    """Generic API acknowledgement."""

    ok: bool
    message: str
    detail: Optional[dict[str, Any]] = None


class ConfigResponse(BaseModel):
    """Wrapper for GET/PUT config responses."""

    config: AppConfig


class UpdateCheckResponse(BaseModel):
    """Payload returned by GET /api/update/check."""

    current_version: str
    latest_version: str
    update_available: bool
    release_notes: str = ""
    asset_name: str = ""
    html_url: str = ""


class UpdateApplyResponse(BaseModel):
    """Payload returned by POST /api/update/apply."""

    ok: bool
    message: str
    target_version: str
