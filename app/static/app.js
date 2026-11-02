const cameraGrid = document.querySelector("#camera-grid");
const alertsPanel = document.querySelector("#alerts");
const statusBadge = document.querySelector("#system-status");
const cameraTemplate = document.querySelector("#camera-template");

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = String(value ?? "");
  return div.innerHTML;
}

async function loadCameras() {
  const response = await fetch("/api/cameras");
  if (!response.ok) throw new Error("Camera status request failed");
  const cameras = await response.json();
  cameraGrid.replaceChildren();
  for (const camera of cameras) {
    const card = cameraTemplate.content.cloneNode(true);
    card.querySelector("h3").textContent = camera.name;
    card.querySelector(".camera-id").textContent = camera.id;
    const state = card.querySelector(".camera-state");
    state.textContent = camera.connected ? "Live" : "Offline";
    state.classList.add(camera.connected ? "online" : "offline");
    card.querySelector(".camera-error").textContent = camera.last_error || `${camera.frames_processed} frames processed`;
    const image = card.querySelector("img");
    image.src = `/api/cameras/${encodeURIComponent(camera.id)}/stream`;
    cameraGrid.appendChild(card);
  }
  if (!cameras.length) cameraGrid.innerHTML = '<p class="empty">No enabled cameras configured.</p>';
}

async function loadAlerts() {
  const response = await fetch("/api/alerts?limit=50");
  if (!response.ok) throw new Error("Alert request failed");
  const alerts = await response.json();
  alertsPanel.innerHTML = alerts.map((alert) => {
    const time = new Date(alert.occurred_at).toLocaleString();
    const evidence = alert.evidence_file
      ? `<a href="/api/evidence/${encodeURIComponent(alert.evidence_file)}" target="_blank" rel="noopener">View evidence</a>`
      : "";
    return `<article class="alert-row">
      <div class="alert-icon">!</div>
      <div class="alert-body">
        <div class="alert-title"><strong>${escapeHtml(alert.rule_name)}</strong><span>${escapeHtml(time)}</span></div>
        <p>${escapeHtml(alert.message)} · Camera ${escapeHtml(alert.camera_id)}</p>
      </div>
      ${evidence}
    </article>`;
  }).join("");
  if (!alerts.length) alertsPanel.innerHTML = '<p class="empty">No alerts have been recorded.</p>';
}

async function refresh() {
  try {
    await Promise.all([loadCameras(), loadAlerts()]);
    statusBadge.textContent = "System online";
    statusBadge.className = "status online";
  } catch (error) {
    statusBadge.textContent = "Connection error";
    statusBadge.className = "status offline";
    console.error(error);
  }
}

document.querySelector("#refresh").addEventListener("click", refresh);
refresh();
setInterval(loadAlerts, 5000);
setInterval(loadCameras, 15000);

