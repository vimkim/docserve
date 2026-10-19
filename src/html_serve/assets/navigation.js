import "./copy-path.js";

const tools = document.getElementById("navigation-tools");
const labels = { files: "Find files", contents: "Find contents", directories: "Find directories", recent: "Recently visited", updated: "Recently updated" };
tools.innerHTML = `
  <div class="finder-buttons">
    <button type="button" data-find="files">Find files</button>
    <button type="button" data-find="contents">Find contents</button>
    <button type="button" data-find="directories">Find directories</button>
    <button type="button" data-find="recent">Recently visited</button>
    <button type="button" data-find="updated">Recently updated</button>
  </div>
  <dialog id="finder" aria-labelledby="finder-title">
    <div class="finder-heading"><h2 id="finder-title">Find files</h2><button type="button" id="finder-close">Close</button></div>
    <div role="tablist" aria-label="Find by">
      <button type="button" role="tab" data-mode="files">Files</button>
      <button type="button" role="tab" data-mode="contents">Contents</button>
      <button type="button" role="tab" data-mode="directories">Directories</button>
      <button type="button" role="tab" data-mode="recent">Recent</button>
      <button type="button" role="tab" data-mode="updated">Updated</button>
    </div>
    <input id="finder-query" type="search" aria-label="Search query" placeholder="Type to search…" autocomplete="off" spellcheck="false">
    <div id="finder-options">
      <label>Search in <select id="finder-scope" aria-label="Search scope"><option value="root">Serving root</option><option value="current">Current directory</option></select></label>
      <label><input id="finder-include" type="checkbox"> Include hidden and ignored</label>
      <label id="finder-regex-label" hidden><input id="finder-regex" type="checkbox"> Regex</label>
    </div>
    <div id="finder-filename-filters" hidden>
      <label>Include filenames (regex)<input id="finder-filename" type="text" placeholder="e.g. \\.md$" maxlength="500" autocomplete="off" spellcheck="false" aria-describedby="finder-filename-help"></label>
      <label>Exclude filenames (regex)<input id="finder-exclude-filename" type="text" placeholder="e.g. ^draft" maxlength="500" autocomplete="off" spellcheck="false" aria-describedby="finder-filename-help"></label>
      <p id="finder-filename-help">Optional. Match filenames only. Lowercase patterns ignore case; uppercase makes them case-sensitive. Exclude wins.</p>
    </div>
    <div id="finder-recent-options" hidden>
      <label>Show <select id="finder-recent-kind" aria-label="Recent visit type"><option value="all">All</option><option value="file">Files only</option><option value="directory">Directories only</option></select></label>
    </div>
    <div class="finder-search-status">
      <progress id="finder-progress" aria-label="Search in progress" hidden></progress>
      <p id="finder-status" role="status" aria-live="polite"></p>
      <span id="finder-elapsed" role="timer" aria-live="off" hidden></span>
    </div>
    <div class="finder-panes">
      <ul id="finder-results" role="listbox" aria-label="Search results" tabindex="0"></ul>
      <section class="finder-preview-pane" aria-label="File preview">
        <div class="finder-preview-heading"><span id="finder-path"></span><div class="finder-preview-actions">
          <label id="finder-preview-format-label" hidden>View <select id="finder-preview-format" aria-label="Preview format"><option value="rendered">Rendered</option><option value="source">Source</option></select></label>
          <a id="finder-open" hidden>Open</a>
        </div></div>
        <p id="finder-preview-status" role="status"></p><div id="finder-preview"></div>
      </section>
    </div>
    <p class="finder-help">↑ ↓ select · Enter opens · Escape closes · Click a result to preview</p>
  </dialog>`;
tools.hidden = false;

const dialog = document.getElementById("finder");
const query = document.getElementById("finder-query");
const list = document.getElementById("finder-results");
const status = document.getElementById("finder-status");
const progress = document.getElementById("finder-progress");
const elapsed = document.getElementById("finder-elapsed");
const preview = document.getElementById("finder-preview");
const previewStatus = document.getElementById("finder-preview-status");
const previewFormat = document.getElementById("finder-preview-format");
const previewFormatLabel = document.getElementById("finder-preview-format-label");
const openLink = document.getElementById("finder-open");
const scope = document.getElementById("finder-scope");
const include = document.getElementById("finder-include");
const regex = document.getElementById("finder-regex");
const filename = document.getElementById("finder-filename");
const excludeFilename = document.getElementById("finder-exclude-filename");
const recentKind = document.getElementById("finder-recent-kind");
const filenameFilters = {
  contents: { include: "", exclude: "" },
  updated: { include: "\\.(html|md)$", exclude: "" },
};
let mode = "files", results = [], selected = -1, generation = 0, previewGeneration = 0;
let opener, searchAbort, previewAbort, timer, progressTimer;
let currentPreview;

function stopProgress() {
  clearInterval(progressTimer);
  progress.hidden = true;
  elapsed.hidden = true;
  list.setAttribute("aria-busy", "false");
}

function startProgress() {
  stopProgress();
  progress.hidden = false;
  elapsed.hidden = false;
  list.setAttribute("aria-busy", "true");
  status.textContent = mode === "updated" ? "Scanning files and checking modification times…"
    : mode === "recent" ? "Loading recent visits…" : "Searching…";
  const started = performance.now();
  const update = () => { elapsed.textContent = `${Math.floor((performance.now() - started) / 1000)}s elapsed`; };
  update();
  progressTimer = setInterval(update, 1000);
}

async function api(endpoint, parameters, signal) {
  const response = await fetch(`/__serve_html__/api/${endpoint}?${new URLSearchParams(parameters)}`, { signal });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}

function resetPreview() {
  previewAbort?.abort();
  previewGeneration += 1;
  preview.replaceChildren();
  preview.classList.remove("finder-rendered");
  currentPreview = undefined;
  previewFormatLabel.hidden = true;
  previewStatus.textContent = "";
  document.getElementById("finder-path").textContent = "";
  openLink.hidden = true;
}

function matchText(element, text, ranges, firstByte = 0) {
  // ripgrep reports UTF-8 byte offsets. Convert them before slicing JavaScript strings.
  const bytes = new TextEncoder().encode(text);
  const decode = new TextDecoder();
  let offset = 0;
  for (const range of ranges) {
    const start = Math.max(0, range.start - firstByte);
    const end = Math.min(bytes.length, range.end - firstByte);
    if (end < 0 || start > bytes.length) continue;
    element.append(decode.decode(bytes.slice(offset, start)));
    const mark = document.createElement("mark");
    mark.textContent = decode.decode(bytes.slice(start, end));
    element.append(mark);
    offset = end;
  }
  element.append(decode.decode(bytes.slice(offset)));
}

function renderPreview() {
  if (!currentPreview) return;
  const { data, result } = currentPreview;
  preview.replaceChildren();
  const rendered = data.render_kind && previewFormat.value === "rendered";
  preview.classList.toggle("finder-rendered", Boolean(rendered));
  if (rendered) {
    const frame = document.createElement("iframe");
    frame.title = `Preview of ${result.path}`;
    frame.dataset.docservePreview = "";
    // Markdown uses our sanitized viewer. HTML keeps its styles and assets,
    // while the sandbox prevents author scripts, popups, and top navigation.
    if (data.render_kind === "html") frame.setAttribute("sandbox", "allow-same-origin");
    const url = new URL(result.url, location.href);
    url.searchParams.set("__docserve_standalone", "1");
    frame.src = url.href;
    previewStatus.textContent = "Loading preview…";
    frame.addEventListener("load", () => {
      if (preview.contains(frame)) previewStatus.textContent = result.line
        ? "Select Source to see the highlighted match." : "";
    });
    preview.append(frame);
    return;
  }
  for (const line of data.lines) {
    const row = document.createElement("div");
    row.className = "finder-line";
    const number = document.createElement("span");
    number.className = "finder-line-number";
    number.textContent = line.number;
    const code = document.createElement("code");
    if (line.number === result.line) {
      row.classList.add("finder-match");
      matchText(code, line.text, result.matches || [], line.offset || 0);
    } else code.textContent = line.text;
    row.append(number, code);
    preview.append(row);
  }
  previewStatus.textContent = data.message || (data.truncated ? "Showing part of this file." : "");
  preview.querySelector(".finder-match")?.scrollIntoView({ block: "nearest" });
}

previewFormat.addEventListener("change", renderPreview);

async function select(index) {
  if (!results.length) return;
  selected = Math.max(0, Math.min(index, results.length - 1));
  for (const [position, child] of [...list.children].entries()) {
    child.setAttribute("aria-selected", String(position === selected));
  }
  const option = list.children[selected];
  list.setAttribute("aria-activedescendant", option.id);
  query.setAttribute("aria-activedescendant", option.id);
  option.scrollIntoView({ block: "nearest" });
  resetPreview();
  const result = results[selected];
  document.getElementById("finder-path").textContent = result.path || "/";
  openLink.href = result.url;
  openLink.textContent = result.kind === "directory" ? "Open directory" : "Open file";
  openLink.hidden = false;
  if (result.kind === "directory") {
    previewStatus.textContent = "Open this directory to view its listing.";
    return;
  }
  const current = previewGeneration;
  previewAbort = new AbortController();
  previewStatus.textContent = "Loading preview…";
  try {
    const data = await api("preview", {
      url: result.url, line: result.line || 1, column: result.matches?.[0]?.start || 0,
    }, previewAbort.signal);
    if (current !== previewGeneration) return;
    currentPreview = { data, result };
    previewFormatLabel.hidden = !data.render_kind;
    renderPreview();
  } catch (error) {
    if (error.name !== "AbortError" && current === previewGeneration) previewStatus.textContent = error.message;
  }
}

async function search(current) {
  searchAbort = new AbortController();
  try {
    const data = await api(mode === "recent" ? "recent" : "search", {
      mode, q: query.value, scope_url: tools.dataset.scopeUrl || location.pathname,
      root: scope.value === "current" ? "0" : "1",
      include: include.checked ? "1" : "0", regex: regex.checked ? "1" : "0",
      filename: filenameFilters[mode] ? filename.value : "",
      exclude_filename: filenameFilters[mode] ? excludeFilename.value : "", kind: recentKind.value,
    }, searchAbort.signal);
    if (current !== generation) return;
    results = data.results;
    for (const [index, result] of results.entries()) {
      const option = document.createElement("li");
      option.id = `finder-result-${index}`;
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", "false");
      const title = document.createElement("span");
      title.className = "finder-result-path";
      title.textContent = (result.path || "/") + (result.kind === "directory" && result.path ? "/" : "");
      option.append(title);
      if (result.line) {
        const snippet = document.createElement("span");
        snippet.className = "finder-snippet";
        snippet.textContent = `${result.line}: ${result.text}`;
        option.append(snippet);
      } else if (result.visited_at) {
        const time = document.createElement("time");
        time.className = "finder-snippet";
        time.dateTime = result.visited_at;
        time.textContent = `${result.kind === "directory" ? "Directory" : "File"} · ${new Date(result.visited_at).toLocaleString()}`;
        option.append(time);
      } else if ("modified_at" in result) {
        const time = document.createElement("time");
        time.className = "finder-snippet";
        if (result.modified_at) {
          time.dateTime = result.modified_at;
          time.textContent = `Modified · ${new Date(result.modified_at).toLocaleString()}`;
        } else time.textContent = "Modified time unavailable";
        option.append(time);
      }
      option.addEventListener("click", () => { void select(index); });
      option.addEventListener("dblclick", () => { location.href = result.url; });
      list.append(option);
    }
    let limitMessage = "";
    if (data.truncated) {
      if (mode === "updated" && data.scan_complete === true) limitMessage = " Showing the newest matches.";
      else if (data.scan_complete !== false) limitMessage = " Results are limited; narrow your search.";
    }
    status.textContent = `${results.length} result${results.length === 1 ? "" : "s"}.${limitMessage}${data.message ? " " + data.message : ""}`;
    if (results.length) void select(0);
    else previewStatus.textContent = "No result selected.";
  } catch (error) {
    if (error.name !== "AbortError" && current === generation) status.textContent = error.message;
  } finally {
    if (current === generation) stopProgress();
  }
}

function schedule(immediate = false) {
  clearTimeout(timer);
  searchAbort?.abort();
  resetPreview();
  results = [];
  selected = -1;
  list.replaceChildren();
  list.removeAttribute("aria-activedescendant");
  query.removeAttribute("aria-activedescendant");
  startProgress();
  const current = ++generation;
  timer = setTimeout(() => { void search(current); }, immediate ? 0 : 120);
}

function changeMode(value) {
  if (filenameFilters[mode]) {
    filenameFilters[mode] = { include: filename.value, exclude: excludeFilename.value };
  }
  mode = value;
  if (filenameFilters[mode]) {
    filename.value = filenameFilters[mode].include;
    excludeFilename.value = filenameFilters[mode].exclude;
  }
  document.getElementById("finder-title").textContent = labels[mode];
  document.getElementById("finder-regex-label").hidden = mode !== "contents";
  document.getElementById("finder-options").hidden = mode === "recent";
  document.getElementById("finder-filename-filters").hidden = !filenameFilters[mode];
  document.getElementById("finder-recent-options").hidden = mode !== "recent";
  for (const tab of dialog.querySelectorAll("[data-mode]")) {
    tab.setAttribute("aria-selected", String(tab.dataset.mode === mode));
    tab.tabIndex = tab.dataset.mode === mode ? 0 : -1;
  }
  schedule(true);
}

for (const button of tools.querySelectorAll("[data-find]")) {
  button.addEventListener("click", () => {
    opener = button;
    query.value = "";
    dialog.showModal();
    changeMode(button.dataset.find);
    query.focus();
  });
}
for (const tab of dialog.querySelectorAll("[data-mode]")) {
  tab.addEventListener("click", () => changeMode(tab.dataset.mode));
  tab.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const tabs = [...dialog.querySelectorAll("[data-mode]")];
    const index = tabs.indexOf(tab);
    const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    tabs[next].focus();
    changeMode(tabs[next].dataset.mode);
  });
}
for (const control of [query, filename, excludeFilename]) control.addEventListener("input", () => schedule());
for (const control of [scope, include, regex, recentKind]) control.addEventListener("change", () => schedule(true));
for (const element of [query, list]) element.addEventListener("keydown", event => {
  if (event.isComposing) return;
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    void select(selected + (event.key === "ArrowDown" ? 1 : -1));
  } else if (event.key === "Enter") {
    event.preventDefault();
    if (selected >= 0) location.href = results[selected].url;
  }
});
document.getElementById("finder-close").addEventListener("click", () => dialog.close());
dialog.addEventListener("keydown", event => {
  if (event.key === "Escape") {
    event.preventDefault();
    dialog.close();
  }
});
dialog.addEventListener("close", () => {
  clearTimeout(timer);
  searchAbort?.abort();
  generation += 1;
  stopProgress();
  resetPreview();
  opener?.focus();
});
