/**
 * @file app.js
 * @brief Operator UI for Wormhole auto-config: form, SSE progress, i18n, updates.
 */

const ACTIVE_PHASES = new Set([
  "waiting_lan",
  "waiting_reconnect",
  "applying_wifi",
  "applying_bridge",
  "verifying_wifi",
]);

/** @type {{ current_version: string, latest_version: string, update_available: boolean } | null} */
let lastUpdateInfo = null;

const fields = [
  "ssid",
  "password",
  "mqtt_host",
  "mqtt_port",
  "mqtt_username",
  "mqtt_password",
  "router_ip",
  "ssh_username",
  "ssh_port",
  "ssh_timeout_sec",
  "lan_interface",
  "lan_wait_timeout_sec",
  "wifi_verify_timeout_sec",
  "poll_interval_sec",
  "locale",
];

/**
 * @brief Read form values into an AppConfig-compatible object.
 * @returns {object} Config payload for the API
 */
function readForm() {
  const data = {
    bridge_mode: document.getElementById("bridge_mode").checked,
    locale: window.I18n.normalizeUiLocale(
      document.getElementById("locale").value || window.__locale
    ),
  };
  for (const name of fields) {
    if (name === "locale") {
      continue;
    }
    const el = document.getElementById(name);
    let value = el.value;
    if (el.type === "number") {
      value = value === "" ? null : Number(value);
    }
    data[name] = value;
  }
  return data;
}

/**
 * @brief Fill the form from a config object returned by the API.
 * @param {object} config Persisted configuration
 */
function fillForm(config) {
  for (const name of fields) {
    if (name === "locale") {
      continue;
    }
    const el = document.getElementById(name);
    if (config[name] !== undefined && config[name] !== null) {
      el.value = config[name];
    }
  }
  document.getElementById("bridge_mode").checked = Boolean(config.bridge_mode);
  if (config.locale) {
    document.getElementById("locale").value = window.I18n.normalizeUiLocale(config.locale);
  }
}

/**
 * @brief Localize a job phase code for display.
 * @param {string} phase Job phase enum value
 * @returns {string} Localized phase label
 */
function formatPhase(phase) {
  const key = `phase_${phase}`;
  const label = window.I18n.t(key);
  return label === key ? phase : label;
}

/**
 * @brief Update status panel and banners from a job state snapshot.
 * @param {object} state Job state from REST or SSE
 */
function renderState(state) {
  if (!state) {
    return;
  }

  const phase = state.phase || "idle";
  document.getElementById("phase").textContent = formatPhase(phase);
  document.getElementById("message").textContent =
    state.message || window.I18n.t("idle");

  const lanBits = [];
  if (state.lan_interface) {
    lanBits.push(state.lan_interface);
  }
  if (state.lan_ip) {
    lanBits.push(state.lan_ip);
  }
  document.getElementById("lan").textContent = lanBits.length ? lanBits.join(" / ") : "—";

  const wifiBits = [state.wifi_ip0, state.wifi_ip1].filter(Boolean);
  document.getElementById("wifi-ips").textContent = wifiBits.length ? wifiBits.join(" / ") : "—";

  const logEl = document.getElementById("log");
  logEl.textContent = (state.logs || []).join("\n");
  logEl.scrollTop = logEl.scrollHeight;

  const success = document.getElementById("success-banner");
  const error = document.getElementById("error-banner");
  success.classList.add("hidden");
  error.classList.add("hidden");

  if (phase === "success" || (phase === "waiting_reconnect" && !state.error && (state.wifi_ip0 || state.wifi_ip1))) {
    success.textContent = state.message || window.I18n.t("wifiSuccessFallback");
    success.classList.remove("hidden");
  } else if (phase === "failed" || (phase === "waiting_reconnect" && state.error)) {
    error.textContent =
      state.error || state.message || window.I18n.t("jobFailedFallback");
    error.classList.remove("hidden");
  }

  const running = ACTIVE_PHASES.has(phase);
  document.getElementById("start-btn").disabled = running;
  document.getElementById("stop-btn").disabled = !running;
}

/**
 * @brief Render version label and optional upgrade button from update check data.
 * @param {object|null} info Update check payload
 */
function renderUpdateInfo(info) {
  lastUpdateInfo = info;
  const versionEl = document.getElementById("current-version");
  const applyBtn = document.getElementById("apply-update-btn");
  const statusEl = document.getElementById("update-status");

  if (!info || !info.current_version) {
    versionEl.textContent = "";
    applyBtn.classList.add("hidden");
    return;
  }

  versionEl.textContent = window.I18n.t("currentVersion", {
    version: info.current_version,
  });

  if (info.update_available) {
    applyBtn.classList.remove("hidden");
    applyBtn.textContent = window.I18n.t("upgradeTo", {
      version: info.latest_version,
    });
    applyBtn.disabled = false;
    statusEl.textContent = window.I18n.t("updateAvailable", {
      version: info.latest_version,
    });
  } else {
    applyBtn.classList.add("hidden");
    statusEl.textContent = window.I18n.t("updateLatest");
  }
}

/**
 * @brief Refresh i18n-dependent update labels after a locale switch.
 */
function refreshUpdateLabels() {
  if (lastUpdateInfo) {
    renderUpdateInfo(lastUpdateInfo);
  }
  const checkBtn = document.getElementById("check-update-btn");
  if (checkBtn && !checkBtn.disabled) {
    checkBtn.textContent = window.I18n.t("checkUpdate");
  }
}

/**
 * @brief Call GET /api/update/check and update the header controls.
 */
async function checkForUpdate() {
  const statusEl = document.getElementById("update-status");
  const checkBtn = document.getElementById("check-update-btn");
  const applyBtn = document.getElementById("apply-update-btn");
  statusEl.textContent = window.I18n.t("updateChecking");
  checkBtn.disabled = true;
  applyBtn.classList.add("hidden");
  try {
    const response = await fetch("/api/update/check");
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || body.message || `HTTP ${response.status}`);
    }
    renderUpdateInfo(body);
  } catch (err) {
    statusEl.textContent = window.I18n.t("updateCheckFailed", {
      error: err.message,
    });
  } finally {
    checkBtn.disabled = false;
    checkBtn.textContent = window.I18n.t("checkUpdate");
  }
}

/**
 * @brief Poll /api/health until the service is back after restart.
 * @param {number} [timeoutMs] Overall timeout
 * @returns {Promise<void>}
 */
async function waitForHealth(timeoutMs = 60000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch("/api/health", { cache: "no-store" });
      if (response.ok) {
        return;
      }
    } catch (err) {
      // Service is restarting.
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("timeout waiting for service restart");
}

/**
 * @brief Download/install the latest wheel and wait for the process to come back.
 */
async function applyUpdate() {
  if (!lastUpdateInfo || !lastUpdateInfo.update_available) {
    return;
  }
  const statusEl = document.getElementById("update-status");
  const checkBtn = document.getElementById("check-update-btn");
  const applyBtn = document.getElementById("apply-update-btn");
  const target = lastUpdateInfo.latest_version;
  statusEl.textContent = window.I18n.t("updateApplying", { version: target });
  checkBtn.disabled = true;
  applyBtn.disabled = true;
  document.getElementById("start-btn").disabled = true;
  document.getElementById("stop-btn").disabled = true;
  document.getElementById("save-btn").disabled = true;

  try {
    const response = await fetch("/api/update/apply", { method: "POST" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || body.message || `HTTP ${response.status}`);
    }
    statusEl.textContent = window.I18n.t("updateRestarting");
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await waitForHealth();
    window.location.reload();
  } catch (err) {
    statusEl.textContent = window.I18n.t("updateApplyFailed", {
      error: err.message,
    });
    checkBtn.disabled = false;
    applyBtn.disabled = false;
    document.getElementById("save-btn").disabled = false;
  }
}

/**
 * @brief Persist current form values via PUT /api/config.
 */
async function saveConfig() {
  const response = await fetch("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(readForm()),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }
  const body = await response.json();
  fillForm(body.config);
  return body.config;
}

/**
 * @brief Start an auto-config job with the current form values.
 */
async function startJob() {
  const response = await fetch("/api/jobs/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(readForm()),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || body.message || `HTTP ${response.status}`);
  }
  renderState(body.state);
}

/**
 * @brief Request cancellation of the running job.
 */
async function stopJob() {
  const response = await fetch("/api/jobs/stop", { method: "POST" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || body.message || `HTTP ${response.status}`);
  }
  renderState(body.state);
}

/**
 * @brief Subscribe to job progress via Server-Sent Events.
 */
function connectEvents() {
  const source = new EventSource("/api/jobs/events");
  source.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.state) {
        renderState(payload.state);
      }
    } catch (err) {
      console.error("Failed to parse SSE payload", err);
    }
  };
  source.onerror = () => {
    // Browser will retry; keep UI usable via REST buttons.
  };
  return source;
}

/**
 * @brief Switch UI language and persist locale into server config when possible.
 * @param {string} locale Target locale
 */
async function switchLocale(locale) {
  const resolved = window.I18n.normalizeUiLocale(locale);
  window.I18n.applyI18n(resolved);
  refreshUpdateLabels();
  try {
    await saveConfig();
  } catch (err) {
    // Keep UI locale even if save fails (e.g. empty SSID validation not required on PUT).
    console.warn("Failed to persist locale", err);
  }
}

async function init() {
  const configRes = await fetch("/api/config");
  const configBody = await configRes.json();
  const initialLocale = window.I18n.resolveInitialLocale(configBody.config.locale);
  window.I18n.applyI18n(initialLocale);
  fillForm({ ...configBody.config, locale: initialLocale });

  const jobRes = await fetch("/api/jobs/current");
  renderState(await jobRes.json());

  connectEvents();
  await checkForUpdate();

  document.querySelectorAll(".lang-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchLocale(btn.getAttribute("data-locale"));
    });
  });

  document.getElementById("check-update-btn").addEventListener("click", () => {
    checkForUpdate().catch((err) => console.error(err));
  });
  document.getElementById("apply-update-btn").addEventListener("click", () => {
    applyUpdate().catch((err) => console.error(err));
  });

  document.getElementById("save-btn").addEventListener("click", async () => {
    try {
      await saveConfig();
      document.getElementById("message").textContent = window.I18n.t("configSaved");
    } catch (err) {
      alert(window.I18n.t("saveFailed", { error: err.message }));
    }
  });

  document.getElementById("start-btn").addEventListener("click", async () => {
    try {
      await startJob();
    } catch (err) {
      alert(window.I18n.t("startFailed", { error: err.message }));
    }
  });

  document.getElementById("stop-btn").addEventListener("click", async () => {
    try {
      await stopJob();
    } catch (err) {
      alert(window.I18n.t("stopFailed", { error: err.message }));
    }
  });
}

init().catch((err) => {
  console.error(err);
  const message =
    window.I18n && window.I18n.t
      ? window.I18n.t("initFailed", { error: err.message })
      : err.message;
  alert(message);
});
