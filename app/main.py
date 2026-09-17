"""FastAPI entrypoint for the Wormhole auto-config service."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.auto_config import AutoConfigService, sse_event_stream
from app.config import AppConfig, load_config, save_config
from app.i18n import normalize_locale, t
from app.models import (
    ApiMessage,
    ConfigResponse,
    JobState,
    StartJobResponse,
    UpdateApplyResponse,
    UpdateCheckResponse,
)
from app.update import (
    UpdateError,
    apply_update,
    check_for_update,
    current_version,
    schedule_process_restart,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Wormhole Auto-Config", version=current_version())
service = AutoConfigService()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    """Serve the operator web UI."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    """Return the persisted local configuration."""
    return ConfigResponse(config=load_config())


@app.put("/api/config", response_model=ConfigResponse)
async def put_config(config: AppConfig) -> ConfigResponse:
    """Validate and persist local configuration."""
    return ConfigResponse(config=save_config(config))


@app.get("/api/jobs/current", response_model=JobState)
async def get_current_job() -> JobState:
    """Return the current auto-config job snapshot."""
    return service.current()


@app.post("/api/jobs/start", response_model=StartJobResponse)
async def start_job(
    config: Optional[AppConfig] = Body(default=None),
) -> StartJobResponse:
    """Persist optional config and start an auto-config job."""
    if config is not None and config.ssid.strip():
        save_config(config)
    cfg = load_config()
    locale = normalize_locale(cfg.locale)
    try:
        state = await service.start(cfg)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return StartJobResponse(
        ok=True,
        message=t(locale, "job.start_ok"),
        state=state,
    )


@app.post("/api/jobs/stop", response_model=StartJobResponse)
async def stop_job() -> StartJobResponse:
    """Request cancellation of the running job."""
    cfg = load_config()
    locale = normalize_locale(cfg.locale)
    state = await service.stop()
    return StartJobResponse(
        ok=True,
        message=t(locale, "job.stop_ok"),
        state=state,
    )


@app.get("/api/jobs/events")
async def job_events() -> StreamingResponse:
    """Stream job state updates as Server-Sent Events."""
    return StreamingResponse(
        sse_event_stream(service),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/health", response_model=ApiMessage)
async def health() -> ApiMessage:
    """Liveness probe for smoke checks."""
    return ApiMessage(ok=True, message=t("en", "api.ok"))


@app.get("/api/update/check", response_model=UpdateCheckResponse)
async def update_check() -> UpdateCheckResponse:
    """Compare the installed version against the latest GitHub Release."""
    try:
        info = await check_for_update()
    except UpdateError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return UpdateCheckResponse(
        current_version=info.current_version,
        latest_version=info.latest_version,
        update_available=info.update_available,
        release_notes=info.release_notes,
        asset_name=info.asset_name,
        html_url=info.html_url,
    )


@app.post("/api/update/apply", response_model=UpdateApplyResponse)
async def update_apply() -> UpdateApplyResponse:
    """Download the latest wheel, install it, and schedule a process restart."""
    cfg = load_config()
    locale = normalize_locale(cfg.locale)
    if service.is_running():
        raise HTTPException(
            status_code=409,
            detail=t(locale, "update.job_running"),
        )
    try:
        info = await apply_update()
    except UpdateError as exc:
        message = str(exc)
        status = 400 if "already up to date" in message else 502
        raise HTTPException(status_code=status, detail=message) from exc

    asyncio.create_task(schedule_restart_after_response())
    return UpdateApplyResponse(
        ok=True,
        message=t(locale, "update.apply_ok", version=info.latest_version),
        target_version=info.latest_version,
    )


async def schedule_restart_after_response() -> None:
    """Delay briefly so the apply response can flush, then exit the process."""
    await schedule_process_restart(1.0)

