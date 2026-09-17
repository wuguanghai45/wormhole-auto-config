"""Online update helpers: GitHub Releases check, download, and install."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Optional

import httpx
from packaging.version import InvalidVersion, Version

PACKAGE_NAME = "wormhole-auto-config"
DEFAULT_UPDATE_REPO = "wuguanghai45/wormhole-auto-config"
GITHUB_API = "https://api.github.com"
FALLBACK_VERSION = "0.0.0"


class UpdateError(Exception):
    """Raised when an update check or apply step fails."""


@dataclass(frozen=True)
class UpdateInfo:
    """Result of comparing the installed package to the latest GitHub Release."""

    current_version: str
    latest_version: str
    update_available: bool
    release_notes: str
    asset_name: str
    asset_url: str
    html_url: str


def resolve_update_repo() -> str:
    """Return owner/repo for GitHub Releases (env override supported)."""
    raw = os.environ.get("WORMHOLE_UPDATE_REPO", "").strip()
    return raw or DEFAULT_UPDATE_REPO


def _github_headers() -> dict[str, str]:
    """Build GitHub API headers, including optional auth token."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{PACKAGE_NAME}-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = (
        os.environ.get("WORMHOLE_GITHUB_TOKEN", "").strip()
        or os.environ.get("GITHUB_TOKEN", "").strip()
    )
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


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


def _pick_wheel_asset(assets: list[dict[str, Any]]) -> dict[str, Any]:
    """Select the first release asset whose name ends with .whl."""
    for asset in assets:
        name = str(asset.get("name") or "")
        if name.endswith(".whl"):
            return asset
    raise UpdateError("latest release has no .whl asset")


async def check_for_update(timeout_sec: float = 20.0) -> UpdateInfo:
    """
    Query GitHub Releases for the latest wheel and compare to the installed version.

    @param[in] timeout_sec HTTP timeout for the GitHub API request.
    @return Comparison result including download URL when a wheel exists.
    @raises UpdateError When the API call fails or no wheel asset is present.
    """
    repo = resolve_update_repo()
    url = f"{GITHUB_API}/repos/{repo}/releases/latest"
    installed = current_version()

    try:
        async with httpx.AsyncClient(
            timeout=timeout_sec,
            headers=_github_headers(),
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise UpdateError(f"failed to reach GitHub Releases: {exc}") from exc

    if response.status_code == 404:
        raise UpdateError("no GitHub Release found")
    if response.status_code >= 400:
        raise UpdateError(
            f"GitHub API error HTTP {response.status_code}: {response.text[:200]}"
        )

    payload = response.json()
    tag = str(payload.get("tag_name") or "")
    latest = tag[1:] if tag.lower().startswith("v") else tag
    if not latest:
        raise UpdateError("latest release has an empty tag_name")

    asset = _pick_wheel_asset(list(payload.get("assets") or []))
    asset_name = str(asset.get("name") or "")
    asset_url = str(asset.get("browser_download_url") or "")
    if not asset_url:
        raise UpdateError("wheel asset has no download URL")

    update_available = _parse_version(latest) > _parse_version(installed)
    return UpdateInfo(
        current_version=installed,
        latest_version=latest,
        update_available=update_available,
        release_notes=str(payload.get("body") or ""),
        asset_name=asset_name,
        asset_url=asset_url,
        html_url=str(payload.get("html_url") or ""),
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
    Download a wheel from GitHub and install it with pip.

    @param[in] asset_url Browser download URL for the release wheel.
    @param[in] timeout_sec HTTP timeout for the download.
    @raises UpdateError When download or pip install fails.
    """
    try:
        async with httpx.AsyncClient(
            timeout=timeout_sec,
            headers=_github_headers(),
            follow_redirects=True,
        ) as client:
            response = await client.get(asset_url)
    except httpx.HTTPError as exc:
        raise UpdateError(f"failed to download wheel: {exc}") from exc

    if response.status_code >= 400:
        raise UpdateError(f"wheel download failed HTTP {response.status_code}")

    suffix = Path(asset_url).name
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
