import "./copy-path.js";

const tools = document.getElementById("navigation-tools");
const labels = { files: "Find files", contents: "Find contents", directories: "Find directories", recent: "Recently visited" };
tools.innerHTML = `
  <div class="finder-buttons">
    <button type="button" data-find="files">Find files</button>
    <button type="button" data-find="contents">Find contents</button>
    <button type="button" data-find="directories">Find directories</button>
    <button type="button" data-find="recent">Recently visited</button>
  </div>
  <dialog id="finder" aria-labelledby="finder-title">
    <div class="finder-heading"><h2 id="finder-title">Find files</h2><button type="button" id="finder-close">Close</button></div>
    <div role="tablist" aria-label="Find by">
      <button type="button" role="tab" data-mode="files">Files</button>
      <button type="button" role="tab" data-mode="contents">Contents</button>
      <button type="button" role="tab" data-mode="directories">Directories</button>
      <button type="button" role="tab" data-mode="recent">Recent</button>
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
    <p id="finder-status" role="status" aria-live="polite"></p>
    <div class="finder-panes">
      <ul id="finder-results" role="listbox" aria-label="Search results" tabindex="0"></ul>
      <section class="finder-preview-pane" aria-label="File preview">
        <div class="finder-preview-heading"><span id="finder-path"></span><a id="finder-open" hidden>Open</a></div>
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
const preview = document.getElementById("finder-preview");
const previewStatus = document.getElementById("finder-preview-status");
const openLink = document.getElementById("finder-open");
const scope = document.getElementById("finder-scope");
const include = document.getElementById("finder-include");
const regex = document.getElementById("finder-regex");
const filename = document.getElementById("finder-filename");
const excludeFilename = document.getElementById("finder-exclude-filename");
const recentKind = document.getElementById("finder-recent-kind");
let mode = "files", results = [], selected = -1, generation = 0, previewGeneration = 0;
let opener, searchAbort, previewAbort, timer;

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
  } catch (error) {
    if (error.name !== "AbortError" && current === previewGeneration) previewStatus.textContent = error.message;
  }
}

async function search(current) {
  searchAbort = new AbortController();
  try {
    const data = await api(mode === "recent" ? "recent" : "search", {
      mode, q: query.value, scope_url: scope.value === "current" ? tools.dataset.scopeUrl || location.pathname : "/",
      include: include.checked ? "1" : "0", regex: regex.checked ? "1" : "0",
      filename: mode === "contents" ? filename.value : "",
      exclude_filename: mode === "contents" ? excludeFilename.value : "", kind: recentKind.value,
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
      }
      option.addEventListener("click", () => { void select(index); });
      option.addEventListener("dblclick", () => { location.href = result.url; });
      list.append(option);
    }
    status.textContent = `${results.length} result${results.length === 1 ? "" : "s"}.${data.truncated ? " Results are limited; narrow your search." : ""}${data.message ? " " + data.message : ""}`;
    if (results.length) void select(0);
    else previewStatus.textContent = "No result selected.";
  } catch (error) {
    if (error.name !== "AbortError" && current === generation) status.textContent = error.message;
  } finally {
    if (current === generation) list.setAttribute("aria-busy", "false");
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
  list.setAttribute("aria-busy", "true");
  status.textContent = "Searching…";
  const current = ++generation;
  timer = setTimeout(() => { void search(current); }, immediate ? 0 : 120);
}

function changeMode(value) {
  mode = value;
  document.getElementById("finder-title").textContent = labels[mode];
  document.getElementById("finder-regex-label").hidden = mode !== "contents";
  document.getElementById("finder-options").hidden = mode === "recent";
  document.getElementById("finder-filename-filters").hidden = mode !== "contents";
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
  resetPreview();
  opener?.focus();
});
