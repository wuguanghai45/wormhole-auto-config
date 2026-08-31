"""SSH helper for clearing stale OpenWrt WiFi network sections."""

from __future__ import annotations

import asyncio


class DeviceSshError(Exception):
    """Raised when a required SSH command cannot run successfully on the device."""


class DeviceSshClient:
    """Run non-interactive maintenance commands on a robot through the system SSH client."""

    _CLEANUP_WIFI_COMMAND = (
        "uci -q delete wireless.wifinet0; "
        "uci -q delete wireless.wifinet1; "
        "uci -q delete wireless.wifinet2; "
        "uci commit wireless"
    )

    def __init__(
        self,
        host: str,
        *,
        username: str = "root",
        port: int = 22,
        timeout_sec: float = 10.0,
    ) -> None:
        """Set the SSH endpoint and execution timeout for one robot.

        Authentication is delegated to the local OpenSSH configuration and keys.
        """
        self.host = host
        self.username = username
        self.port = port
        self.timeout_sec = timeout_sec

    async def clear_stale_wifi_networks(self) -> None:
        """Delete stale ``wireless.wifinet0`` through ``wireless.wifinet2`` sections.

        The command deliberately uses ``uci -q delete`` so a section that is
        already absent does not produce device-side noise, then commits the UCI
        changes. It is run before the CGI applies the replacement WiFi
        configuration.

        Raises:
            DeviceSshError: If OpenSSH is unavailable, times out, or returns a
                non-zero exit code.
        """
        command = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={max(1, int(self.timeout_sec))}",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-p",
            str(self.port),
            f"{self.username}@{self.host}",
            self._CLEANUP_WIFI_COMMAND,
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise DeviceSshError(f"SSH client could not start: {exc}") from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout_sec
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise DeviceSshError(
                f"SSH cleanup timed out after {self.timeout_sec:g}s"
            ) from exc

        if process.returncode != 0:
            detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
            suffix = f": {detail}" if detail else ""
            raise DeviceSshError(
                f"SSH cleanup exited with status {process.returncode}{suffix}"
            )
