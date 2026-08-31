/**
 * @file i18n.js
 * @brief Frontend locale catalogs and DOM apply helpers (zh-CN / en).
 */

const I18N = {
  "zh-CN": {
    title: "Wormhole 自动配置",
    appName: "Wormhole 自动配置",
    subtitle: "配置 WiFi 与 MQTT 桥接，并通过局域网自动下发",
    configTitle: "配置",
    ssid: "WiFi SSID",
    password: "WiFi 密码",
    mqttTitle: "MQTT",
    mqttHost: "MQTT 主机",
    mqttPort: "MQTT 端口",
    mqttUsername: "MQTT 用户名",
    mqttPassword: "MQTT 密码",
    bridgeMode: "启用 MQTT 桥接模式（proxy）",
    advanced: "高级选项",
    routerIp: "路由器 IP",
    sshUsername: "SSH 用户",
    sshPort: "SSH 端口",
    sshTimeout: "SSH 超时（秒）",
    lanInterface: "LAN 网口（可选）",
    lanInterfacePlaceholder: "例如 en0 / eth0",
    lanWaitTimeout: "LAN 等待超时（秒）",
    wifiVerifyTimeout: "WiFi 验证超时（秒）",
    pollInterval: "轮询间隔（秒）",
    saveConfig: "保存配置",
    startJob: "启动自动配置",
    stopJob: "停止",
    statusTitle: "状态",
    phase: "阶段",
    message: "消息",
    lan: "LAN",
    wifiIps: "WiFi IP",
    log: "日志",
    idle: "空闲",
    configSaved: "配置已保存",
    saveFailed: "保存失败：{error}",
    startFailed: "启动失败：{error}",
    stopFailed: "停止失败：{error}",
    initFailed: "界面初始化失败：{error}",
    wifiSuccessFallback: "WiFi 连接成功",
    jobFailedFallback: "自动配置失败",
    phase_idle: "空闲",
    phase_waiting_lan: "等待局域网",
    phase_waiting_reconnect: "等待重连重试",
    phase_applying_wifi: "下发 WiFi",
    phase_applying_bridge: "下发桥接",
    phase_verifying_wifi: "验证 WiFi",
    phase_success: "成功",
    phase_failed: "失败",
    phase_cancelled: "已取消",
  },
  en: {
    title: "Wormhole Auto-Config",
    appName: "Wormhole Auto-Config",
    subtitle: "Configure WiFi & MQTT bridge, then auto-provision over LAN",
    configTitle: "Configuration",
    ssid: "WiFi SSID",
    password: "WiFi Password",
    mqttTitle: "MQTT",
    mqttHost: "MQTT Host",
    mqttPort: "MQTT Port",
    mqttUsername: "MQTT Username",
    mqttPassword: "MQTT Password",
    bridgeMode: "Enable MQTT bridge mode (proxy)",
    advanced: "Advanced",
    routerIp: "Router IP",
    sshUsername: "SSH username",
    sshPort: "SSH port",
    sshTimeout: "SSH timeout (sec)",
    lanInterface: "LAN Interface (optional)",
    lanInterfacePlaceholder: "e.g. en0 / eth0",
    lanWaitTimeout: "LAN wait timeout (sec)",
    wifiVerifyTimeout: "WiFi verify timeout (sec)",
    pollInterval: "Poll interval (sec)",
    saveConfig: "Save Config",
    startJob: "Start Auto-Config",
    stopJob: "Stop",
    statusTitle: "Status",
    phase: "Phase",
    message: "Message",
    lan: "LAN",
    wifiIps: "WiFi IPs",
    log: "Log",
    idle: "Idle",
    configSaved: "Configuration saved",
    saveFailed: "Save failed: {error}",
    startFailed: "Start failed: {error}",
    stopFailed: "Stop failed: {error}",
    initFailed: "Failed to initialize UI: {error}",
    wifiSuccessFallback: "WiFi connected successfully",
    jobFailedFallback: "Auto-config failed",
    phase_idle: "idle",
    phase_waiting_lan: "waiting LAN",
    phase_waiting_reconnect: "waiting reconnect",
    phase_applying_wifi: "applying WiFi",
    phase_applying_bridge: "applying bridge",
    phase_verifying_wifi: "verifying WiFi",
    phase_success: "success",
    phase_failed: "failed",
    phase_cancelled: "cancelled",
  },
};

const LOCALE_STORAGE_KEY = "wormhole-auto-config-locale";

/**
 * @brief Normalize a locale tag to a supported UI catalog.
 * @param {string|null|undefined} locale Raw locale
 * @returns {string} Supported locale key
 */
function normalizeUiLocale(locale) {
  if (!locale) {
    return "zh-CN";
  }
  const raw = String(locale).trim().replace("_", "-");
  const lower = raw.toLowerCase();
  if (lower.startsWith("zh")) {
    return "zh-CN";
  }
  if (lower.startsWith("en")) {
    return "en";
  }
  return I18N[raw] ? raw : "zh-CN";
}

/**
 * @brief Translate a UI key for the active locale.
 * @param {string} key Message key
 * @param {object} [params] Optional format params
 * @returns {string} Localized string
 */
function t(key, params = {}) {
  const locale = normalizeUiLocale(window.__locale || "zh-CN");
  const catalog = I18N[locale] || I18N["zh-CN"];
  let template = catalog[key] || I18N["zh-CN"][key] || key;
  Object.keys(params).forEach((name) => {
    template = template.replaceAll(`{${name}}`, String(params[name]));
  });
  return template;
}

/**
 * @brief Apply translations to elements marked with data-i18n attributes.
 * @param {string} locale Target locale
 */
function applyI18n(locale) {
  const resolved = normalizeUiLocale(locale);
  window.__locale = resolved;
  document.documentElement.lang = resolved === "zh-CN" ? "zh-CN" : "en";

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (!key) {
      return;
    }
    if (el.tagName === "TITLE") {
      document.title = t(key);
      return;
    }
    el.textContent = t(key);
  });

  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (key) {
      el.setAttribute("placeholder", t(key));
    }
  });

  document.querySelectorAll(".lang-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-locale") === resolved);
  });

  const localeInput = document.getElementById("locale");
  if (localeInput) {
    localeInput.value = resolved;
  }

  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, resolved);
  } catch (err) {
    // Ignore storage failures in private mode.
  }
}

/**
 * @brief Resolve initial UI locale from storage, config, or browser.
 * @param {string} [configLocale] Locale from persisted server config
 * @returns {string} Locale to apply
 */
function resolveInitialLocale(configLocale) {
  try {
    const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (stored) {
      return normalizeUiLocale(stored);
    }
  } catch (err) {
    // Ignore.
  }
  if (configLocale) {
    return normalizeUiLocale(configLocale);
  }
  if (typeof navigator !== "undefined" && navigator.language) {
    return normalizeUiLocale(navigator.language);
  }
  return "zh-CN";
}

window.I18n = {
  t,
  applyI18n,
  normalizeUiLocale,
  resolveInitialLocale,
  LOCALE_STORAGE_KEY,
};
