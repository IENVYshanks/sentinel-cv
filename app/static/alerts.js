const alertsPanel = document.querySelector("#alerts");
const alertUpdate = document.querySelector("#alert-update");
const alertSearch = document.querySelector("#alert-search");
const alertType = document.querySelector("#alert-type");
let allAlerts = [];

function renderAlerts() {
  const query = alertSearch.value.trim().toLowerCase();
  const type = alertType.value;
  const filtered = allAlerts.filter((alert) => {
    const searchable = [alert.rule_name, alert.message, alert.camera_id, alert.metadata?.identity_name].join(" ").toLowerCase();
    return (!query || searchable.includes(query)) && (!type || alert.rule_type === type);
  });
  document.querySelector("#alert-count").textContent = `${filtered.length} result${filtered.length === 1 ? "" : "s"}`;
  alertsPanel.innerHTML = filtered.map((alert) => {
    const evidence = alert.evidence_file ? `<a class="text-link" href="/api/evidence/${encodeURIComponent(alert.evidence_file)}" target="_blank" rel="noopener">View evidence</a>` : "";
    const identity = alert.metadata?.identity_name ? `<span class="tag">${Sentinel.escapeHtml(alert.metadata.identity_name)}</span>` : "";
    return `<article class="alert-row"><div class="alert-icon">!</div><div class="alert-body"><div class="alert-title"><strong>${Sentinel.escapeHtml(alert.rule_name)}</strong><span>${Sentinel.escapeHtml(Sentinel.formatDate(alert.occurred_at))}</span></div><p>${Sentinel.escapeHtml(alert.message)} · Camera ${Sentinel.escapeHtml(alert.camera_id)}</p><div class="tag-row"><span class="tag">${Sentinel.escapeHtml(alert.rule_type)}</span>${identity}</div></div>${evidence}</article>`;
  }).join("");
  if (!filtered.length) alertsPanel.innerHTML = '<p class="empty">No alerts match the current filters.</p>';
}

async function loadAlerts() {
  try {
    allAlerts = await Sentinel.fetchJson("/api/alerts?limit=500", { cache: "no-store" });
    const types = [...new Set(allAlerts.map((alert) => alert.rule_type))].sort();
    const selected = alertType.value;
    alertType.innerHTML = '<option value="">All types</option>' + types.map((type) => `<option value="${Sentinel.escapeHtml(type)}">${Sentinel.escapeHtml(type.replaceAll("_", " "))}</option>`).join("");
    alertType.value = selected;
    renderAlerts();
    alertUpdate.textContent = "";
  } catch (error) {
    alertUpdate.textContent = error.message || "Alerts could not be loaded.";
  }
}

alertSearch.addEventListener("input", renderAlerts);
alertType.addEventListener("change", renderAlerts);
document.querySelector("#refresh-alerts").addEventListener("click", loadAlerts);
loadAlerts();
setInterval(loadAlerts, 10000);
