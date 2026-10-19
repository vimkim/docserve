// Shared document controls. The four states are banner, directory, compact,
// and compact-directory; closing a directory always returns to its own layout.
import { createCopyPathButton, setCopyPath } from "./copy-path.js";

const standaloneKey = "__docserve_standalone";
const frame = document.getElementById("document-frame");
const embedded = window.frameElement?.hasAttribute("data-docserve-document");

function originalURL(value) {
  const url = documentURL(value);
  url.search += (url.search ? "&" : "?") + standaloneKey + "=1";
  return url;
}

function documentURL(value) {
  const url = new URL(value, location.href);
  // Do not reserialize ordinary query strings: an HTML page may depend on them.
  if (url.searchParams.has(standaloneKey)) {
    url.search = url.search.slice(1).split("&").filter(part => !new URLSearchParams(part).has(standaloneKey)).join("&");
  }
  return url;
}

function label(value) {
  try { return decodeURIComponent(value); } catch { return value; }
}

if (window.frameElement?.hasAttribute("data-docserve-preview")) {
  document.documentElement.classList.add("docserve-finder-preview");
} else if (frame && window.parent !== window) {
  // Plain HTTP LAN browsers can omit Fetch Metadata. Both our document frame
  // and an author's supporting frames must recover the original HTML page.
  location.replace(originalURL(location.href));
} else if (embedded) {
  document.documentElement.classList.add("docserve-embedded");
} else if (new URL(location.href).searchParams.get(standaloneKey) !== "1") {
  initialize();
}

function initialize() {
  let view = "banner";
  let currentURL = documentURL(location.href);
  let browsingURL = new URL("./", currentURL);
  let directoryData, entries = [], visits = [], request, generation = 0;
  let finderLoaded = false;
  let copyURL;
  const header = document.querySelector(".toolbar");
  const nav = header.querySelector("nav");
  const extras = frame ? [] : [...nav.children].filter(node => node.id === "raw-link" || node.id === "theme-toggle");
  header.id = "document-banner";
  const brand = document.createElement("a");
  brand.className = "docserve-brand";
  brand.setAttribute("aria-label", "docserve — Go to root");
  brand.href = "/";
  brand.innerHTML = '<span aria-hidden="true">▤</span><span class="brand-name">docserve</span>';
  header.prepend(brand);
  nav.innerHTML = `<button id="directory-toggle" type="button" aria-controls="document-directory" aria-expanded="false">Directory listing</button>
    <a href="/" class="document-root">Go to root</a>
    <a id="standalone-link" target="_blank" rel="noopener" aria-label="Open standalone"><span class="standalone-label">Open standalone </span>↗</a>
    <button id="compact-view" type="button" aria-label="Compact view" title="Switch to floating controls">− <span class="compact-label">Compact view</span></button>`;
  nav.querySelector("#standalone-link").before(...extras);
  const bannerCopy = createCopyPathButton();
  nav.querySelector("#standalone-link").before(bannerCopy);

  const floating = document.createElement("nav");
  floating.id = "document-floating";
  floating.setAttribute("aria-label", "Compact document navigation");
  floating.hidden = true;
  floating.innerHTML = `<button id="compact-directory-toggle" type="button" aria-controls="document-directory" aria-expanded="false">Directory listing</button>
    <span id="compact-filename"></span>
    <button id="expand-banner" type="button" aria-label="Expand banner" title="Return to the banner">▤ <span class="expand-label">Expand banner</span></button>
    <a id="compact-standalone" target="_blank" rel="noopener" aria-label="Open standalone">↗</a>`;
  const compactCopy = createCopyPathButton();
  floating.querySelector("#expand-banner").before(compactCopy);
  const pane = document.createElement("aside");
  pane.id = "document-directory";
  pane.setAttribute("aria-label", "Directory listing");
  pane.hidden = true;
  pane.innerHTML = `<div class="directory-heading"><h2>Directory listing</h2><button id="close-directory" type="button" aria-label="Close directory listing">×</button></div>
    <div class="directory-location"><button id="directory-up" type="button" aria-label="Parent directory">↑</button><span id="directory-path"></span></div>
    <input id="directory-filter" type="search" aria-label="Filter this directory" placeholder="Filter this directory…">
    <p id="directory-status" role="status" aria-live="polite"></p>
    <ul id="directory-entries" aria-label="Directory entries"></ul>
    <h3>Recently visited</h3><ul id="directory-recent" aria-label="Recently visited"></ul>
    <div class="directory-links"><a id="full-directory-link">Full directory listing</a><a href="/">Go to root</a></div>
    <div id="navigation-tools" hidden></div>`;
  const backdrop = document.createElement("button");
  backdrop.id = "directory-backdrop";
  backdrop.type = "button";
  backdrop.tabIndex = -1;
  backdrop.setAttribute("aria-label", "Close directory listing");
  backdrop.hidden = true;
  const layout = document.createElement("div");
  layout.id = "document-layout";
  const reader = document.createElement("div");
  reader.id = "document-reader";
  const main = document.getElementById(frame ? "html-content" : "content");
  main.before(layout);
  reader.append(main);
  layout.append(pane, reader);
  document.body.append(floating, backdrop);

  const directoryToggle = document.getElementById("directory-toggle");
  const compactToggle = document.getElementById("compact-directory-toggle");
  const compactButton = document.getElementById("compact-view");
  const expandButton = document.getElementById("expand-banner");
  const filter = document.getElementById("directory-filter");
  const status = document.getElementById("directory-status");
  const entryList = document.getElementById("directory-entries");
  const recentList = document.getElementById("directory-recent");
  const tools = document.getElementById("navigation-tools");
  const narrow = matchMedia("(max-width: 800px)");
  const isOpen = () => view === "directory" || view === "compact-directory";

  function updateLayout() {
    const compact = view === "compact" || view === "compact-directory";
    document.body.dataset.documentView = view;
    header.hidden = compact;
    floating.hidden = !compact;
    pane.hidden = !isOpen();
    compactButton.hidden = view === "directory";
    expandButton.hidden = view === "compact-directory";
    directoryToggle.setAttribute("aria-expanded", String(view === "directory"));
    compactToggle.setAttribute("aria-expanded", String(view === "compact-directory"));
    backdrop.hidden = !isOpen() || !narrow.matches;
    reader.inert = isOpen() && narrow.matches;
    document.documentElement.style.setProperty("--document-banner-height", `${compact ? 0 : header.getBoundingClientRect().height}px`);
  }

  function changeView(next) {
    view = next;
    updateLayout();
    if (isOpen()) {
      void loadDirectory();
      filter.focus();
      if (!finderLoaded) {
        finderLoaded = true;
        import("./navigation.js").catch(() => { finderLoaded = false; });
      }
    }
  }

  function closeDirectory() {
    const compact = view === "compact-directory";
    changeView(compact ? "compact" : "banner");
    (compact ? compactToggle : directoryToggle).focus();
  }

  function updateDocument() {
    const name = label(currentURL.pathname.split("/").filter(Boolean).pop() || "/");
    document.getElementById("filename").textContent = name;
    document.getElementById("compact-filename").textContent = name;
    const original = originalURL(currentURL);
    document.getElementById("standalone-link").href = original;
    document.getElementById("compact-standalone").href = original;
    if (copyURL !== currentURL.pathname) {
      copyURL = currentURL.pathname;
      void loadDocumentPath(copyURL);
    }
    browsingURL = new URL("./", currentURL);
    tools.dataset.scopeUrl = browsingURL.pathname;
    if (isOpen()) void loadDirectory();
  }

  async function api(endpoint, parameters, signal) {
    const response = await fetch(`/__serve_html__/api/${endpoint}?${new URLSearchParams(parameters)}`, { signal, cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Request failed (HTTP ${response.status}).`);
    return data;
  }

  async function loadDocumentPath(url) {
    for (const button of [bannerCopy, compactCopy]) setCopyPath(button, "");
    try {
      const data = await api("path", { url });
      if (url === currentURL.pathname) {
        for (const button of [bannerCopy, compactCopy]) setCopyPath(button, data.server_path);
      }
    } catch { /* Keep reading available when path metadata cannot be loaded. */ }
  }

  function plainClick(event) {
    return event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey;
  }

  function openFile(event, value) {
    if (!plainClick(event)) return;
    const close = narrow.matches || view === "compact-directory";
    if (close) closeDirectory();
    if (frame) {
      event.preventDefault();
      const url = new URL(value, location.href);
      frame.contentWindow.location.assign(/\.html?$/i.test(url.pathname) ? originalURL(url) : url);
    }
  }

  function entry(item, recent = false) {
    const li = document.createElement("li");
    const link = document.createElement("a");
    link.href = item.url;
    const directory = item.kind === "directory";
    const name = recent ? item.path || "/" : item.name;
    const icon = document.createElement("span");
    icon.className = "directory-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = directory ? "▱" : /\.html?$/i.test(item.url) ? "<>" : "#";
    const title = document.createElement("span");
    title.textContent = name + (directory && name !== "/" ? "/" : item.symlink ? "@" : "");
    link.append(icon, title);
    if (label(new URL(item.url, location.href).pathname) === label(currentURL.pathname)) link.setAttribute("aria-current", "page");
    link.addEventListener("click", event => {
      if (directory && plainClick(event)) {
        event.preventDefault();
        browsingURL = new URL(item.url, location.href);
        void loadDirectory();
      } else {
        openFile(event, item.url);
      }
    });
    li.append(link);
    if (item.server_path) li.append(createCopyPathButton(item.server_path, name));
    return li;
  }

  function renderEntries() {
    const visible = entries.filter(item => item.name.toLocaleLowerCase().includes(filter.value.toLocaleLowerCase()));
    entryList.replaceChildren(...visible.map(item => entry(item)));
    recentList.replaceChildren(...visits.slice(0, 5).map(item => entry(item, true)));
    status.textContent = visible.length ? "" : filter.value ? "No matching files." : "This directory is empty.";
  }

  async function loadDirectory() {
    request?.abort();
    request = new AbortController();
    const signal = request.signal;
    const current = ++generation;
    entryList.setAttribute("aria-busy", "true");
    status.textContent = "Loading directory…";
    tools.dataset.scopeUrl = browsingURL.pathname;
    try {
      const [data, history] = await Promise.all([
        api("directory", { url: browsingURL.pathname }, signal),
        api("recent", { scope_url: browsingURL.pathname }, signal).catch(error => { if (error.name === "AbortError") throw error; return { results: [] }; }),
      ]);
      if (current !== generation) return;
      directoryData = data;
      browsingURL = new URL(data.url, location.href);
      entries = data.entries;
      visits = history.results;
      filter.value = "";
      document.getElementById("directory-path").textContent = "/" + data.path;
      document.getElementById("directory-up").disabled = data.parent === null;
      document.getElementById("full-directory-link").href = data.url;
      renderEntries();
    } catch (error) {
      if (error.name !== "AbortError" && current === generation) {
        entries = [];
        entryList.replaceChildren();
        status.textContent = `Could not load this directory: ${error.message}`;
      }
    } finally {
      if (current === generation) entryList.setAttribute("aria-busy", "false");
    }
  }

  function keydown(event) {
    if (!isOpen() || event.defaultPrevented || document.querySelector("dialog[open]")) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeDirectory();
    } else if (event.key === "Tab" && narrow.matches) {
      const stops = [...pane.querySelectorAll('a[href], button:not(:disabled), input')].filter(node => !node.hidden && node.getClientRects().length);
      const first = stops[0], last = stops.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
  }

  directoryToggle.addEventListener("click", () => view === "directory" ? closeDirectory() : changeView("directory"));
  compactToggle.addEventListener("click", () => view === "compact-directory" ? closeDirectory() : changeView("compact-directory"));
  compactButton.addEventListener("click", () => { changeView("compact"); compactToggle.focus(); });
  expandButton.addEventListener("click", () => { changeView("banner"); compactButton.focus(); });
  document.getElementById("close-directory").addEventListener("click", closeDirectory);
  backdrop.addEventListener("click", closeDirectory);
  document.getElementById("directory-up").addEventListener("click", () => {
    if (!directoryData?.parent) return;
    browsingURL = new URL(directoryData.parent, location.href);
    void loadDirectory();
  });
  filter.addEventListener("input", renderEntries);
  document.addEventListener("keydown", keydown);
  narrow.addEventListener("change", updateLayout);
  new ResizeObserver(updateLayout).observe(header);

  if (frame) {
    async function synchronizeFrame() {
      let url, child;
      try {
        child = frame.contentDocument;
        url = documentURL(frame.contentWindow.location.href);
        if (!child || child.body?.hasAttribute("data-docserve-html-viewer")) return;
      } catch { return; }
      if (url.origin !== location.origin || url.pathname.startsWith("/__serve_html__/")) return;
      const changed = url.pathname !== currentURL.pathname;
      currentURL = url;
      history.replaceState(null, "", url);
      document.title = child.title || label(url.pathname.split("/").pop()) || "Directory listing";
      updateDocument();
      child.addEventListener("keydown", keydown);
      frame.contentWindow.addEventListener("hashchange", synchronizeFrame, { once: true });
      if (changed) {
        try {
          await fetch("/__serve_html__/api/visit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: url.pathname }) });
          if (isOpen()) void loadDirectory();
        } catch { /* Reading still works when visit history cannot be updated. */ }
      }
    }
    frame.addEventListener("load", synchronizeFrame);
    if (location.hash) frame.src = originalURL(currentURL);
    if (frame.contentDocument?.readyState === "complete") void synchronizeFrame();
  }
  updateDocument();
  updateLayout();
}
