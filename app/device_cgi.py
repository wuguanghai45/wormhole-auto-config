"""HTTP client for robot-config-ui CGI endpoints on the device."""

from __future__ import annotations

from typing import Any, Optional

import httpx

# Firmware default Mosquitto bridge link section names.
DEFAULT_BRIDGE_LINK_NAMES = ("4g", "wifi0", "wifi1")


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
        """GET /cgi-bin/get-services-info for agent and bridge MQTT config."""
        data = await self._get_json("/cgi-bin/get-services-info")
        if data.get("status") != "success":
            raise DeviceCgiError(data.get("message") or "get-services-info failed")
        return data

    @staticmethod
    def extract_bridge_link_names(services_info: dict[str, Any]) -> list[str]:
        """Return ordered bridge link names from a get-services-info payload."""
        mqtt = services_info.get("mqtt") or {}
        bridge = mqtt.get("bridge") if isinstance(mqtt, dict) else None
        raw_links: Any = None
        if isinstance(bridge, dict):
            raw_links = bridge.get("links")
        if not isinstance(raw_links, list):
            raw_links = mqtt.get("links") if isinstance(mqtt, dict) else None
        if not isinstance(raw_links, list):
            return []

        names: list[str] = []
        seen: set[str] = set()
        for item in raw_links:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
        return names

    async def save_agent_mqtt(
        self,
        *,
        host: str,
        port: int,
        username: str = "",
        password: str = "",
        enabled: bool = True,
        tls_enabled: bool = False,
    ) -> dict[str, Any]:
        """POST /cgi-bin/save-agent-mqtt-config for the wormhole-agent endpoint."""
        host_value = str(host or "").strip()
        if not host_value:
            raise DeviceCgiError("MQTT host is required")
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise DeviceCgiError(f"Invalid MQTT port: {port}")

        payload = {
            "enabled": enabled,
            "host": host_value,
            "port": port,
            "username": "" if username is None else str(username),
            "password": "" if password is None else str(password),
            "tls_enabled": tls_enabled,
            "tls_cafile": "",
            "tls_certfile": "",
            "tls_keyfile": "",
        }
        data = await self._post_json("/cgi-bin/save-agent-mqtt-config", payload)
        if data.get("status") != "success":
            raise DeviceCgiError(data.get("message") or "save-agent-mqtt-config failed")
        return data

    async def save_mqtt_bridge(
        self,
        *,
        links: list[dict[str, Any]],
        connection_mode: str = "proxy",
        enabled: bool = True,
    ) -> dict[str, Any]:
        """POST /cgi-bin/save-mqtt-bridge-config for all Mosquitto bridge links."""
        if connection_mode not in ("proxy", "direct"):
            raise DeviceCgiError(f"Invalid connection_mode: {connection_mode}")
        if not links:
            raise DeviceCgiError("At least one bridge link is required")

        payload = {
            "enabled": enabled,
            "connection_mode": connection_mode,
            "links": links,
        }
        data = await self._post_json("/cgi-bin/save-mqtt-bridge-config", payload)
        if data.get("status") != "success":
            raise DeviceCgiError(data.get("message") or "save-mqtt-bridge-config failed")
        return data

    async def save_mqtt(
        self,
        *,
        host: str,
        port: str | int,
        username: str = "",
        password: str = "",
        connection_mode: str = "proxy",
        link_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Apply one broker to wormhole-agent and every Mosquitto bridge link.

        Reads existing link names from get-services-info when ``link_names`` is
        not provided, then falls back to the firmware defaults ``4g`` /
        ``wifi0`` / ``wifi1``. Writes the same host/port/credentials to the
        agent endpoint and all bridge links.
        """
        if connection_mode not in ("proxy", "direct"):
            raise DeviceCgiError(f"Invalid connection_mode: {connection_mode}")
        host_value = str(host or "").strip()
        if not host_value:
            raise DeviceCgiError("MQTT host and port are required")

        try:
            port_value = int(str(port).strip())
        except (TypeError, ValueError) as exc:
            raise DeviceCgiError(f"Invalid MQTT port: {port}") from exc
        if port_value < 1 or port_value > 65535:
            raise DeviceCgiError(f"Invalid MQTT port: {port}")

        resolved_names = list(link_names) if link_names else []
        if not resolved_names:
            try:
                services = await self.get_services_info()
                resolved_names = self.extract_bridge_link_names(services)
            except DeviceCgiError:
                resolved_names = []
        if not resolved_names:
            resolved_names = list(DEFAULT_BRIDGE_LINK_NAMES)

        username_value = "" if username is None else str(username)
        password_value = "" if password is None else str(password)

        await self.save_agent_mqtt(
            host=host_value,
            port=port_value,
            username=username_value,
            password=password_value,
            enabled=True,
            tls_enabled=False,
        )

        bridge_links = [
            {
                "name": name,
                "enabled": True,
                "host": host_value,
                "port": port_value,
                "username": username_value,
                "password": password_value,
                "tls_enabled": False,
            }
            for name in resolved_names
        ]
        await self.save_mqtt_bridge(
            links=bridge_links,
            connection_mode=connection_mode,
            enabled=True,
        )
        return {
            "status": "success",
            "link_names": resolved_names,
            "connection_mode": connection_mode,
        }

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
