const params = new URLSearchParams(location.search);
const documentURL = params.get("url");
const select = document.getElementById("compare-revision");
const rightSelect = document.getElementById("compare-right");
const versionButtons = {
  left: [document.getElementById("compare-left-prev"), document.getElementById("compare-left-next")],
  right: [document.getElementById("compare-right-prev"), document.getElementById("compare-right-next")],
};
const status = document.getElementById("compare-status");
const before = document.getElementById("compare-before");
const after = document.getElementById("compare-after");
const previous = document.getElementById("compare-prev");
const next = document.getElementById("compare-next");
const sync = document.getElementById("compare-sync");
const close = document.getElementById("compare-close");
const state = { generation: 0, phase: "loading", changes: [], index: -1 };
let endpoints = [];
let pair = null;
close.href = documentURL || "/";

function phase(value, message) {
  if (value !== "ready") stopOverview();
  state.phase = value;
  status.textContent = message;
  previous.disabled = next.disabled = value !== "ready" || !state.changes.length;
}

function standalone(value) {
  const url = new URL(value, location.origin);
  if (/\.html?$/i.test(url.pathname)) url.searchParams.set("__docserve_standalone", "1");
  return url.href;
}

function loadFrame(frame, url, signal) {
  return new Promise((resolve, reject) => {
    const expected = standalone(url);
    const finish = error => {
      clearTimeout(timer);
      frame.removeEventListener("load", loaded);
      signal.removeEventListener("abort", aborted);
      if (error) reject(error); else resolve();
    };
    const loaded = () => {
      if (frame.contentWindow.location.href === expected) finish();
    };
    const aborted = () => finish(new DOMException("Cancelled", "AbortError"));
    const timer = setTimeout(() => finish(new Error("Document loading timed out.")), 12000);
    frame.addEventListener("load", loaded);
    signal.addEventListener("abort", aborted, { once: true });
    frame.src = expected;
  });
}

async function ready(frame) {
  const doc = frame.contentDocument;
  if (!doc?.body) throw new Error("Document could not be loaded.");
  const deadline = Date.now() + 12000;
  while (doc.querySelector('#content.markdown-body[aria-busy="true"], #content.markdown-body [aria-busy="true"]')) {
    if (Date.now() > deadline) throw new Error("Document rendering timed out.");
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  if (doc.querySelector("#content.markdown-body .render-error")) throw new Error("Markdown rendering failed.");
  await new Promise(resolve => setTimeout(resolve, 200));
  await Promise.race([
    Promise.all([doc.fonts?.ready, ...[...doc.images].map(image => image.complete ? null : new Promise(resolve => {
      image.addEventListener("load", resolve, { once: true });
      image.addEventListener("error", resolve, { once: true });
    }))]),
    new Promise(resolve => setTimeout(resolve, 2500)),
  ]);
}

function blocks(doc) {
  const root = doc.querySelector("#content.markdown-body") || doc.body;
  const groups = [];
  const blockTags = new Set("ADDRESS ARTICLE ASIDE BLOCKQUOTE DIV DL DT DD FIGCAPTION FOOTER H1 H2 H3 H4 H5 H6 HEADER LI MAIN NAV P PRE SECTION TABLE TD TH TR".split(" "));
  let group;
  function add(element, part, extra = "") {
    if (!group || group.element !== element || extra) {
      group = { element, kind: element.tagName, parts: [], extra };
      groups.push(group);
    }
    if (part) group.parts.push(part);
    if (extra) group = null;
  }
  function visit(element, owner) {
    if (element.nodeType === Node.TEXT_NODE) {
      add(owner, { node: element, whitespace: doc.defaultView.getComputedStyle(element.parentElement).whiteSpace });
      return;
    }
    if (element.nodeType !== Node.ELEMENT_NODE || element.matches("script,style,noscript,template")) return;
    const style = doc.defaultView.getComputedStyle(element);
    if (style.display === "none" || style.visibility === "hidden") return;
    if (element.hasAttribute("data-docserve-kind")) {
      add(element, null, `${element.dataset.docserveKind}:${element.dataset.docserveSource}`);
      return;
    }
    if (element.matches("img,svg,video,audio,canvas,hr")) {
      add(element, null, `${element.tagName}:${element.getAttribute("src") || element.getAttribute("alt") || ""}`);
      return;
    }
    if (element.tagName === "BR") { add(owner, { node: element }); return; }
    const current = blockTags.has(element.tagName) ? element : owner;
    for (const child of element.childNodes) visit(child, current);
  }
  visit(root, root);
  if (groups.length > 1500) throw new Error("Document has too many blocks to compare.");
  const normalized = groups.map(block => {
    block.text = "";
    block.spans = [];
    let pending;
    function append(text, from, to) {
      block.spans.push({ start: block.text.length, end: block.text.length + text.length, from, to });
      block.text += text;
    }
    function flushSpace() {
      if (pending && block.text && !block.text.endsWith("\n")) append(" ", pending.from, pending.to);
      pending = null;
    }
    for (const { node, whitespace } of block.parts) {
      if (node.nodeType === Node.ELEMENT_NODE) {
        pending = null;
        const index = [...node.parentNode.childNodes].indexOf(node);
        append("\n", { node: node.parentNode, offset: index }, { node: node.parentNode, offset: index + 1 });
        continue;
      }
      const preserve = ["pre", "pre-wrap", "break-spaces"].includes(whitespace);
      const pattern = preserve ? /[\s\S]+/g : whitespace === "pre-line" ? /\n|[ \t\r\f]+|[^ \t\r\n\f]+/g : /[ \t\r\n\f]+|[^ \t\r\n\f]+/g;
      for (const match of node.data.matchAll(pattern)) {
        const text = match[0];
        const from = { node, offset: match.index }, to = { node, offset: match.index + text.length };
        if (!preserve && /^[ \t\r\n\f]+$/.test(text) && !(whitespace === "pre-line" && text === "\n")) {
          pending = { from: pending?.from || from, to };
        } else {
          if (text.startsWith("\n")) pending = null; else flushSpace();
          append(text, from, to);
        }
      }
    }
    delete block.parts;
    return block;
  }).filter(block => block.text || block.extra);
  return normalized.map(block => {
    block.exclusive = !normalized.some(other => other !== block && block.element.contains(other.element));
    const links = [...block.element.querySelectorAll("a[href]")].map(el => el.getAttribute("href")).join(" ");
    block.key = block.kind + "\0" + block.text + "\0" + block.extra + "\0" + links;
    return block;
  });
}

function pairs(a, b, key = value => value.key) {
  if (a.length * b.length > 500000) throw new Error("Document is too large to compare.");
  const rows = Array.from({ length: a.length + 1 }, () => new Uint32Array(b.length + 1));
  for (let i = a.length - 1; i >= 0; i--) for (let j = b.length - 1; j >= 0; j--)
    rows[i][j] = key(a[i]) === key(b[j]) ? rows[i + 1][j + 1] + 1 : Math.max(rows[i + 1][j], rows[i][j + 1]);
  const result = [];
  let i = 0, j = 0;
  while (i < a.length && j < b.length) {
    if (key(a[i]) === key(b[j])) { result.push([i++, j++]); }
    else if (rows[i + 1][j] >= rows[i][j + 1]) i++;
    else j++;
  }
  return result;
}

function range(block, start, end) {
  const first = block.spans.find(part => part.end > start);
  const last = block.spans.findLast(part => part.start < end);
  if (!first || !last) return null;
  function point(span, offset, edge) {
    if (span.from.node === span.to.node && span.to.offset - span.from.offset === span.end - span.start)
      return { node: span.from.node, offset: span.from.offset + offset - span.start };
    return span[edge];
  }
  const from = point(first, start, "from"), to = point(last, end, "to");
  const result = block.element.ownerDocument.createRange();
  result.setStart(from.node, from.offset);
  result.setEnd(to.node, to.offset);
  return result;
}

function tokens(text) {
  return [...text.matchAll(/\s+|[\p{L}\p{N}_]+|[^\s\p{L}\p{N}_]/gu)].map(match => ({ text: match[0], start: match.index, end: match.index + match[0].length }));
}

function compare(oldBlocks, newBlocks) {
  const changes = [], oldRanges = [], newRanges = [], oldWholeRanges = [], newWholeRanges = [];
  const anchors = [[-1, -1], ...pairs(oldBlocks, newBlocks), [oldBlocks.length, newBlocks.length]];
  function paintBlock(block, side) {
    if (block.exclusive) block.element.classList.add(side === "old" ? "docserve-deleted" : "docserve-added");
    else {
      const r = block.target ||= range(block, 0, block.text.length);
      if (r) (side === "old" ? oldWholeRanges : newWholeRanges).push(r);
    }
  }
  function whole(block, side) {
    paintBlock(block, side);
    changes.push({ old: side === "old" ? block : null, new: side === "new" ? block : null });
  }
  function edit(oldBlock, newBlock) {
    const a = tokens(oldBlock.text), b = tokens(newBlock.text);
    if (a.length * b.length > 100000) { whole(oldBlock, "old"); whole(newBlock, "new"); return; }
    const matched = pairs(a, b, token => token.text);
    const oldMatched = new Set(matched.map(pair => pair[0])), newMatched = new Set(matched.map(pair => pair[1]));
    for (const [block, tokens, matched, ranges, side] of [[oldBlock, a, oldMatched, oldRanges, "old"], [newBlock, b, newMatched, newRanges, "new"]]) {
      tokens.forEach((token, i) => {
        if (matched.has(i)) return;
        const r = range(block, token.start, token.end);
        if (!r) return;
        ranges.push(r);
        block.focus ||= r;
        if (r.cloneContents().querySelector("br") && ![...r.getClientRects()].some(rect => rect.width)) paintBlock(block, side);
      });
    }
    if (a.length === oldMatched.size && b.length === newMatched.size) { whole(oldBlock, "old"); whole(newBlock, "new"); }
    else changes.push({ old: oldBlock, new: newBlock });
  }
  for (let k = 1; k < anchors.length; k++) {
    const [oi, ni] = anchors[k - 1], [oj, nj] = anchors[k];
    const old = oldBlocks.slice(oi + 1, oj), current = newBlocks.slice(ni + 1, nj);
    let i = 0;
    while (i < old.length && i < current.length && old[i].kind === current[i].kind) { edit(old[i], current[i]); i++; }
    old.slice(i).forEach(block => whole(block, "old"));
    current.slice(i).forEach(block => whole(block, "new"));
  }
  return { changes, oldRanges, newRanges, oldWholeRanges, newWholeRanges, anchors: anchors.slice(1, -1).map(([i, j]) => [oldBlocks[i], newBlocks[j]]) };
}

function install(doc, name, ranges, wholeRanges, targets) {
  const style = doc.createElement("style");
  style.textContent = `.docserve-deleted { background-color: #ffd9d9 !important; } .docserve-added { background-color: #d8f5dc !important; } ::highlight(docserve-old) { background-color: #ff9a9a; color: inherit; } ::highlight(docserve-new) { background-color: #9de7a9; color: inherit; } ::highlight(docserve-old-whole) { background-color: #ffd9d9; color: inherit; } ::highlight(docserve-new-whole) { background-color: #d8f5dc; color: inherit; }`;
  doc.head.append(style);
  if (doc.defaultView.CSS?.highlights && doc.defaultView.Highlight) {
    doc.defaultView.CSS.highlights.set(name, new doc.defaultView.Highlight(...ranges));
    doc.defaultView.CSS.highlights.set(`${name}-whole`, new doc.defaultView.Highlight(...wholeRanges));
  } else {
    const bookmarks = targets.map(range => {
      const start = doc.createComment(""), end = doc.createComment("");
      const cursor = range.cloneRange();
      cursor.collapse(false);
      cursor.insertNode(end);
      cursor.setStart(range.startContainer, range.startOffset);
      cursor.collapse(true);
      cursor.insertNode(start);
      range.setStartAfter(start);
      range.setEndBefore(end);
      return { range, start, end };
    });
    for (const range of [...ranges, ...wholeRanges]) {
      const walker = doc.createTreeWalker(range.commonAncestorContainer, NodeFilter.SHOW_TEXT);
      const nodes = range.commonAncestorContainer.nodeType === Node.TEXT_NODE ? [range.commonAncestorContainer] : [];
      while (walker.nextNode()) if (range.intersectsNode(walker.currentNode)) nodes.push(walker.currentNode);
      for (const node of nodes.reverse()) {
        const start = node === range.startContainer ? range.startOffset : 0;
        const end = node === range.endContainer ? range.endOffset : node.length;
        if (end <= start) continue;
        const selected = doc.createRange();
        selected.setStart(node, start);
        selected.setEnd(node, end);
        const mark = doc.createElement("span");
        mark.style.all = "unset";
        mark.className = name === "docserve-old" ? "docserve-deleted" : "docserve-added";
        selected.surroundContents(mark);
      }
    }
    for (const { range, start, end } of bookmarks) {
      range.setStartAfter(start);
      range.setEndBefore(end);
      start.remove();
      end.remove();
    }
  }
}

function stale() {
  if (state.phase !== "ready") return;
  for (const frame of [before, after]) {
    const doc = frame.contentDocument;
    if (!doc) continue;
    doc.defaultView.CSS?.highlights?.delete("docserve-old");
    doc.defaultView.CSS?.highlights?.delete("docserve-new");
    doc.defaultView.CSS?.highlights?.delete("docserve-old-whole");
    doc.defaultView.CSS?.highlights?.delete("docserve-new-whole");
    doc.querySelectorAll(".docserve-added, .docserve-deleted").forEach(element => element.classList.remove("docserve-added", "docserve-deleted"));
  }
  phase("stale", "Document changed. Refresh comparison to update marks.");
}

function renderPair() {
  for (const [side, control] of [["left", select], ["right", rightSelect]]) {
    control.replaceChildren();
    endpoints.forEach((endpoint, index) => {
      if (side === "left" && index === 0) return;
      const option = new Option(endpoint.label, String(index));
      option.disabled = side === "left" ? index <= pair.right : index >= pair.left;
      control.add(option);
    });
    control.value = String(pair[side]);
    control.disabled = false;
    const valid = index => index >= 0 && index < endpoints.length && (side === "left" ? index > pair.right : index < pair.left);
    versionButtons[side][0].disabled = !valid(pair[side] + 1);
    versionButtons[side][1].disabled = !valid(pair[side] - 1);
  }
}

function setEndpoint(side, index) {
  if (!pair || !Number.isInteger(index) || index < 0 || index >= endpoints.length ||
      (side === "left" ? index <= pair.right : index >= pair.left)) return;
  if (pair[side] === index) return;
  pair = { ...pair, [side]: index };
  renderPair();
  refresh();
}

async function refresh() {
  if (!pair || !documentURL) return;
  const selected = [endpoints[pair.left], endpoints[pair.right]];
  state.abort?.abort();
  const abort = state.abort = new AbortController();
  const generation = ++state.generation;
  phase("loading", "Loading rendered documents...");
  try {
    const responses = await Promise.all(selected.map(endpoint =>
      fetch(standalone(endpoint.url), { method: "HEAD", cache: "no-store", signal: abort.signal })));
    for (let i = 0; i < responses.length; i++) {
      if (!responses[i].ok) throw new Error(selected[i].working ? "The current document is no longer available." : "The selected revision is no longer available.");
    }
    await Promise.all([before, after].map((frame, i) => loadFrame(frame, selected[i].url, abort.signal)));
    await Promise.all([ready(before), ready(after)]);
    if (generation !== state.generation) return;
    const result = compare(blocks(before.contentDocument), blocks(after.contentDocument));
    const oldTargets = [], newTargets = [];
    for (const change of result.changes) for (const [block, targets] of [[change.old, oldTargets], [change.new, newTargets]]) {
      if (block?.text) targets.push(block.target ||= range(block, 0, block.text.length));
      if (block?.focus) targets.push(block.focus);
    }
    install(before.contentDocument, "docserve-old", result.oldRanges, result.oldWholeRanges, oldTargets);
    install(after.contentDocument, "docserve-new", result.newRanges, result.newWholeRanges, newTargets);
    state.changes = result.changes;
    state.anchors = result.anchors;
    state.index = -1;
    phase("ready", `${state.changes.length} changes.`);
    startOverview(generation);
  } catch (error) {
    if (generation === state.generation) phase("error", error.message);
  }
}

function selectChange(index) {
  if (state.phase !== "ready" || index < 0 || index >= state.changes.length) return;
  state.index = index;
  for (const button of document.querySelectorAll(".ruler .band")) {
    const selected = button.dataset.indices.split(",").map(Number).includes(index);
    button.classList.toggle("selected", selected);
    if (selected) button.setAttribute("aria-current", "true"); else button.removeAttribute("aria-current");
  }
  syncing = Boolean(state.changes[index].old && state.changes[index].new);
  for (const block of [state.changes[index].old, state.changes[index].new]) {
    if (!block) continue;
    const win = block.element.ownerDocument.defaultView;
    const rect = (block.focus || block.target || block.element).getBoundingClientRect();
    const offset = rect.height > win.innerHeight ? 0 : rect.height / 2 - win.innerHeight / 2;
    win.scrollTo(0, win.scrollY + rect.top + offset);
  }
  clearTimeout(syncTimer);
  syncTimer = setTimeout(() => { syncing = false; }, 100);
  status.textContent = `Change ${index + 1} of ${state.changes.length}.`;
}

function navigate(offset) {
  const index = state.index === -1 ? (offset < 0 ? state.changes.length - 1 : 0) : (state.index + offset + state.changes.length) % state.changes.length;
  selectChange(index);
}

function stopOverview() {
  const overview = state.overview;
  if (!overview) return;
  overview.abort.abort();
  overview.observers.forEach(observer => observer.disconnect());
  cancelAnimationFrame(overview.raf);
  overview.chooser?.remove();
  for (const pane of overview.panes) {
    pane.track.querySelector(".marks").replaceChildren();
    pane.track.querySelector(".bands").replaceChildren();
    pane.track.querySelector(".viewport").style.height = "0";
  }
  state.overview = null;
}

function startOverview(generation) {
  const overview = { generation, abort: new AbortController(), observers: [], raf: 0, chooser: null,
    panes: [["old", before], ["new", after]].map(([side, frame]) => ({ side, frame, track: document.getElementById(`compare-${side}-ruler`), signature: "" })) };
  state.overview = overview;
  const signal = overview.abort.signal;
  const schedule = () => {
    if (state.overview !== overview || overview.raf) return;
    overview.raf = requestAnimationFrame(() => {
      overview.raf = 0;
      if (state.overview === overview && state.generation === generation) overview.panes.forEach(pane => measurePane(pane, overview));
    });
  };
  for (const pane of overview.panes) {
    const doc = pane.frame.contentDocument, win = pane.frame.contentWindow;
    for (const event of ["scroll", "resize"]) win.addEventListener(event, schedule, { passive: true, signal });
    for (const event of ["load", "error"]) doc.addEventListener(event, schedule, { capture: true, signal });
    doc.fonts?.addEventListener("loadingdone", schedule, { signal });
    doc.addEventListener("serve-html-themechange", stale, { signal });
    const mutation = new MutationObserver(stale);
    mutation.observe(doc.body, { childList: true, characterData: true, subtree: true, attributes: true });
    overview.observers.push(mutation);
    const resize = new ResizeObserver(schedule);
    for (const element of [doc.body, doc.documentElement, pane.track]) resize.observe(element);
    overview.observers.push(resize);
  }
  document.addEventListener("pointerdown", event => {
    if (overview.chooser && !overview.chooser.contains(event.target) && !event.target.closest(".band")) closeChooser(overview);
  }, { signal });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && overview.chooser) { event.preventDefault(); closeChooser(overview, true); }
  }, { signal });
  schedule();
}

function closeChooser(overview, focus = false) {
  const button = overview.chooserButton;
  overview.chooser?.remove();
  overview.chooser = null;
  if (focus) button?.focus();
}

function measurePane(pane, overview) {
  const win = pane.frame.contentWindow, doc = pane.frame.contentDocument;
  const height = pane.track.clientHeight;
  const total = Math.max(doc.documentElement.scrollHeight, doc.body.scrollHeight, win.innerHeight, 1);
  const viewport = pane.track.querySelector(".viewport");
  viewport.style.top = `${Math.min(height, Math.max(0, win.scrollY / total * height))}px`;
  viewport.style.height = `${Math.min(height, win.innerHeight / total * height)}px`;
  const marks = [];
  state.changes.forEach((change, index) => {
    const block = change[pane.side];
    if (!block) return;
    const rect = (block.target || block.element).getBoundingClientRect();
    const top = Math.max(0, Math.min(height, (rect.top + win.scrollY) / total * height));
    const bottom = Math.max(top, Math.min(height, (rect.bottom + win.scrollY) / total * height));
    marks.push({ index, top, bottom });
  });
  marks.sort((a, b) => a.top - b.top || a.index - b.index);
  const signature = JSON.stringify([height, marks]);
  if (signature === pane.signature) return;
  pane.signature = signature;
  const ownsChooser = overview.chooser && pane.track.contains(overview.chooserButton);
  const focused = pane.track.contains(document.activeElement) || (ownsChooser && overview.chooser.contains(document.activeElement));
  const focusedIndices = ownsChooser ? overview.chooserButton.dataset.indices : document.activeElement?.dataset.indices;
  if (ownsChooser) closeChooser(overview);
  const marksRoot = pane.track.querySelector(".marks"), bandsRoot = pane.track.querySelector(".bands");
  marksRoot.replaceChildren();
  bandsRoot.replaceChildren();
  const bands = [];
  for (const mark of marks) {
    const visual = document.createElement("span");
    visual.className = "mark";
    visual.style.top = `${Math.min(mark.top, Math.max(0, height - 2))}px`;
    visual.style.height = `${Math.max(2, mark.bottom - mark.top)}px`;
    marksRoot.append(visual);
    const center = (mark.top + mark.bottom) / 2;
    const top = Math.max(0, Math.min(mark.top, center - 12, height - Math.min(24, height)));
    const bottom = Math.min(height, Math.max(mark.bottom, center + 12, top + 24));
    const last = bands.at(-1);
    if (last && top <= last.bottom) { last.bottom = Math.max(last.bottom, bottom); last.indices.push(mark.index); }
    else bands.push({ top, bottom, indices: [mark.index] });
  }
  for (const band of bands) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "band";
    button.dataset.indices = band.indices.join(",");
    if (band.indices.includes(state.index)) { button.classList.add("selected"); button.setAttribute("aria-current", "true"); }
    if (band.indices.length === 1) {
      const block = state.changes[band.indices[0]][pane.side];
      button.title = (block.text || block.extra || block.kind).replace(/\s+/g, " ").slice(0, 80);
    }
    button.style.top = `${band.top}px`;
    button.style.height = `${band.bottom - band.top}px`;
    button.setAttribute("aria-label", band.indices.length === 1 ? `Go to change ${band.indices[0] + 1}` : `Choose from ${band.indices.length} changes`);
    button.addEventListener("click", () => {
      if (band.indices.length === 1) { closeChooser(overview); selectChange(band.indices[0]); return; }
      if (overview.chooserButton === button && overview.chooser) { closeChooser(overview, true); return; }
      closeChooser(overview);
      const chooser = document.createElement("div");
      chooser.className = "chooser";
      chooser.setAttribute("aria-label", "Choose a change");
      for (const index of band.indices) {
        const option = document.createElement("button");
        option.type = "button";
        const block = state.changes[index][pane.side];
        option.textContent = `Change ${index + 1}: ${(block.text || block.extra || block.kind).replace(/\s+/g, " ").slice(0, 80)}`;
        option.addEventListener("click", () => { closeChooser(overview, true); selectChange(index); });
        chooser.append(option);
      }
      pane.track.parentElement.parentElement.append(chooser);
      overview.chooser = chooser;
      overview.chooserButton = button;
      chooser.firstElementChild.focus();
    });
    bandsRoot.append(button);
    if (focused && focusedIndices && band.indices.includes(Number(focusedIndices.split(",")[0]))) button.focus();
  }
}

let syncing = false;
let syncTimer;
for (const [source, target, index] of [[before, after, 0], [after, before, 1]]) {
  source.addEventListener("load", () => {
    if (state.phase === "ready") stale();
    source.contentWindow.addEventListener("scroll", () => {
      if (!sync.checked || syncing || state.phase !== "ready") return;
      const anchors = state.anchors || [];
      const anchor = anchors.reduce((best, item) => item[index].element.getBoundingClientRect().top <= 30 ? item : best, null);
      syncing = true;
      if (anchor) {
        const delta = anchor[1 - index].element.getBoundingClientRect().top - anchor[index].element.getBoundingClientRect().top;
        target.contentWindow.scrollBy(0, delta);
      } else {
        const src = source.contentDocument.scrollingElement || source.contentDocument.documentElement;
        const dst = target.contentDocument.scrollingElement || target.contentDocument.documentElement;
        target.contentWindow.scrollTo(0, source.contentWindow.scrollY / Math.max(1, src.scrollHeight - src.clientHeight) * (dst.scrollHeight - dst.clientHeight));
      }
      clearTimeout(syncTimer);
      syncTimer = setTimeout(() => { syncing = false; }, 50);
    }, { passive: true });
  });
}
window.addEventListener("pagehide", stopOverview);
window.addEventListener("pageshow", event => {
  if (event.persisted && state.phase === "ready") startOverview(state.generation);
});
select.addEventListener("change", () => setEndpoint("left", Number(select.value)));
rightSelect.addEventListener("change", () => setEndpoint("right", Number(rightSelect.value)));
for (const side of ["left", "right"]) {
  versionButtons[side][0].addEventListener("click", () => setEndpoint(side, pair[side] + 1));
  versionButtons[side][1].addEventListener("click", () => setEndpoint(side, pair[side] - 1));
}
document.getElementById("compare-refresh").addEventListener("click", refresh);
previous.addEventListener("click", () => navigate(-1));
next.addEventListener("click", () => navigate(1));

(async () => {
  if (!documentURL || !documentURL.startsWith("/") || documentURL.startsWith("//")) throw new Error("A document URL is required.");
  const response = await fetch(`/__serve_html__/api/git-history?${new URLSearchParams({ url: documentURL })}`);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "History could not be loaded.");
  endpoints = [{ working: true, label: "Current working file", url: documentURL }, ...data.revisions.map(revision => ({
    label: `${revision.short}  ${revision.datetime}  ${revision.subject}`, url: revision.url, commit: revision.commit,
  }))];
  if (endpoints.length === 1) { after.src = standalone(documentURL); phase("unavailable", data.reason || "No previous version."); return; }
  const defaultIndex = endpoints.findIndex(endpoint => endpoint.commit && endpoint.commit === data.default);
  pair = { left: defaultIndex > 0 ? defaultIndex : 1, right: 0 };
  renderPair();
  await refresh();
})().catch(error => phase("error", error.message));
