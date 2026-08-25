"""HTTP client for robot-config-ui CGI endpoints on the device."""

from __future__ import annotations

from typing import Any, Optional

import httpx


class DeviceCgiError(Exception):
    """Raised when a device CGI call fails."""

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class DeviceCgiClient:
    """Async HTTP helper for wormhole device CGI APIs."""

    def __init__(self, router_ip: str, timeout_sec: float = 10.0) -> None:
        self.base_url = f"http://{router_ip}"
        self.timeout = timeout_sec

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            trust_env=False,
        )

    async def _get_json(self, path: str) -> dict[str, Any]:
        async with self._client() as client:
            try:
                response = await client.get(path)
            except httpx.HTTPError as exc:
                raise DeviceCgiError(f"GET {path} failed: {exc}") from exc
        return self._parse_json(response, path)

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with self._client() as client:
            try:
                response = await client.post(path, json=payload)
            except httpx.HTTPError as exc:
                raise DeviceCgiError(f"POST {path} failed: {exc}") from exc
        return self._parse_json(response, path)

    @staticmethod
    def _parse_json(response: httpx.Response, path: str) -> dict[str, Any]:
        if response.status_code >= 400:
            raise DeviceCgiError(
                f"{path} returned HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise DeviceCgiError(f"{path} returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise DeviceCgiError(f"{path} returned unexpected JSON type")
        return data

    async def probe_reachable(self) -> bool:
        """Return True when get-network-status responds successfully."""
        try:
            data = await self.get_network_status()
            return data.get("status") == "success"
        except DeviceCgiError:
            return False

    async def save_wifi(self, ssid: str, password: str) -> dict[str, Any]:
        """POST /cgi-bin/save-wifi-config with SSID and password."""
        data = await self._post_json(
            "/cgi-bin/save-wifi-config",
            {"ssid": ssid, "password": password},
        )
        if data.get("status") != "success":
            raise DeviceCgiError(data.get("message") or "save-wifi-config failed")
        return data

    async def get_services_info(self) -> dict[str, Any]:
        """GET /cgi-bin/get-services-info (legacy mqtt.hostname/port fields)."""
        data = await self._get_json("/cgi-bin/get-services-info")
        if data.get("status") != "success":
            raise DeviceCgiError(data.get("message") or "get-services-info failed")
        return data

    async def save_mqtt(
        self,
        *,
        host: str,
        port: str | int,
        username: str = "",
        password: str = "",
        connection_mode: str = "proxy",
    ) -> dict[str, Any]:
        """POST /cgi-bin/save-mqtt-config using the production shell CGI contract.

        Body fields are all JSON strings because the device CGI parses them with
        sed patterns like `"port":"..."`.
        """
        if connection_mode not in ("proxy", "direct"):
            raise DeviceCgiError(f"Invalid connection_mode: {connection_mode}")
        host_value = str(host or "").strip()
        port_value = str(port or "").strip()
        if not host_value or not port_value:
            raise DeviceCgiError("MQTT host and port are required")

        payload = {
            "host": host_value,
            "port": port_value,
            "username": "" if username is None else str(username),
            "password": "" if password is None else str(password),
            "connection_mode": connection_mode,
        }
        data = await self._post_json("/cgi-bin/save-mqtt-config", payload)
        if data.get("status") != "success":
            raise DeviceCgiError(data.get("message") or "save-mqtt-config failed")
        return data

    async def get_network_status(self) -> dict[str, Any]:
        """GET /cgi-bin/get-network-status for live WiFi/4G status."""
        data = await self._get_json("/cgi-bin/get-network-status")
        if data.get("status") != "success":
            raise DeviceCgiError(data.get("message") or "get-network-status failed")
        return data

    @staticmethod
    def wifi_ips(status: dict[str, Any]) -> tuple[str, str]:
        """Extract wifi.ip0 and wifi.ip1 from a network status payload."""
        wifi = status.get("wifi") or {}
        ip0 = str(wifi.get("ip0") or "").strip()
        ip1 = str(wifi.get("ip1") or "").strip()
        return ip0, ip1

    @staticmethod
    def has_wifi_ip(status: dict[str, Any]) -> bool:
        """Return True when either WiFi radio has an IPv4 address."""
        ip0, ip1 = DeviceCgiClient.wifi_ips(status)
        return bool(ip0 or ip1)
