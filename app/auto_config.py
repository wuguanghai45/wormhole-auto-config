"""Auto-config job state machine with SSE fan-out."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Optional

from app.config import AppConfig, load_config
from app.device_cgi import DeviceCgiClient, DeviceCgiError
from app.device_ssh import DeviceSshClient
from app.i18n import normalize_locale, t
from app.lan_monitor import find_lan_address, format_lan_snapshot
from app.models import JobPhase, JobState, utc_now


class AutoConfigService:
    """Runs a single auto-config job and publishes state updates."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task[None]] = None
        self._cancel_requested = False
        self._locale = normalize_locale(None)
        self._state = JobState(message=t(self._locale, "job.idle"), locale=self._locale)
        self._subscribers: list[asyncio.Queue[JobState]] = []

    def current(self) -> JobState:
        """Return a copy of the current job state."""
        return self._state.model_copy(deep=True)

    def subscribe(self) -> asyncio.Queue[JobState]:
        """Register an SSE subscriber queue and push the current state."""
        queue: asyncio.Queue[JobState] = asyncio.Queue(maxsize=32)
        self._subscribers.append(queue)
        try:
            queue.put_nowait(self.current())
        except asyncio.QueueFull:
            pass
        return queue

    def unsubscribe(self, queue: asyncio.Queue[JobState]) -> None:
        """Remove an SSE subscriber queue."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def _publish(self) -> None:
        snapshot = self.current()
        dead: list[asyncio.Queue[JobState]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(snapshot)
            except asyncio.QueueFull:
                try:
                    _ = queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(snapshot)
                except asyncio.QueueFull:
                    dead.append(queue)
        for queue in dead:
            self.unsubscribe(queue)

    def _msg(self, key: str, **params: Any) -> str:
        return t(self._locale, key, **params)

    def _set_phase(self, phase: JobPhase, key: str, **params: Any) -> None:
        message = self._msg(key, **params)
        self._state.phase = phase
        self._state.message = message
        self._state.locale = self._locale
        self._state.updated_at = utc_now()
        self._state.append_log(message)
        self._publish()

    def _log(self, key: str, **params: Any) -> None:
        self._state.append_log(self._msg(key, **params))
        self._publish()

    def _running(self) -> bool:
        return self._task is not None and not self._task.done()

    def is_running(self) -> bool:
        """Return True when an auto-config job task is active."""
        return self._running()

    async def start(self, config: Optional[AppConfig] = None) -> JobState:
        """Start a new auto-config job if none is running."""
        async with self._lock:
            cfg = config or load_config()
            locale = normalize_locale(cfg.locale)
            if self._running():
                raise RuntimeError(t(locale, "job.already_running"))
            self._locale = locale
            if not cfg.ssid.strip():
                raise ValueError(t(self._locale, "job.ssid_required"))
            if not cfg.mqtt_host.strip() or not str(cfg.mqtt_port).strip():
                raise ValueError(t(self._locale, "job.mqtt_required"))
            self._cancel_requested = False
            bridge_label = self._msg(
                "job.bridge_on" if cfg.bridge_mode else "job.bridge_off"
            )
            self._state = JobState(
                phase=JobPhase.WAITING_LAN,
                message=self._msg("job.waiting_lan"),
                locale=self._locale,
                started_at=utc_now(),
                updated_at=utc_now(),
            )
            self._state.append_log(
                self._msg(
                    "job.started",
                    router=cfg.router_ip,
                    bridge=bridge_label,
                    mqtt=cfg.mqtt_host.strip(),
                )
            )
            self._publish()
            self._task = asyncio.create_task(self._run(cfg), name="auto-config-job")
            return self.current()

    async def stop(self) -> JobState:
        """Request cancellation of the running job."""
        async with self._lock:
            if not self._running():
                self._state.message = self._msg("job.no_running")
                self._state.locale = self._locale
                return self.current()
            self._cancel_requested = True
            self._log("job.cancel_requested")
            task = self._task
        if task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        return self.current()

    def _check_cancel(self) -> None:
        if self._cancel_requested:
            raise asyncio.CancelledError()

    async def _run(self, config: AppConfig) -> None:
        """Keep configuring devices until cancelled: success or failure both await reconnect."""
        attempt = 0
        try:
            while True:
                attempt += 1
                if attempt > 1:
                    self._state.error = None
                    self._state.wifi_ip0 = None
                    self._state.wifi_ip1 = None
                    self._state.finished_at = None
                    self._log("job.retry_after_reconnect", attempt=attempt)

                try:
                    await self._wait_for_lan(config)
                    self._check_cancel()
                    await self._configure_device(config)
                    await self._wait_for_lan_disconnect(
                        config,
                        message_key="job.waiting_next_device",
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - retry after LAN reconnect
                    error_text = str(exc)
                    self._state.phase = JobPhase.FAILED
                    self._state.message = self._msg("job.failed", error=error_text)
                    self._state.error = error_text
                    self._state.finished_at = utc_now()
                    self._state.updated_at = utc_now()
                    self._state.append_log(self._state.message)
                    self._publish()
                    await self._wait_for_lan_disconnect(
                        config,
                        message_key="job.waiting_disconnect",
                    )
        except asyncio.CancelledError:
            self._state.phase = JobPhase.CANCELLED
            self._state.message = self._msg("job.cancelled_message")
            self._state.finished_at = utc_now()
            self._state.updated_at = utc_now()
            self._state.append_log(self._msg("job.cancelled"))
            self._publish()

    async def _configure_device(self, config: AppConfig) -> None:
        """Clear stale WiFi sections, then apply WiFi, MQTT, and verify connectivity."""
        client = DeviceCgiClient(config.router_ip, config.http_timeout_sec)
        ssh_client = DeviceSshClient(
            config.router_ip,
            username=config.ssh_username.strip() or "root",
            port=config.ssh_port,
            timeout_sec=config.ssh_timeout_sec,
        )

        self._set_phase(JobPhase.APPLYING_WIFI, "job.applying_wifi")
        self._log("job.clearing_wifi")
        await ssh_client.clear_stale_wifi_networks()
        self._log("job.wifi_cleared")
        self._check_cancel()

        await client.save_wifi(config.ssid.strip(), config.password)
        self._log("job.wifi_saved")
        self._check_cancel()

        await self._apply_mqtt(client, config)
        self._check_cancel()

        await self._verify_wifi(client, config)

    async def _router_reachable(self, config: AppConfig) -> bool:
        """Return True when the preferred LAN has IP and the router CGI responds."""
        lan = find_lan_address(config.lan_interface)
        if lan is None:
            return False
        client = DeviceCgiClient(config.router_ip, config.http_timeout_sec)
        return await client.probe_reachable()

    async def _wait_for_lan_disconnect(
        self,
        config: AppConfig,
        *,
        message_key: str,
    ) -> None:
        """Wait until LAN/router is no longer reachable before the next attempt."""
        self._set_phase(JobPhase.WAITING_RECONNECT, message_key)
        while True:
            self._check_cancel()
            if not await self._router_reachable(config):
                self._log("job.lan_disconnected")
                return
            await asyncio.sleep(config.poll_interval_sec)

    async def _wait_for_lan(self, config: AppConfig) -> None:
        self._set_phase(JobPhase.WAITING_LAN, "job.waiting_lan")
        deadline = time.monotonic() + config.lan_wait_timeout_sec
        client = DeviceCgiClient(config.router_ip, config.http_timeout_sec)
        last_snapshot = ""

        while True:
            self._check_cancel()
            lan = find_lan_address(config.lan_interface)
            snapshot = format_lan_snapshot(config.lan_interface, self._locale)
            if snapshot != last_snapshot:
                self._log("job.lan_status", snapshot=snapshot)
                last_snapshot = snapshot

            if lan is not None:
                reachable = await client.probe_reachable()
                if reachable:
                    self._state.lan_ip = lan.ip
                    self._state.lan_interface = lan.interface
                    self._set_phase(
                        JobPhase.WAITING_LAN,
                        "job.lan_ready",
                        iface=lan.interface,
                        ip=lan.ip,
                    )
                    return
                self._log(
                    "job.lan_waiting_router",
                    ip=lan.ip,
                    iface=lan.interface,
                    router=config.router_ip,
                )

            if time.monotonic() >= deadline:
                raise TimeoutError(
                    self._msg("error.lan_timeout", seconds=config.lan_wait_timeout_sec)
                )
            await asyncio.sleep(config.poll_interval_sec)

    async def _apply_mqtt(
        self,
        client: DeviceCgiClient,
        config: AppConfig,
    ) -> None:
        """Save MQTT via legacy CGI using operator-provided broker settings."""
        desired_mode = "proxy" if config.bridge_mode else "direct"
        host = config.mqtt_host.strip()
        port = str(config.mqtt_port).strip()
        if not host or not port:
            raise DeviceCgiError(self._msg("error.no_mqtt_broker"))

        self._set_phase(
            JobPhase.APPLYING_BRIDGE,
            "job.setting_mqtt",
            mode=desired_mode,
            host=host,
            port=port,
        )
        await client.save_mqtt(
            host=host,
            port=port,
            username=config.mqtt_username,
            password=config.mqtt_password,
            connection_mode=desired_mode,
        )
        self._log("job.mqtt_set", mode=desired_mode, host=host, port=port)

    async def _verify_wifi(self, client: DeviceCgiClient, config: AppConfig) -> None:
        self._set_phase(JobPhase.VERIFYING_WIFI, "job.verifying_wifi")
        deadline = time.monotonic() + config.wifi_verify_timeout_sec

        while True:
            self._check_cancel()
            try:
                status = await client.get_network_status()
            except DeviceCgiError as exc:
                self._log("job.wifi_poll_error", error=str(exc))
            else:
                ip0, ip1 = client.wifi_ips(status)
                self._state.wifi_ip0 = ip0 or None
                self._state.wifi_ip1 = ip1 or None
                if client.has_wifi_ip(status):
                    ips = " / ".join(ip for ip in (ip0, ip1) if ip)
                    self._state.phase = JobPhase.SUCCESS
                    self._state.message = self._msg("job.wifi_success", ips=ips)
                    self._state.error = None
                    self._state.finished_at = utc_now()
                    self._state.updated_at = utc_now()
                    self._state.append_log(self._state.message)
                    self._publish()
                    return
                self._log("job.wifi_pending")

            if time.monotonic() >= deadline:
                raise TimeoutError(
                    self._msg(
                        "error.wifi_timeout",
                        seconds=config.wifi_verify_timeout_sec,
                    )
                )
            await asyncio.sleep(config.poll_interval_sec)


async def sse_event_stream(service: AutoConfigService) -> AsyncIterator[str]:
    """Yield SSE-formatted job state events."""
    queue = service.subscribe()
    try:
        while True:
            state = await queue.get()
            payload = json.dumps(
                {"type": "state", "state": state.model_dump(mode="json")},
                ensure_ascii=False,
            )
            yield f"data: {payload}\n\n"
    finally:
        service.unsubscribe(queue)
