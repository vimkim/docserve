// Shared by directory listings and document controls, including plain HTTP LANs.
let status, statusTimer, manualDialog;

function copyHost() {
  return document.activeElement?.closest("dialog[open]") || document.body;
}

function announce(message) {
  if (!status) {
    status = document.createElement("p");
    status.className = "copy-path-status";
    status.setAttribute("role", "status");
  }
  copyHost().append(status);
  clearTimeout(statusTimer);
  status.textContent = message;
  statusTimer = setTimeout(() => { status.textContent = ""; }, 3000);
}

function legacyCopy(path) {
  const active = document.activeElement;
  const selection = document.getSelection();
  const ranges = selection ? Array.from({ length: selection.rangeCount }, (_, index) => selection.getRangeAt(index).cloneRange()) : [];
  const field = document.createElement("textarea");
  field.value = path;
  field.readOnly = true;
  field.className = "copy-path-transfer";
  copyHost().append(field);
  try {
    field.focus({ preventScroll: true });
    field.select();
    return document.execCommand("copy");
  } finally {
    field.remove();
    active?.focus({ preventScroll: true });
    if (selection) {
      selection.removeAllRanges();
      for (const range of ranges) selection.addRange(range);
    }
  }
}

function showManualCopy(path) {
  if (!manualDialog) {
    manualDialog = document.createElement("dialog");
    manualDialog.className = "copy-path-dialog";
    manualDialog.setAttribute("aria-label", "Copy server path");
    manualDialog.innerHTML = `<p>Automatic copying is unavailable. Copy the selected server path:</p>
      <textarea aria-label="Server path" readonly rows="3"></textarea>
      <form method="dialog"><button type="submit">Close</button></form>`;
    document.body.append(manualDialog);
  }
  const field = manualDialog.querySelector("textarea");
  field.value = path;
  manualDialog.showModal();
  field.focus();
  field.select();
}

async function copyPath(path) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(path);
      announce("Path copied.");
      return;
    } catch { /* Try the selection-based copy when clipboard permission is denied. */ }
  }
  try {
    if (legacyCopy(path)) {
      announce("Path copied.");
      return;
    }
  } catch { /* Keep the path available even if the browser blocks both methods. */ }
  showManualCopy(path);
}

export function setCopyPath(button, path) {
  button.dataset.copyPath = path;
  button.disabled = !path;
  button.title = path || "Server path unavailable";
}

function initialize(button) {
  setCopyPath(button, button.dataset.copyPath || "");
  button.hidden = false;
  button.addEventListener("click", () => { if (button.dataset.copyPath) void copyPath(button.dataset.copyPath); });
}

export function createCopyPathButton(path = "", name = "") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "copy-path-button";
  button.textContent = "Copy path";
  button.setAttribute("aria-label", name ? `Copy path for ${name}` : "Copy path");
  button.dataset.copyPath = path;
  initialize(button);
  return button;
}

document.querySelectorAll("button[data-copy-path]").forEach(initialize);
