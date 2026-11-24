const cameraGrid = document.querySelector("#camera-grid");
const cameraTemplate = document.querySelector("#camera-template");
const cameraUpdate = document.querySelector("#camera-update");
let cameraRequestActive = false;

async function loadCameras() {
  if (cameraRequestActive) return;
  cameraRequestActive = true;
  try {
    const cameras = await Sentinel.fetchJson("/api/cameras", { cache: "no-store" });
    cameraGrid.replaceChildren();
    for (const camera of cameras) {
      const card = cameraTemplate.content.cloneNode(true);
      card.querySelector("h3").textContent = camera.name;
      card.querySelector(".camera-id").textContent = camera.id;
      const state = card.querySelector(".camera-state");
      state.textContent = camera.connected ? "Live" : camera.running ? "Reconnecting" : "Stopped";
      state.classList.add(camera.connected ? "online" : "offline");
      const faces = camera.face_detection_enabled ? ` · ${camera.faces_detected} face${camera.faces_detected === 1 ? "" : "s"}` : "";
      const identities = camera.recognized_identities.length ? ` · Recognized: ${camera.recognized_identities.join(", ")}` : "";
      card.querySelector(".camera-error").textContent = camera.last_error || `${camera.frames_processed} frames processed${faces}${identities}`;
      if (camera.running) card.querySelector("img").src = `/api/cameras/${encodeURIComponent(camera.id)}/stream`;
      cameraGrid.appendChild(card);
    }
    if (!cameras.length) cameraGrid.innerHTML = '<p class="empty panel">No enabled cameras configured.</p>';
    cameraUpdate.textContent = "";
  } catch (error) {
    cameraUpdate.textContent = error.message || "Camera status could not be loaded.";
  } finally {
    cameraRequestActive = false;
  }
}

document.querySelector("#refresh-cameras").addEventListener("click", loadCameras);
loadCameras();
setInterval(loadCameras, 15000);
