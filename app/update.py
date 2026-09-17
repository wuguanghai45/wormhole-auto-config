"""Online update helpers: MinIO versions.json check, download, and install."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from packaging.version import InvalidVersion, Version

PACKAGE_NAME = "wormhole-auto-config"
DEFAULT_MANIFEST_URL = (
    "http://minio.hcrobots.com:9000/hc-release/wormhole-auto-config/versions.json"
)
FALLBACK_VERSION = "0.0.0"


class UpdateError(Exception):
    """Raised when an update check or apply step fails."""


@dataclass(frozen=True)
class UpdateInfo:
    """Result of comparing the installed package to the latest MinIO release."""

    current_version: str
    latest_version: str
    update_available: bool
    release_notes: str
    asset_name: str
    asset_url: str
    html_url: str


def resolve_manifest_url() -> str:
    """Return the MinIO versions.json URL (env override supported)."""
    raw = os.environ.get("WORMHOLE_UPDATE_MANIFEST_URL", "").strip()
    return raw or DEFAULT_MANIFEST_URL


def current_version() -> str:
    """
    Return the installed package version.

    Falls back to FALLBACK_VERSION when distribution metadata is missing
    (for example a loose checkout without an install).
    """
    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return FALLBACK_VERSION


def _parse_version(value: str) -> Version:
    """Parse a semver-like string, stripping a leading 'v' if present."""
    text = value.strip()
    if text.lower().startswith("v"):
        text = text[1:]
    try:
        return Version(text)
    except InvalidVersion as exc:
        raise UpdateError(f"invalid version: {value}") from exc


def _pick_latest_entry(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the first versions[] entry from a latest-only manifest."""
    versions = payload.get("versions")
    if not isinstance(versions, list) or not versions:
        raise UpdateError("versions.json has no versions entries")
    entry = versions[0]
    if not isinstance(entry, dict):
        raise UpdateError("versions.json entry is invalid")
    return entry


async def check_for_update(timeout_sec: float = 20.0) -> UpdateInfo:
    """
    Query the MinIO versions.json manifest and compare to the installed version.

    @param[in] timeout_sec HTTP timeout for the manifest request.
    @return Comparison result including download URL when a wheel exists.
    @raises UpdateError When the request fails or the manifest is invalid.
    """
    url = resolve_manifest_url()
    installed = current_version()

    try:
        async with httpx.AsyncClient(
            timeout=timeout_sec,
            follow_redirects=True,
            headers={"User-Agent": f"{PACKAGE_NAME}-updater"},
        ) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise UpdateError(f"failed to reach update manifest: {exc}") from exc

    if response.status_code == 404:
        raise UpdateError("no update manifest found")
    if response.status_code >= 400:
        raise UpdateError(
            f"manifest HTTP {response.status_code}: {response.text[:200]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise UpdateError("update manifest is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise UpdateError("update manifest root must be an object")

    entry = _pick_latest_entry(payload)
    latest_raw = str(entry.get("version") or "").strip()
    if not latest_raw:
        raise UpdateError("manifest entry has an empty version")
    latest = latest_raw[1:] if latest_raw.lower().startswith("v") else latest_raw

    asset_url = str(entry.get("download_url") or "").strip()
    if not asset_url:
        raise UpdateError("manifest entry has no download_url")

    asset_name = Path(urlparse(asset_url).path).name
    if not asset_name.endswith(".whl"):
        asset_name = f"{PACKAGE_NAME.replace('-', '_')}-{latest}-py3-none-any.whl"

    update_available = _parse_version(latest) > _parse_version(installed)
    return UpdateInfo(
        current_version=installed,
        latest_version=latest,
        update_available=update_available,
        release_notes=str(entry.get("notes") or ""),
        asset_name=asset_name,
        asset_url=asset_url,
        html_url=asset_url,
    )


def _install_wheel(wheel_path: Path) -> None:
    """Install a local wheel into the current interpreter environment."""
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        str(wheel_path),
    ]
    completed = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise UpdateError(f"pip install failed: {detail[:500]}")


async def download_and_install(asset_url: str, timeout_sec: float = 120.0) -> None:
    """
    Download a wheel from MinIO and install it with pip.

    @param[in] asset_url Download URL for the release wheel.
    @param[in] timeout_sec HTTP timeout for the download.
    @raises UpdateError When download or pip install fails.
    """
    try:
        async with httpx.AsyncClient(
            timeout=timeout_sec,
            follow_redirects=True,
            headers={"User-Agent": f"{PACKAGE_NAME}-updater"},
        ) as client:
            response = await client.get(asset_url)
    except httpx.HTTPError as exc:
        raise UpdateError(f"failed to download wheel: {exc}") from exc

    if response.status_code >= 400:
        raise UpdateError(f"wheel download failed HTTP {response.status_code}")

    suffix = Path(urlparse(asset_url).path).name
    if not suffix.endswith(".whl"):
        suffix = "update.whl"

    with tempfile.TemporaryDirectory(prefix="wormhole-update-") as tmp:
        wheel_path = Path(tmp) / suffix
        wheel_path.write_bytes(response.content)
        await asyncio.to_thread(_install_wheel, wheel_path)


async def schedule_process_restart(delay_sec: float = 1.0) -> None:
    """
    Exit the process after a short delay so LaunchAgent/systemd can restart it.

    @param[in] delay_sec Seconds to wait before terminating (lets the HTTP
        response flush to the client first).
    """
    await asyncio.sleep(delay_sec)
    os._exit(0)


async def apply_update() -> UpdateInfo:
    """
    Check for a newer release, install its wheel, and schedule a process restart.

    @return The update info that was applied.
    @raises UpdateError When no update is available or install fails.
    """
    info = await check_for_update()
    if not info.update_available:
        raise UpdateError(
            f"already up to date ({info.current_version})"
        )
    await download_and_install(info.asset_url)
    return info
