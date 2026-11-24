const identityGrid = document.querySelector("#identity-grid");
const identityTemplate = document.querySelector("#identity-template");
const identityForm = document.querySelector("#identity-form");
const identityStatus = document.querySelector("#identity-form-status");
let identityRequestActive = false;
const sampleDialog = document.querySelector("#sample-dialog");
const sampleGrid = document.querySelector("#sample-grid");
const sampleStatus = document.querySelector("#sample-status");
let activeIdentity = null;

function fileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Photo could not be read"));
    reader.readAsDataURL(file);
  });
}

function showIdentityMessage(message, type = "error") {
  identityStatus.textContent = message;
  identityStatus.className = `update-note ${type === "success" ? "success-note" : type === "neutral" ? "neutral-note" : ""}`;
}

async function renameIdentity(identity) {
  const name = window.prompt("New display name", identity.display_name);
  if (name === null || !name.trim()) return;
  await Sentinel.fetchJson(`/api/identities/${encodeURIComponent(identity.identity_id)}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ display_name: name.trim() }),
  });
  await loadIdentities();
}

async function deleteIdentity(identity) {
  if (!window.confirm(`Delete ${identity.display_name}? This removes the stored face and embedding.`)) return;
  const response = await fetch(`/api/identities/${encodeURIComponent(identity.identity_id)}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await Sentinel.responseError(response));
  await loadIdentities();
}

function prepareReplacement(identity) {
  document.querySelector("#identity-id").value = identity.identity_id;
  document.querySelector("#identity-name").value = identity.display_name;
  document.querySelector("#identity-image").focus();
  identityForm.scrollIntoView({ behavior: "smooth", block: "center" });
  showIdentityMessage("Choose a new photo, then process and enroll.", "neutral");
}

function showSampleMessage(text, type = "error") {
  sampleStatus.textContent = text;
  sampleStatus.className = `update-note ${type === "success" ? "success-note" : type === "neutral" ? "neutral-note" : ""}`;
}

async function loadSamples() {
  if (!activeIdentity) return;
  const samples = await Sentinel.fetchJson(`/api/identities/${encodeURIComponent(activeIdentity.identity_id)}/samples`, { cache: "no-store" });
  sampleGrid.replaceChildren();
  for (const sample of samples) {
    const card = document.createElement("article");
    card.className = "sample-card";
    const image = document.createElement("img");
    image.alt = sample.primary ? "Primary reference face" : "Additional reference face";
    image.src = sample.primary
      ? `/api/identities/${encodeURIComponent(activeIdentity.identity_id)}/image?v=${encodeURIComponent(activeIdentity.updated_at)}`
      : `/api/identities/${encodeURIComponent(activeIdentity.identity_id)}/samples/${sample.sample_id}/image`;
    const details = document.createElement("div");
    const label = document.createElement("strong");
    label.textContent = sample.primary ? "Primary photo" : `Additional photo ${sample.sample_id}`;
    const date = document.createElement("small");
    date.textContent = Sentinel.formatDate(sample.created_at);
    details.append(label, date);
    card.append(image, details);
    if (sample.primary) {
      const badge = document.createElement("span");
      badge.className = "sample-protected";
      badge.textContent = "Protected";
      card.append(badge);
    } else {
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "danger-button";
      remove.textContent = "Delete";
      remove.addEventListener("click", async () => {
        if (!window.confirm("Delete this additional reference photo?")) return;
        const response = await fetch(`/api/identities/${encodeURIComponent(activeIdentity.identity_id)}/samples/${sample.sample_id}`, { method: "DELETE" });
        if (!response.ok) return showSampleMessage(await Sentinel.responseError(response));
        showSampleMessage("Photo deleted.", "success");
        await Promise.all([loadSamples(), loadIdentities()]);
      });
      card.append(remove);
    }
    sampleGrid.appendChild(card);
  }
}

async function manageSamples(identity) {
  activeIdentity = identity;
  document.querySelector("#sample-dialog-title").textContent = `${identity.display_name} photos`;
  sampleStatus.textContent = "";
  sampleDialog.showModal();
  try {
    await loadSamples();
  } catch (error) {
    showSampleMessage(error.message || "Photos could not be loaded.");
  }
}

async function loadIdentities() {
  if (identityRequestActive) return;
  identityRequestActive = true;
  try {
    const identities = await Sentinel.fetchJson("/api/identities", { cache: "no-store" });
    identityGrid.replaceChildren();
    document.querySelector("#identity-count").textContent = `${identities.length} enrolled`;
    for (const identity of identities) {
      const card = identityTemplate.content.cloneNode(true);
      card.querySelector(".identity-photo").src = `/api/identities/${encodeURIComponent(identity.identity_id)}/image?v=${encodeURIComponent(identity.updated_at)}`;
      card.querySelector(".identity-name").textContent = identity.display_name;
      card.querySelector(".identity-id").textContent = identity.identity_id;
      card.querySelector(".identity-samples").textContent = `${identity.sample_count} reference photo${identity.sample_count === 1 ? "" : "s"}`;
      card.querySelector(".identity-updated").textContent = `Updated ${Sentinel.formatDate(identity.updated_at)}`;
      card.querySelector(".manage-samples").addEventListener("click", () => manageSamples(identity));
      card.querySelector(".rename-identity").addEventListener("click", () => renameIdentity(identity).catch((error) => showIdentityMessage(error.message)));
      card.querySelector(".replace-identity").addEventListener("click", () => prepareReplacement(identity));
      card.querySelector(".delete-identity").addEventListener("click", () => deleteIdentity(identity).catch((error) => showIdentityMessage(error.message)));
      identityGrid.appendChild(card);
    }
    if (!identities.length) identityGrid.innerHTML = '<p class="empty panel">No identities enrolled.</p>';
  } finally {
    identityRequestActive = false;
  }
}

identityForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.querySelector("#identity-submit");
  const file = document.querySelector("#identity-image").files[0];
  if (!file) return;
  if (file.size > 10_000_000) return showIdentityMessage("Photo must be 10 MB or smaller.");
  button.disabled = true;
  showIdentityMessage("Detecting face and generating embedding…", "neutral");
  try {
    const imageBase64 = await fileAsDataUrl(file);
    await Sentinel.fetchJson("/api/identities", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ identity_id: document.querySelector("#identity-id").value.trim(), display_name: document.querySelector("#identity-name").value.trim(), image_base64: imageBase64 }),
    });
    identityForm.reset();
    showIdentityMessage("Identity enrolled successfully.", "success");
    await loadIdentities();
  } catch (error) {
    showIdentityMessage(error.message || "Enrollment failed.");
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#sample-dialog-close").addEventListener("click", () => sampleDialog.close());

document.querySelector("#sample-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!activeIdentity) return;
  const button = document.querySelector("#sample-submit");
  const file = document.querySelector("#sample-image").files[0];
  if (!file) return;
  if (file.size > 10_000_000) return showSampleMessage("Photo must be 10 MB or smaller.");
  button.disabled = true;
  showSampleMessage("Detecting face and generating embedding…", "neutral");
  try {
    const imageBase64 = await fileAsDataUrl(file);
    await Sentinel.fetchJson(`/api/identities/${encodeURIComponent(activeIdentity.identity_id)}/samples`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ image_base64: imageBase64 }) });
    document.querySelector("#sample-form").reset();
    showSampleMessage("Reference photo added.", "success");
    await Promise.all([loadSamples(), loadIdentities()]);
  } catch (error) {
    showSampleMessage(error.message || "Photo could not be added.");
  } finally {
    button.disabled = false;
  }
});

loadIdentities();
