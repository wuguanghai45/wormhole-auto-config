"""Message catalogs and helpers for zh-CN / en localization."""

from __future__ import annotations

from typing import Any, Mapping

DEFAULT_LOCALE = "zh-CN"
SUPPORTED_LOCALES = ("zh-CN", "en")

MESSAGES: dict[str, dict[str, str]] = {
    "zh-CN": {
        "job.idle": "空闲",
        "job.no_running": "当前没有运行中的任务",
        "job.started": "任务已启动（路由器={router}，MQTT={mqtt}，桥接={bridge}）",
        "job.bridge_on": "开启",
        "job.bridge_off": "关闭",
        "job.cancel_requested": "已请求取消",
        "job.cancelled": "自动配置已取消",
        "job.cancelled_message": "自动配置已取消",
        "job.failed": "自动配置失败：{error}",
        "job.waiting_lan": "正在等待 LAN 获取 IP…",
        "job.waiting_disconnect": "配置失败，等待 LAN/设备断开以便重试…",
        "job.waiting_next_device": "配置成功，等待 LAN/设备断开后继续下一台…",
        "job.lan_disconnected": "已检测到 LAN/设备断开，等待重新连接…",
        "job.retry_after_reconnect": "LAN 已重新连接，开始第 {attempt} 次自动配置…",
        "job.lan_ready": "LAN 已就绪：{iface}（{ip}），路由器可达",
        "job.lan_status": "LAN 状态：{snapshot}",
        "job.lan_waiting_router": "已在 {iface} 获得 LAN IP {ip}，等待路由器 {router}",
        "job.applying_wifi": "正在下发 WiFi 配置…",
        "job.clearing_wifi": "正在通过 SSH 清理遗留 WiFi 配置…",
        "job.wifi_cleared": "遗留 WiFi 配置已清理",
        "job.wifi_saved": "设备端 WiFi 配置已保存",
        "job.reading_mqtt": "正在读取 MQTT 桥接链路（目标模式={mode}）…",
        "job.mqtt_unchanged": "MQTT connection_mode 已是 {mode}，跳过保存",
        "job.mqtt_links_fallback": "无法读取桥接链路列表（{error}），使用默认 4g/wifi0/wifi1",
        "job.setting_mqtt": "正在下发 MQTT（{host}:{port}，模式={mode}，链路={links}）…",
        "job.mqtt_set": "MQTT 已保存（{host}:{port}，模式={mode}，统一链路={links}）",
        "job.verifying_wifi": "正在验证 WiFi 连接…",
        "job.wifi_poll_error": "WiFi 状态查询失败：{error}",
        "job.wifi_success": "WiFi 连接成功（{ips}）",
        "job.wifi_pending": "WiFi 尚未连接（无 STA IP）",
        "job.ssid_required": "必须填写 WiFi SSID",
        "job.mqtt_required": "必须填写 MQTT 主机和端口",
        "job.already_running": "已有自动配置任务在运行",
        "job.start_ok": "自动配置已启动",
        "job.stop_ok": "已请求停止",
        "error.lan_timeout": "等待 LAN/路由器超时（{seconds} 秒）",
        "error.wifi_timeout": "验证 WiFi 超时（{seconds} 秒）",
        "error.no_mqtt_broker": "MQTT Broker 主机或端口为空，无法下发 MQTT 配置",
        "lan.no_ip_on_iface": "网口 {iface} 尚无可用 IPv4",
        "lan.none": "未发现可用的 LAN IPv4",
        "api.ok": "正常",
        "update.job_running": "自动配置任务运行中，无法升级",
        "update.apply_ok": "已安装 {version}，服务即将重启",
    },
    "en": {
        "job.idle": "Idle",
        "job.no_running": "No running job",
        "job.started": "Job started (router={router}, MQTT={mqtt}, bridge={bridge})",
        "job.bridge_on": "on",
        "job.bridge_off": "off",
        "job.cancel_requested": "Cancel requested",
        "job.cancelled": "Job cancelled",
        "job.cancelled_message": "Auto-config cancelled",
        "job.failed": "Auto-config failed: {error}",
        "job.waiting_lan": "Waiting for LAN IP...",
        "job.waiting_disconnect": "Config failed; waiting for LAN/device disconnect to retry...",
        "job.waiting_next_device": "Config succeeded; waiting for LAN/device disconnect for the next unit...",
        "job.lan_disconnected": "LAN/device disconnected; waiting for reconnect...",
        "job.retry_after_reconnect": "LAN reconnected; starting auto-config attempt {attempt}...",
        "job.lan_ready": "LAN ready on {iface} ({ip}), router reachable",
        "job.lan_status": "LAN status: {snapshot}",
        "job.lan_waiting_router": "LAN IP {ip} on {iface}, waiting for router {router}",
        "job.applying_wifi": "Applying WiFi configuration...",
        "job.clearing_wifi": "Clearing stale WiFi configuration over SSH...",
        "job.wifi_cleared": "Stale WiFi configuration cleared",
        "job.wifi_saved": "WiFi configuration saved on device",
        "job.reading_mqtt": "Reading MQTT bridge links (desired mode={mode})...",
        "job.mqtt_unchanged": "MQTT connection_mode already {mode}, skip save",
        "job.mqtt_links_fallback": "Could not read bridge links ({error}); using default 4g/wifi0/wifi1",
        "job.setting_mqtt": "Applying MQTT ({host}:{port}, mode={mode}, links={links})...",
        "job.mqtt_set": "MQTT saved ({host}:{port}, mode={mode}, unified links={links})",
        "job.verifying_wifi": "Verifying WiFi connection...",
        "job.wifi_poll_error": "WiFi status poll error: {error}",
        "job.wifi_success": "WiFi connected successfully ({ips})",
        "job.wifi_pending": "WiFi not connected yet (no STA IP)",
        "job.ssid_required": "SSID is required",
        "job.mqtt_required": "MQTT host and port are required",
        "job.already_running": "An auto-config job is already running",
        "job.start_ok": "Auto-config started",
        "job.stop_ok": "Stop requested",
        "error.lan_timeout": "Timed out waiting for LAN/router after {seconds}s",
        "error.wifi_timeout": "Timed out verifying WiFi after {seconds}s",
        "error.no_mqtt_broker": "MQTT broker host or port is empty; cannot apply MQTT config",
        "lan.no_ip_on_iface": "interface {iface} has no usable IPv4 yet",
        "lan.none": "no usable LAN IPv4 found",
        "api.ok": "ok",
        "update.job_running": "Cannot upgrade while an auto-config job is running",
        "update.apply_ok": "Installed {version}; service will restart shortly",
    },
}


def normalize_locale(locale: str | None) -> str:
    """Map a locale tag to a supported catalog key."""
    if not locale:
        return DEFAULT_LOCALE
    raw = locale.strip().replace("_", "-")
    lower = raw.lower()
    if lower.startswith("zh"):
        return "zh-CN"
    if lower.startswith("en"):
        return "en"
    if raw in MESSAGES:
        return raw
    return DEFAULT_LOCALE


def t(locale: str | None, key: str, **params: Any) -> str:
    """Translate a message key for the given locale with optional format params."""
    lang = normalize_locale(locale)
    catalog = MESSAGES.get(lang) or MESSAGES[DEFAULT_LOCALE]
    template = catalog.get(key) or MESSAGES[DEFAULT_LOCALE].get(key) or key
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, ValueError):
        return template


def translate_mapping(locale: str | None, mapping: Mapping[str, str]) -> dict[str, str]:
    """Return a dict of key -> translated string for the given locale."""
    return {key: t(locale, key) for key in mapping}
