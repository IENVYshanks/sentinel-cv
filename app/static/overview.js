const overviewCameras = document.querySelector("#overview-cameras");
const overviewAlerts = document.querySelector("#overview-alerts");
const overviewError = document.querySelector("#overview-error");

async function loadOverview() {
  try {
    const [health, cameras, identities, alerts] = await Promise.all([
      Sentinel.fetchJson("/api/health", { cache: "no-store" }),
      Sentinel.fetchJson("/api/cameras", { cache: "no-store" }),
      Sentinel.fetchJson("/api/identities", { cache: "no-store" }),
      Sentinel.fetchJson("/api/alerts?limit=100", { cache: "no-store" }),
    ]);
    document.querySelector("#metric-health").textContent = health.status === "ok" ? "Online" : "Degraded";
    document.querySelector("#metric-mode").textContent = `${health.mode} mode`;
    document.querySelector("#metric-cameras").textContent = `${health.connected}/${health.cameras}`;
    document.querySelector("#metric-connected").textContent = "Connected cameras";
    document.querySelector("#metric-identities").textContent = identities.length;
    document.querySelector("#metric-alerts").textContent = alerts.length;

    overviewCameras.innerHTML = cameras.slice(0, 5).map((camera) => `
      <a class="compact-row" href="/cameras">
        <span class="state-dot ${camera.connected ? "good" : "bad"}"></span>
        <span><strong>${Sentinel.escapeHtml(camera.name)}</strong><small>${camera.connected ? "Live" : camera.running ? "Reconnecting" : "Stopped"}</small></span>
        <span class="row-value">${camera.frames_processed} frames</span>
      </a>`).join("");
    if (!cameras.length) overviewCameras.innerHTML = '<p class="empty">No enabled cameras.</p>';

    overviewAlerts.innerHTML = alerts.slice(0, 5).map((alert) => `
      <a class="compact-row" href="/alerts">
        <span class="state-dot warning"></span>
        <span><strong>${Sentinel.escapeHtml(alert.rule_name)}</strong><small>${Sentinel.escapeHtml(alert.message)}</small></span>
        <span class="row-value">${Sentinel.escapeHtml(Sentinel.formatDate(alert.occurred_at))}</span>
      </a>`).join("");
    if (!alerts.length) overviewAlerts.innerHTML = '<p class="empty">No alerts recorded.</p>';
    overviewError.textContent = "";
  } catch (error) {
    overviewError.textContent = error.message || "Overview could not be loaded.";
  }
}

loadOverview();
setInterval(loadOverview, 10000);
