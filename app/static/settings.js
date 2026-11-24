function renderDefinitions(target, entries) {
  target.replaceChildren();
  for (const [label, value] of entries) {
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = label;
    detail.textContent = String(value ?? "—");
    target.append(term, detail);
  }
}

async function loadSettings() {
  try {
    const system = await Sentinel.fetchJson("/api/system", { cache: "no-store" });
    renderDefinitions(document.querySelector("#runtime-settings"), [["Mode", system.mode], ["Bind address", `${system.host}:${system.port}`], ["Configured cameras", system.configured_cameras], ["Enabled cameras", system.enabled_cameras]]);
    renderDefinitions(document.querySelector("#model-settings"), [["Person detector", system.detector_model], ["Face detector", system.face_detector_model], ["Identity model", system.identity_model], ["Identity threshold", system.identity_threshold]]);
    renderDefinitions(document.querySelector("#storage-settings"), [["Database", system.database_path], ["Evidence directory", system.evidence_dir], ["Evidence retention", `${system.evidence_retention_days} days`]]);
  } catch (error) {
    document.querySelector("#settings-error").textContent = error.message || "System settings could not be loaded.";
  }
}

loadSettings();
