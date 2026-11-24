if (document.body.dataset.page === "legacy") {
const cameraGrid = document.querySelector("#camera-grid");
const alertsPanel = document.querySelector("#alerts");
const statusBadge = document.querySelector("#system-status");
const cameraTemplate = document.querySelector("#camera-template");
const cameraUpdate = document.querySelector("#camera-update");
const alertUpdate = document.querySelector("#alert-update");
const identityGrid = document.querySelector("#identity-grid");
const identityTemplate = document.querySelector("#identity-template");
const identityForm = document.querySelector("#identity-form");
const identityFormStatus = document.querySelector("#identity-form-status");
const identityCount = document.querySelector("#identity-count");
let cameraRequestActive = false;
let alertRequestActive = false;
let identityRequestActive = false;

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = String(value ?? "");
  return div.innerHTML;
}

async function loadCameras() {
  if (cameraRequestActive) return;
  cameraRequestActive = true;
  try {
    const response = await fetch("/api/cameras", { cache: "no-store" });
    if (!response.ok) throw new Error("Camera status request failed");
    const cameras = await response.json();
    cameraGrid.replaceChildren();
    for (const camera of cameras) {
      const card = cameraTemplate.content.cloneNode(true);
      card.querySelector("h3").textContent = camera.name;
      card.querySelector(".camera-id").textContent = camera.id;
      const state = card.querySelector(".camera-state");
      state.textContent = camera.connected ? "Live" : camera.running ? "Reconnecting" : "Stopped";
      state.classList.add(camera.connected ? "online" : "offline");
      const faceStatus = camera.face_detection_enabled
        ? ` · ${camera.faces_detected} face${camera.faces_detected === 1 ? "" : "s"} detected`
        : "";
      const identityStatus = camera.identity_detection_enabled && camera.recognized_identities.length
        ? ` · Recognized: ${camera.recognized_identities.join(", ")}`
        : "";
      card.querySelector(".camera-error").textContent = camera.last_error || `${camera.frames_processed} frames processed${faceStatus}${identityStatus}`;
      const image = card.querySelector("img");
      if (camera.running) image.src = `/api/cameras/${encodeURIComponent(camera.id)}/stream`;
      cameraGrid.appendChild(card);
    }
    if (!cameras.length) cameraGrid.innerHTML = '<p class="empty">No enabled cameras configured.</p>';
    cameraUpdate.textContent = "";
  } catch (error) {
    cameraUpdate.textContent = "Camera status could not be refreshed.";
    throw error;
  } finally {
    cameraRequestActive = false;
  }
}

async function loadAlerts() {
  if (alertRequestActive) return;
  alertRequestActive = true;
  try {
    const response = await fetch("/api/alerts?limit=50", { cache: "no-store" });
    if (!response.ok) throw new Error("Alert request failed");
    const alerts = await response.json();
    alertsPanel.innerHTML = alerts.map((alert) => {
      const time = new Date(alert.occurred_at).toLocaleString();
      const evidence = alert.evidence_file
        ? `<a href="/api/evidence/${encodeURIComponent(alert.evidence_file)}" target="_blank" rel="noopener">View evidence</a>`
        : "";
      const identity = alert.metadata?.identity_name
        ? ` · Identity: ${escapeHtml(alert.metadata.identity_name)}`
        : "";
      return `<article class="alert-row">
        <div class="alert-icon">!</div>
        <div class="alert-body">
          <div class="alert-title"><strong>${escapeHtml(alert.rule_name)}</strong><span>${escapeHtml(time)}</span></div>
          <p>${escapeHtml(alert.message)} · Camera ${escapeHtml(alert.camera_id)}${identity}</p>
        </div>
        ${evidence}
      </article>`;
    }).join("");
    if (!alerts.length) alertsPanel.innerHTML = '<p class="empty">No alerts have been recorded.</p>';
    alertUpdate.textContent = "";
  } catch (error) {
    alertUpdate.textContent = "Alerts could not be refreshed.";
    throw error;
  } finally {
    alertRequestActive = false;
  }
}

function fileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Photo could not be read"));
    reader.readAsDataURL(file);
  });
}

async function responseError(response) {
  try {
    const payload = await response.json();
    return payload.detail || "Request failed";
  } catch (_) {
    return "Request failed";
  }
}

function showIdentityError(error) {
  identityFormStatus.textContent = error.message || "Identity operation failed.";
  identityFormStatus.className = "update-note";
  console.error(error);
}

async function renameIdentity(identity) {
  const displayName = window.prompt("New display name", identity.display_name);
  if (displayName === null || !displayName.trim()) return;
  const response = await fetch(`/api/identities/${encodeURIComponent(identity.identity_id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: displayName.trim() }),
  });
  if (!response.ok) throw new Error(await responseError(response));
  await loadIdentities();
}

async function deleteIdentity(identity) {
  const confirmed = window.confirm(`Delete ${identity.display_name}? This removes the stored face and embedding.`);
  if (!confirmed) return;
  const response = await fetch(`/api/identities/${encodeURIComponent(identity.identity_id)}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(await responseError(response));
  await loadIdentities();
}

function prepareReplacement(identity) {
  document.querySelector("#identity-id").value = identity.identity_id;
  document.querySelector("#identity-name").value = identity.display_name;
  document.querySelector("#identity-image").focus();
  identityForm.scrollIntoView({ behavior: "smooth", block: "center" });
  identityFormStatus.textContent = "Choose a new photo, then process and enroll.";
  identityFormStatus.className = "update-note neutral-note";
}

async function loadIdentities() {
  if (identityRequestActive) return;
  identityRequestActive = true;
  try {
    const response = await fetch("/api/identities", { cache: "no-store" });
    if (!response.ok) throw new Error(await responseError(response));
    const identities = await response.json();
    identityGrid.replaceChildren();
    identityCount.textContent = `${identities.length} enrolled`;
    for (const identity of identities) {
      const card = identityTemplate.content.cloneNode(true);
      card.querySelector(".identity-photo").src = `/api/identities/${encodeURIComponent(identity.identity_id)}/image?v=${encodeURIComponent(identity.updated_at)}`;
      card.querySelector(".identity-name").textContent = identity.display_name;
      card.querySelector(".identity-id").textContent = identity.identity_id;
      card.querySelector(".identity-updated").textContent = `Updated ${new Date(`${identity.updated_at}Z`).toLocaleString()}`;
      card.querySelector(".rename-identity").addEventListener("click", () => renameIdentity(identity).catch(showIdentityError));
      card.querySelector(".replace-identity").addEventListener("click", () => prepareReplacement(identity));
      card.querySelector(".delete-identity").addEventListener("click", () => deleteIdentity(identity).catch(showIdentityError));
      identityGrid.appendChild(card);
    }
    if (!identities.length) identityGrid.innerHTML = '<p class="empty">No identities enrolled.</p>';
  } finally {
    identityRequestActive = false;
  }
}

identityForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = document.querySelector("#identity-submit");
  const file = document.querySelector("#identity-image").files[0];
  if (!file) return;
  if (file.size > 10_000_000) {
    showIdentityError(new Error("Photo must be 10 MB or smaller."));
    return;
  }
  submitButton.disabled = true;
  identityFormStatus.textContent = "Detecting face and generating embedding…";
  identityFormStatus.className = "update-note neutral-note";
  try {
    const imageBase64 = await fileAsDataUrl(file);
    const response = await fetch("/api/identities", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        identity_id: document.querySelector("#identity-id").value.trim(),
        display_name: document.querySelector("#identity-name").value.trim(),
        image_base64: imageBase64,
      }),
    });
    if (!response.ok) throw new Error(await responseError(response));
    identityForm.reset();
    identityFormStatus.textContent = "Identity enrolled successfully.";
    identityFormStatus.className = "update-note success-note";
    await loadIdentities();
  } catch (error) {
    showIdentityError(error);
  } finally {
    submitButton.disabled = false;
  }
});

async function refresh() {
  try {
    await Promise.all([loadCameras(), loadAlerts(), loadIdentities()]);
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
setInterval(() => loadAlerts().catch(console.error), 5000);
setInterval(() => loadCameras().catch(console.error), 15000);
}

function shellEscapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = String(value ?? "");
  return div.innerHTML;
}

async function shellResponseError(response) {
  try {
    const payload = await response.json();
    return payload.detail || "Request failed";
  } catch (_) {
    return "Request failed";
  }
}

async function shellFetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(await shellResponseError(response));
  return response.json();
}

function shellFormatDate(value) {
  if (!value) return "—";
  const normalized = value.includes("T") ? value : `${value.replace(" ", "T")}Z`;
  return new Date(normalized).toLocaleString();
}

async function loadGlobalStatus() {
  const badge = document.querySelector("#global-system-status");
  if (!badge) return;
  try {
    const health = await shellFetchJson("/api/health", { cache: "no-store" });
    badge.textContent = health.status === "ok" ? "System online" : "Needs attention";
    badge.className = `status ${health.status === "ok" ? "online" : "offline"}`;
  } catch (error) {
    badge.textContent = "Service unavailable";
    badge.className = "status offline";
  }
}

document.querySelectorAll("[data-nav]").forEach((link) => {
  if (link.dataset.nav === document.body.dataset.page) {
    link.classList.add("active");
    link.setAttribute("aria-current", "page");
  }
});

window.Sentinel = {
  escapeHtml: shellEscapeHtml,
  fetchJson: shellFetchJson,
  responseError: shellResponseError,
  formatDate: shellFormatDate,
};

loadGlobalStatus();
setInterval(loadGlobalStatus, 15000);

