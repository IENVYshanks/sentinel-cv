const form = document.querySelector("#video-test-form");
const fileInput = document.querySelector("#video-file");
const submitButton = document.querySelector("#video-submit");
const cancelButton = document.querySelector("#video-cancel");
const message = document.querySelector("#video-message");
const preview = document.querySelector("#video-stream");
const placeholder = document.querySelector("#video-placeholder");
let jobId = localStorage.getItem("sentinel-video-test-job");
let pollTimer = null;

function showMessage(text, type = "neutral") {
  message.textContent = text;
  message.className = `update-note ${type === "error" ? "" : type === "success" ? "success-note" : "neutral-note"}`;
}

function updateStatus(status) {
  document.querySelector("#video-filename").textContent = status.filename;
  document.querySelector("#video-state").textContent = status.state;
  document.querySelector("#video-state").className = `status ${status.state === "completed" ? "online" : status.state === "failed" || status.state === "canceled" ? "offline" : ""}`;
  document.querySelector("#video-progress").style.width = `${status.progress}%`;
  document.querySelector("#video-percent").textContent = `${status.progress.toFixed(1)}%`;
  document.querySelector("#video-frames").textContent = `${status.frames_processed} / ${status.total_frames || "?"}`;
  document.querySelector("#video-identities").textContent = status.recognized_identities.join(", ") || "None";
  if (status.error) showMessage(status.error, "error");
  const terminal = ["completed", "failed", "canceled"].includes(status.state);
  cancelButton.disabled = terminal;
  submitButton.disabled = !terminal;
  if (terminal) {
    clearInterval(pollTimer);
    pollTimer = null;
    localStorage.removeItem("sentinel-video-test-job");
    if (status.state === "completed") showMessage("Video processing completed.", "success");
  }
}

async function pollStatus() {
  if (!jobId) return;
  try {
    const status = await Sentinel.fetchJson(`/api/video-tests/${encodeURIComponent(jobId)}`, { cache: "no-store" });
    updateStatus(status);
  } catch (error) {
    clearInterval(pollTimer);
    pollTimer = null;
    localStorage.removeItem("sentinel-video-test-job");
    jobId = null;
    submitButton.disabled = false;
    cancelButton.disabled = true;
    showMessage(error.message || "Video test could not be loaded.", "error");
  }
}

function beginPolling() {
  clearInterval(pollTimer);
  pollStatus();
  pollTimer = setInterval(pollStatus, 1000);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;
  if (file.size > 250 * 1024 * 1024) return showMessage("Video must be 250 MB or smaller.", "error");
  submitButton.disabled = true;
  showMessage("Uploading video…");
  try {
    const response = await fetch(`/api/video-tests?filename=${encodeURIComponent(file.name)}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
    if (!response.ok) throw new Error(await Sentinel.responseError(response));
    const status = await response.json();
    jobId = status.id;
    localStorage.setItem("sentinel-video-test-job", jobId);
    preview.src = `/api/video-tests/${encodeURIComponent(jobId)}/stream?v=${Date.now()}`;
    preview.hidden = false;
    placeholder.hidden = true;
    cancelButton.disabled = false;
    updateStatus(status);
    if (!["completed", "failed", "canceled"].includes(status.state)) beginPolling();
  } catch (error) {
    submitButton.disabled = false;
    showMessage(error.message || "Video upload failed.", "error");
  }
});

cancelButton.addEventListener("click", async () => {
  if (!jobId) return;
  const response = await fetch(`/api/video-tests/${encodeURIComponent(jobId)}`, { method: "DELETE" });
  if (!response.ok) return showMessage(await Sentinel.responseError(response), "error");
  showMessage("Video test canceled.");
  await pollStatus();
});

if (jobId) {
  preview.src = `/api/video-tests/${encodeURIComponent(jobId)}/stream?v=${Date.now()}`;
  preview.hidden = false;
  placeholder.hidden = true;
  submitButton.disabled = true;
  cancelButton.disabled = false;
  beginPolling();
}
