/**
 * @file app.js
 * @brief Operator UI for Wormhole auto-config: form, SSE progress, i18n.
 */

const ACTIVE_PHASES = new Set([
  "waiting_lan",
  "waiting_reconnect",
  "applying_wifi",
  "applying_bridge",
  "verifying_wifi",
]);

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

  document.querySelectorAll(".lang-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchLocale(btn.getAttribute("data-locale"));
    });
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
