// Run with: npm --prefix tools/serve-html-assets test
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, mkdir, rm, utimes, writeFile } from "node:fs/promises";
import http from "node:http";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test, { after, before } from "node:test";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(path.join(root, "tools/serve-html-assets/package.json"));
const { chromium } = require("playwright");
const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="60"><rect width="160" height="60" fill="#0969da"/><text x="15" y="35" fill="white">External SVG</text></svg>';
const filename = "한글 review #1's ?.MD";
const htmlFilename = 'review # 한?.HTML';
let directory, extraDirectory, cacheDirectory, server, images, browser, baseURL;
let serverOutput = "";

before(async () => {
  directory = await mkdtemp(path.join(os.tmpdir(), "serve-html-browser-"));
  extraDirectory = await mkdtemp(path.join(os.tmpdir(), "serve-html-browser-extra-"));
  execFileSync('git', ['init', '-q', extraDirectory]);
  cacheDirectory = await mkdtemp(path.join(os.tmpdir(), "serve-html-browser-cache-"));
  await mkdir(path.join(directory, "nested/figures"), { recursive: true });
  images = http.createServer((request, response) => {
    response.writeHead(200, { "Content-Type": "image/svg+xml" });
    response.end(svg);
  }).listen(0, "127.0.0.1");
  await once(images, "listening");
  const remote = `http://127.0.0.1:${images.address().port}/remote.svg`;
  await writeFile(path.join(directory, "nested/figures/architecture.svg"), svg);
  await writeFile(path.join(directory, "nested", filename), [
    "# Markdown preview", "", "## Storage layout", "",
    "| Feature | Result |", "| --- | --- |", "| Markdown | Rendered |", "",
    "- [x] Task complete", "", "~~Deleted~~", "",
    "![Relative SVG](figures/architecture.svg)", "", `![Remote SVG](${remote})`, "",
    "[Next document](../next.markdown#next-heading)", "",
    "Inline math: $E = mc^2$", "", "$$", "\\int_0^1 x^2\\,dx = \\frac{1}{3}", "$$", "",
    "```mermaid", "flowchart LR", "    A[Markdown] --> B[Preview]", "```", "",
    "```mermaid", "sequenceDiagram", "    Alice->>Bob: Hello", "```", "",
    "```python", "value = '$ordinary_code$'", "```", "",
    "`$literal_math$`", "", "## Storage layout", "",
    '<script>globalThis.previewXss = true</script>',
    '<img src="figures/architecture.svg" onload="globalThis.previewXss = true">',
    "[Unsafe](javascript:alert(1))", "",
  ].join("\n"));
  await mkdir(path.join(directory, 'render-previews'), { recursive: true });
  await writeFile(path.join(directory, 'render-previews/한글 #?.MARKDOWN'), [
    '# Rendered finder document', '', '| Feature | Result |', '| --- | --- |', '| Preview | Rendered |', '',
    '![Local figure](figure.svg)', '', 'Inline math: $E = mc^2$', '',
    '```mermaid', 'flowchart LR', 'A --> B', '```', '',
    '<script>parent.previewExecuted = true;</script>',
    '<img src="figure.svg" onload="parent.previewExecuted = true;">',
  ].join('\n'));
  await writeFile(path.join(directory, 'render-previews/figure.svg'), svg);
  await writeFile(path.join(directory, 'render-previews/style.css'), 'body { background: rgb(17, 24, 39); color: white; }');
  await writeFile(path.join(directory, 'render-previews/한글 #?.HTM'), `<!doctype html><meta charset="utf-8">
    <link rel="stylesheet" href="style.css"><h1>Rendered finder HTML</h1><img src="figure.svg">
    <script>window.previewExecuted = true; parent.previewExecuted = true;</script>
    <img src="figure.svg" onload="window.previewExecuted = true;">
    <a href="/" target="_top">Leave preview</a>`);
  await writeFile(path.join(directory, "next.markdown"), "# Next heading\n\nYou followed a Markdown link.\n");
  await writeFile(path.join(directory, "broken.md"), [
    "# Surviving content", "", "$\\notARealCommand$", "",
    "```mermaid", "this is not a diagram", "```", "",
    "```mermaid", "flowchart LR", "A --> B", "```", "", "Final paragraph.",
  ].join("\n"));
  await writeFile(path.join(directory, "plain.md"), "# Plain document\n\nNo diagrams or equations.\n");
  await mkdir(path.join(extraDirectory, 'docs'), { recursive: true });
  const absoluteMarkdown = path.join(extraDirectory, 'docs/한글 #?.md');
  const absoluteHTML = path.join(extraDirectory, 'docs/page.html');
  await writeFile(path.join(extraDirectory, 'docs/figure.svg'), svg);
  await writeFile(path.join(extraDirectory, 'docs/style.css'), 'body { background: rgb(17, 24, 39); color: white; }');
  await writeFile(absoluteMarkdown, '# Extra Markdown\n\n![Extra figure](figure.svg)\n\n[Next page](next.md)\n');
  await writeFile(path.join(extraDirectory, 'docs/next.md'), '# Extra next page\n');
  await writeFile(path.join(extraDirectory, 'other.md'), '# Extra root document\n');
  await writeFile(absoluteHTML, `<!doctype html><title>Extra HTML</title>
    <link rel="stylesheet" href="style.css"><h1 id="target">Extra HTML</h1><img src="figure.svg">
    <script>window.extraScript = true;</script><a href="${encodeURI(absoluteMarkdown).replaceAll('#', '%23').replaceAll('?', '%3F')}">Extra Markdown</a>`);
  const extraHTMLURL = encodeURI(absoluteHTML);
  await writeFile(path.join(directory, 'absolute.md'), `# Absolute links\n\n[Project document](${encodeURI(path.join(directory, 'plain.md'))})\n\n[Extra document](${extraHTMLURL}?keep=%20&other=%2B#target)\n\n![Absolute figure](${encodeURI(path.join(extraDirectory, 'docs/figure.svg'))})`);
  await writeFile(path.join(directory, 'absolute.html'), `<h1>Absolute HTML links</h1>
    <a href="${extraHTMLURL}?keep=%20&amp;other=%2B#target">Extra document</a>`);
  await writeFile(path.join(directory, "existing.html"), "<!doctype html><title>Existing HTML</title><h1>Original page</h1>");
  await writeFile(path.join(directory, "index.html"), "<!doctype html><title>Selected index</title><h1>Root index page</h1>");
  await writeFile(path.join(directory, "nested/index.htm"), "<!doctype html><title>Selected nested index</title><h1>Nested index page</h1>");
  await mkdir(path.join(directory, 'navigation/empty'), { recursive: true });
  await writeFile(path.join(directory, 'navigation/style.css'), 'body { background: rgb(17, 24, 39); color: white; }');
  await writeFile(path.join(directory, 'navigation/helper.html'), '<title>Supporting frame</title><p>Supporting content</p>');
  await writeFile(path.join(directory, 'navigation', htmlFilename), `<!doctype html><meta charset="utf-8"><title>Interactive HTML</title>
    <link rel="stylesheet" href="style.css"><h1>Interactive document</h1>
    <button id="counter">Count: 0</button><script>let count = 0; document.getElementById('counter').onclick = event => { event.target.textContent = 'Count: ' + ++count; };</script>
    <a href="second.htm?keep=%20&amp;other=%2B#target">Next HTML</a>
    <a href="../plain.md">Read Markdown</a><iframe src="helper.html" hidden></iframe>`);
  await writeFile(path.join(directory, 'navigation/second.htm'), '<title>Second HTML</title><h1 id="target">Second document</h1><a href="' + encodeURIComponent(htmlFilename) + '">First HTML</a>');
  await mkdir(path.join(directory, "ordering/subdir"), { recursive: true });
  for (const [index, name] of ["Alpha.md", "report10.md", "report2.md", "zebra.md"].entries()) {
    const file = path.join(directory, "ordering", name);
    await writeFile(file, "# A heading unrelated to the filename\n");
    await utimes(file, 1700000000 + index, 1700000000 + index);
  }
  await utimes(path.join(directory, "ordering/subdir"), 1600000000, 1600000000);
  await mkdir(path.join(directory, 'search-examples/empty'), { recursive: true });
  await writeFile(path.join(directory, 'search-examples/guide.md'), '# Search example\n한글 Needle.literal\nneedleXliteral\n');
  await writeFile(path.join(directory, '.finder-hidden.md'), 'Needle.literal\n');
  await writeFile(path.join(directory, 'search-examples/long.txt'), '한'.repeat(5000) + 'farneedle\n');
  await mkdir(path.join(directory, 'filename-examples/nested.md'), { recursive: true });
  for (const name of ['guide.md', 'draft.md', 'notes.txt', 'nested.md/plain.txt', '한글 #.MD']) {
    await writeFile(path.join(directory, 'filename-examples', name), 'filename-filter-token\n');
  }
  await mkdir(path.join(directory, 'updates/nested'), { recursive: true });
  for (const [index, name] of ['old.md', 'nested/new #.HTML', 'latest.txt'].entries()) {
    const file = path.join(directory, 'updates', name);
    await writeFile(file, name.endsWith('.HTML') ? '<h1>Recently updated HTML</h1><script>window.previewExecuted = true;</script>' : '# Recently updated example\n');
    await utimes(file, 1800000000 + index, 1800000000 + index);
  }

  server = spawn(process.env.HTML_SERVE_TEST_PYTHON || "python3", ["-B",
    process.env.HTML_SERVE_TEST_SCRIPT || path.join(root, "src/html_serve/cli.py"),
    "--directory", directory, "--bind", "127.0.0.1"], {
    stdio: ["ignore", "pipe", "pipe"], env: { ...process.env, XDG_CACHE_HOME: cacheDirectory },
  });
  server.stdout.on("data", (data) => { serverOutput += data; });
  server.stderr.on("data", (data) => { serverOutput += data; });
  const deadline = Date.now() + 5000;
  while (!serverOutput.includes("Ctrl+C")) {
    if (server.exitCode !== null || Date.now() > deadline) throw new Error(`Server startup failed: ${serverOutput}`);
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  baseURL = serverOutput.match(/http:\/\/127\.0\.0\.1:\d+\//)[0];
  browser = await chromium.launch({
    headless: true,
    ...(process.env.SERVE_HTML_CHROMIUM_EXECUTABLE ? { executablePath: process.env.SERVE_HTML_CHROMIUM_EXECUTABLE } : {}),
  });
});

after(async () => {
  await browser?.close();
  if (server && server.exitCode === null) {
    const stopped = once(server, "exit");
    server.kill("SIGINT");
    await stopped;
  }
  if (images?.listening) await new Promise((resolve) => images.close(resolve));
  if (directory) await rm(directory, { recursive: true, force: true });
  if (extraDirectory) await rm(extraDirectory, { recursive: true, force: true });
  if (cacheDirectory) await rm(cacheDirectory, { recursive: true, force: true });
});

async function ready(page) {
  await page.locator('#content[aria-busy="false"]').waitFor();
  assert.equal(await page.locator(".render-error").count(), 0, await page.locator("#content").innerText());
}

async function diagramsReady(page) {
  await page.waitForFunction(() => [...document.querySelectorAll(".diagram")]
    .every((element) => element.getAttribute("aria-busy") === "false"));
}

async function localOnly(page) {
  const external = [];
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1") {
      external.push(url.href);
      await route.abort();
    } else {
      await route.continue();
    }
  });
  return external;
}

test("directories show listings until an index page is clicked", async () => {
  const page = await browser.newPage();
  try {
    await page.goto(baseURL);
    assert.equal(await page.getByRole("heading").innerText(), "Directory listing for /");
    await page.getByRole("link", { name: "index.html", exact: true }).click();
    await page.waitForLoadState('domcontentloaded');
    assert.equal(await page.title(), "Selected index");
    assert.equal(await page.frameLocator('#document-frame').locator("h1").innerText(), "Root index page");
    await page.goto(baseURL + "nested");
    assert.equal(new URL(page.url()).pathname, "/nested/");
    assert.equal(await page.getByRole("heading").innerText(), "Directory listing for /nested/");
    await page.getByRole("link", { name: "index.htm", exact: true }).click();
    await page.waitForLoadState('domcontentloaded');
    assert.equal(await page.title(), "Selected nested index");
    assert.equal(await page.frameLocator('#document-frame').locator("h1").innerText(), "Nested index page");
  } finally {
    await page.close();
  }
});

test('copy buttons use absolute server paths in listings, Markdown and directory panes', async () => {
  const context = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'] });
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  async function copied(button, expected) {
    await button.click();
    await page.waitForFunction(async value => await navigator.clipboard.readText() === value, expected);
    assert.equal(await page.locator('.copy-path-status').textContent(), 'Path copied.');
  }
  try {
    await page.goto(baseURL + 'nested/?sort=title&order=desc');
    const initialURL = page.url();
    await copied(page.getByRole('button', { name: `Copy path for ${filename}`, exact: true }), path.join(directory, 'nested', filename));
    assert.equal(page.url(), initialURL);
    await copied(page.getByRole('button', { name: 'Copy directory path', exact: true }), path.join(directory, 'nested'));
    await copied(page.getByRole('button', { name: 'Copy path for figures', exact: true }), path.join(directory, 'nested/figures'));
    await page.getByRole('link', { name: filename, exact: true }).click();
    await ready(page);
    await copied(page.locator('#document-banner .copy-path-button'), path.join(directory, 'nested', filename));
    await page.locator('#directory-toggle').click();
    await copied(page.locator('#directory-entries').getByRole('button', { name: 'Copy path for index.htm', exact: true }), path.join(directory, 'nested/index.htm'));
    assert.equal(new URL(page.url()).pathname, '/nested/' + encodeURIComponent(filename).replaceAll("'", '%27').replaceAll('?', '%3F'));
    await page.locator('#close-directory').click();
    await page.locator('#compact-view').click();
    await copied(page.locator('#document-floating .copy-path-button'), path.join(directory, 'nested', filename));
    await page.setViewportSize({ width: 320, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  } finally { await context.close(); }
});

test('HTML copy buttons follow framed navigation in the banner and compact controls', async () => {
  const context = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'] });
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  try {
    await page.goto(baseURL + 'navigation/' + encodeURIComponent(htmlFilename));
    const child = page.frameLocator('#document-frame');
    await child.getByRole('heading', { name: 'Interactive document' }).waitFor();
    await page.locator('#document-banner .copy-path-button').click();
    await page.waitForFunction(async value => await navigator.clipboard.readText() === value, path.join(directory, 'navigation', htmlFilename));
    await child.getByRole('link', { name: 'Next HTML', exact: true }).click();
    await page.waitForURL(baseURL + 'navigation/second.htm?keep=%20&other=%2B#target');
    await page.locator('#compact-view').click();
    await page.locator('#document-floating .copy-path-button').click();
    await page.waitForFunction(async value => await navigator.clipboard.readText() === value, path.join(directory, 'navigation/second.htm'));
    await child.getByRole('link', { name: 'First HTML', exact: true }).click();
    await child.getByRole('link', { name: 'Read Markdown', exact: true }).click();
    await page.waitForURL(baseURL + 'plain.md');
    await page.locator('#document-floating .copy-path-button').click();
    await page.waitForFunction(async value => await navigator.clipboard.readText() === value, path.join(directory, 'plain.md'));
  } finally { await context.close(); }
});

test('copy paths work on insecure HTTP and offer manual copying when the browser blocks it', async () => {
  const context = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'] });
  const page = await context.newPage();
  const reader = await context.newPage();
  page.setDefaultTimeout(5000);
  try {
    await page.route('http://docserve.test:*/**', async route => {
      const url = new URL(route.request().url());
      url.hostname = '127.0.0.1';
      await route.fulfill({ response: await route.fetch({ url: url.href }) });
    });
    await reader.goto(baseURL + 'plain.md');
    await page.goto(baseURL.replace('127.0.0.1', 'docserve.test') + 'nested/');
    assert.equal(await page.evaluate(() => isSecureContext), false);
    assert.equal(await page.evaluate(() => !!navigator.clipboard), false);
    await page.bringToFront();
    const button = page.getByRole('button', { name: `Copy path for ${filename}`, exact: true });
    await button.click();
    await page.locator('.copy-path-status').waitFor();
    assert.equal(await button.evaluate(node => node === document.activeElement), true);
    await reader.bringToFront();
    assert.equal(await reader.evaluate(() => navigator.clipboard.readText()), path.join(directory, 'nested', filename));
    await reader.evaluate(() => navigator.clipboard.writeText('Waiting for finder copy'));
    await page.bringToFront();
    await page.getByRole('button', { name: 'Find files', exact: true }).click();
    await page.getByRole('searchbox', { name: 'Search query' }).fill('nested/' + filename);
    const finderCopy = page.locator('#finder-copy-path');
    await page.waitForFunction(() => document.querySelector('#finder-copy-path')?.disabled === false);
    await finderCopy.click();
    assert.equal(await page.locator('#finder .copy-path-status').isVisible(), true);
    assert.equal(await finderCopy.evaluate(node => node === document.activeElement), true);
    await reader.bringToFront();
    assert.equal(await reader.evaluate(() => navigator.clipboard.readText()), path.join(directory, 'nested', filename));
    await page.bringToFront();
    await page.evaluate(() => { document.execCommand = () => false; });
    await finderCopy.click();
    const dialog = page.getByRole('dialog', { name: 'Copy server path', exact: true });
    await dialog.waitFor();
    const field = dialog.getByRole('textbox', { name: 'Server path', exact: true });
    assert.equal(await field.inputValue(), path.join(directory, 'nested', filename));
    assert.equal(await field.evaluate(node => node.selectionStart === 0 && node.selectionEnd === node.value.length), true);
    await dialog.getByRole('button', { name: 'Close', exact: true }).click();
    assert.equal(await finderCopy.evaluate(node => node === document.activeElement), true);
    await page.locator('#finder-close').click();
    await reader.bringToFront();
    await reader.evaluate(() => { Object.defineProperty(navigator, 'clipboard', { value: { writeText: async () => { throw new Error('Permission denied'); } } }); });
    await reader.locator('#document-banner .copy-path-button').click();
    await reader.locator('.copy-path-status').waitFor();
  } finally { await context.close(); }
});

test("finder previews fuzzy file paths and navigates directories with the keyboard", async () => {
  const page = await browser.newPage();
  try {
    await page.goto(baseURL + 'nested/');
    const trigger = page.getByRole('button', { name: 'Find files', exact: true });
    await trigger.click({ timeout: 3000 });
    const dialog = page.getByRole('dialog', { name: 'Find files', exact: true });
    await dialog.waitFor();
    const query = dialog.getByRole('searchbox', { name: 'Search query' });
    await query.fill('nfigarchsvg');
    await dialog.getByRole('option').filter({ hasText: 'nested/figures/architecture.svg' }).waitFor();
    await page.waitForFunction(() => document.querySelector('#finder-preview')?.textContent.includes('<svg'));
    assert.equal(new URL(page.url()).pathname, '/nested/');
    await query.press('Escape');
    await dialog.waitFor({ state: 'hidden' });
    assert.equal(await trigger.evaluate(element => element === document.activeElement), true);
    await page.getByRole('button', { name: 'Find directories', exact: true }).click();
    await page.getByRole('searchbox', { name: 'Search query' }).fill('nfig');
    await page.getByRole('option').filter({ hasText: 'nested/figures' }).waitFor();
    await Promise.all([page.waitForURL(baseURL + 'nested/figures/'), page.keyboard.press('Enter')]);
    await page.getByRole('link', { name: 'Go to root', exact: true }).click();
    assert.equal(page.url(), baseURL);
    await page.getByRole('link', { name: 'plain.md', exact: true }).click();
    await ready(page);
    await page.getByRole('button', { name: 'Directory listing', exact: true }).click();
    await page.getByRole('link', { name: 'Full directory listing', exact: true }).click();
    assert.equal(page.url(), baseURL);
  } finally { await page.close(); }
});

for (const width of [1280, 390]) {
  test(`finder renders Markdown and HTML with relative assets and no preview visits at ${width}px`, async () => {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    page.setDefaultTimeout(10000);
    const external = await localOnly(page);
    try {
      // Reproduce browsers on plain HTTP that omit Fetch Metadata headers.
      await page.route('**/*', async route => {
        const headers = { ...route.request().headers() };
        for (const name of Object.keys(headers)) if (name.startsWith('sec-fetch-')) delete headers[name];
        await route.fallback({ headers });
      });
      await page.goto(baseURL);
      await page.getByRole('button', { name: 'Find files', exact: true }).click();
      const query = page.getByRole('searchbox', { name: 'Search query' });
      const format = page.getByRole('combobox', { name: 'Preview format' });
      const frame = page.frameLocator('#finder-preview iframe');
      await query.fill('render-previews/MARKDOWN');
      await frame.locator('#content[aria-busy="false"]').waitFor();
      assert.equal(await frame.getByRole('heading').innerText(), 'Rendered finder document');
      assert.equal(await frame.locator('table tbody td').first().innerText(), 'Preview');
      assert.equal(await frame.locator('.katex').count(), 1);
      assert.equal(await frame.locator('.diagram svg').count(), 1);
      assert.equal(await frame.locator('.toolbar').isVisible(), false);
      assert.equal(await frame.locator('#navigation-tools').count(), 0);
      assert.equal(await frame.getByAltText('Local figure').evaluate(img => img.complete && img.naturalWidth > 0), true);
      assert.equal(await page.evaluate(() => window.previewExecuted), undefined);
      assert.match(await page.locator('#finder-preview iframe').getAttribute('src'), /%23%3F\.MARKDOWN/);
      await format.selectOption('source');
      assert.match(await page.locator('#finder-preview').innerText(), /# Rendered finder document/);
      assert.equal(await page.locator('#finder-preview iframe').count(), 0);
      await format.selectOption('rendered');
      await frame.getByRole('heading', { name: 'Rendered finder document', exact: true }).waitFor();
      await query.fill('render-previews/HTM');
      await frame.getByRole('heading', { name: 'Rendered finder HTML', exact: true }).waitFor();
      assert.equal(await frame.locator('body').evaluate(node => getComputedStyle(node).backgroundColor), 'rgb(17, 24, 39)');
      assert.equal(await frame.locator('img').first().evaluate(img => img.complete && img.naturalWidth > 0), true);
      assert.equal(await frame.locator('body').evaluate(() => window.previewExecuted), undefined);
      assert.equal(await page.evaluate(() => window.previewExecuted), undefined);
      await frame.getByRole('link', { name: 'Leave preview' }).click();
      assert.equal(page.url(), baseURL);
      await format.selectOption('source');
      assert.match(await page.locator('#finder-preview').innerText(), /<h1>Rendered finder HTML<\/h1>/);
      await format.selectOption('rendered');
      await frame.getByRole('heading', { name: 'Rendered finder HTML', exact: true }).waitFor();
      assert.equal(await page.locator('#finder').evaluate(node => node.scrollWidth <= node.clientWidth), true);
      if (width === 390) {
        const resultsBounds = await page.locator('#finder-results').boundingBox();
        const previewBounds = await page.locator('#finder-preview iframe').boundingBox();
        assert.ok(previewBounds.height > 100 && previewBounds.width > 100);
        assert.ok(previewBounds.y > resultsBounds.y);
      }
      const recent = await page.request.get(baseURL + '__serve_html__/api/recent?q=render-previews');
      assert.deepEqual((await recent.json()).results, []);
      assert.deepEqual(external, []);
      await query.press('Escape');
      await page.locator('#finder-preview iframe').waitFor({ state: 'detached' });
    } finally { await page.close(); }
  });
}

test('content finder highlights Unicode matches and exposes scope, hidden files and regex errors', async () => {
  const page = await browser.newPage();
  try {
    await page.goto(baseURL + 'nested/');
    await page.getByRole('button', { name: 'Find contents', exact: true }).click();
    const query = page.getByRole('searchbox', { name: 'Search query' });
    await query.fill('needle.literal');
    await page.getByRole('option').filter({ hasText: 'search-examples/guide.md' }).waitFor();
    await page.frameLocator('#finder-preview iframe').getByRole('heading', { name: 'Search example', exact: true }).waitFor();
    await page.getByRole('combobox', { name: 'Preview format' }).selectOption('source');
    await page.waitForFunction(() => document.querySelector('#finder-preview mark')?.textContent === 'Needle.literal');
    assert.equal(await page.locator('#finder-results [role="option"]').count(), 1);
    await page.getByLabel('Include hidden and ignored', { exact: true }).check();
    await page.getByRole('option').filter({ hasText: '.finder-hidden.md' }).waitFor();
    assert.equal(await page.locator('#finder-results [role="option"]').count(), 2);
    await page.getByRole('combobox', { name: 'Search scope' }).selectOption('current');
    await page.waitForFunction(() => document.querySelector('#finder-status').textContent === '0 results.');
    await page.getByRole('combobox', { name: 'Search scope' }).selectOption('root');
    await page.getByLabel('Regex', { exact: true }).check();
    await query.fill('[');
    await page.waitForFunction(() => document.querySelector('#finder-status').textContent.includes('regex parse error'));
    assert.equal(await page.locator('#finder-results [role="option"]').count(), 0);
    assert.equal(await page.locator('#finder-open').isVisible(), false);
    await page.getByLabel('Regex', { exact: true }).uncheck();
    await query.fill('farneedle');
    await page.waitForFunction(() => document.querySelector('#finder-preview mark')?.textContent === 'farneedle');
  } finally { await page.close(); }
});

test('content filename filters include, exclude, report errors and fit desktop and narrow screens', async () => {
  for (const width of [1280, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 844 } });
    try {
      await page.goto(baseURL);
      await page.getByRole('button', { name: 'Find contents', exact: true }).click();
      const query = page.getByRole('searchbox', { name: 'Search query' });
      const include = page.getByRole('textbox', { name: 'Include filenames (regex)', exact: true });
      const exclude = page.getByRole('textbox', { name: 'Exclude filenames (regex)', exact: true });
      const paths = page.locator('#finder-results .finder-result-path');
      const waitForCount = count => page.waitForFunction(count => document.querySelector('#finder-status').textContent === `${count} result${count === 1 ? '' : 's'}.`, count);
      await query.fill('filename-filter-token');
      await waitForCount(5);
      await include.fill('\\.md$');
      await waitForCount(3);
      assert.deepEqual((await paths.allTextContents()).sort(), ['filename-examples/draft.md', 'filename-examples/guide.md', 'filename-examples/한글 #.MD']);
      await exclude.fill('^draft');
      await waitForCount(2);
      assert.deepEqual((await paths.allTextContents()).sort(), ['filename-examples/guide.md', 'filename-examples/한글 #.MD']);
      await page.getByLabel('Regex', { exact: true }).check();
      await waitForCount(2);
      await page.getByRole('combobox', { name: 'Preview format' }).selectOption('source');
      await page.waitForFunction(() => document.querySelector('#finder-preview mark')?.textContent === 'filename-filter-token');
      assert.equal(await page.locator('#finder').evaluate(element => element.scrollWidth <= element.clientWidth), true);
      if (width === 390) {
        const resultBounds = await page.locator('#finder-results').boundingBox();
        const previewBounds = await page.locator('.finder-preview-pane').boundingBox();
        assert.ok(resultBounds.height > 50 && previewBounds.height > 50);
        assert.ok(previewBounds.y > resultBounds.y);
      }
      for (const [control, label] of [[include, 'Include filenames'], [exclude, 'Exclude filenames']]) {
        await control.fill('[');
        await page.waitForFunction(label => document.querySelector('#finder-status').textContent.startsWith(label + ':'), label);
        assert.equal(await paths.count(), 0);
        assert.equal(await page.locator('#finder-open').isVisible(), false);
        await control.fill(control === include ? '\\.md$' : '^draft');
        await waitForCount(2);
      }
      await page.getByRole('tab', { name: 'Files', exact: true }).click();
      assert.equal(await include.isVisible(), false);
      await page.getByRole('tab', { name: 'Contents', exact: true }).click();
      await waitForCount(2);
      await include.fill('');
      await waitForCount(4);
      await exclude.fill('');
      await waitForCount(5);
    } finally { await page.close(); }
  }
});

test('recent visits filter files and directories, reopen paths and fit a narrow screen', async () => {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  try {
    await page.goto(baseURL + 'search-examples/');
    await page.getByRole('link', { name: 'guide.md', exact: true }).click();
    await ready(page);
    await page.getByRole('button', { name: 'Directory listing', exact: true }).click();
    await page.getByRole('link', { name: 'Full directory listing', exact: true }).click();
    await page.getByRole('link', { name: 'Go to root', exact: true }).click();
    await page.getByRole('button', { name: 'Recently visited', exact: true }).click();
    await page.getByRole('searchbox', { name: 'Search query' }).fill('search-examples');
    await page.waitForFunction(() => document.querySelector('#finder-status').textContent === '2 results.');
    const paths = page.locator('#finder-results .finder-result-path');
    const kind = page.getByRole('combobox', { name: 'Recent visit type' });
    assert.equal(await kind.inputValue(), 'all');
    assert.deepEqual(await paths.allTextContents(), ['search-examples/', 'search-examples/guide.md']);
    await kind.selectOption('directory');
    await page.waitForFunction(() => document.querySelector('#finder-status').textContent === '1 result.');
    assert.deepEqual(await paths.allTextContents(), ['search-examples/']);
    assert.equal(await page.getByRole('link', { name: 'Open directory', exact: true }).isVisible(), true);
    await page.getByRole('searchbox', { name: 'Search query' }).fill('guide');
    await page.waitForFunction(() => document.querySelector('#finder-status').textContent === '0 results.');
    await kind.selectOption('file');
    await page.waitForFunction(() => document.querySelector('#finder-status').textContent === '1 result.');
    assert.deepEqual(await paths.allTextContents(), ['search-examples/guide.md']);
    await page.getByRole('searchbox', { name: 'Search query' }).fill('search-examples');
    await page.waitForFunction(() => document.querySelector('#finder-status').textContent === '1 result.');
    await kind.selectOption('all');
    await page.waitForFunction(() => document.querySelector('#finder-status').textContent === '2 results.');
    const file = page.getByRole('option').filter({ hasText: 'search-examples/guide.md' });
    await file.click();
    await page.frameLocator('#finder-preview iframe').getByRole('heading', { name: 'Search example', exact: true }).waitFor();
    const resultBounds = await page.locator('#finder-results').boundingBox();
    const previewBounds = await page.locator('.finder-preview-pane').boundingBox();
    assert.ok(previewBounds.y > resultBounds.y);
    assert.equal(await page.locator('#finder').evaluate(element => element.scrollWidth <= element.clientWidth), true);
    if (process.env.SERVE_HTML_FINDER_SCREENSHOT) {
      await page.screenshot({ path: process.env.SERVE_HTML_FINDER_SCREENSHOT });
    }
    await page.getByRole('link', { name: 'Open file', exact: true }).click();
    await ready(page);
    assert.equal(new URL(page.url()).pathname, '/search-examples/guide.md');
    const recent = await page.request.get(baseURL + '__serve_html__/api/recent?q=.finder-hidden');
    assert.deepEqual((await recent.json()).results, []);
  } finally { await page.close(); }
});

test('recently updated shows progress and elapsed time until a slow search completes', async () => {
  const page = await browser.newPage();
  page.setDefaultTimeout(5000);
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  await page.route('**/__serve_html__/api/search?**', async route => {
    await pending;
    await route.continue();
  });
  try {
    await page.goto(baseURL + 'updates/');
    await page.getByRole('button', { name: 'Recently updated', exact: true }).click();
    const progress = page.getByRole('progressbar', { name: 'Search in progress' });
    await progress.waitFor();
    assert.match(await page.locator('#finder-status').textContent(), /Scanning files.*modification times/);
    await page.waitForFunction(() => /[1-9]\d*s elapsed/.test(document.querySelector('#finder-elapsed').textContent));
    assert.equal(await page.locator('#finder-results').getAttribute('aria-busy'), 'true');
    release();
    await page.locator('#finder-results[aria-busy="false"]').waitFor();
    assert.equal(await progress.isVisible(), false);
    assert.equal(await page.locator('#finder-elapsed').isVisible(), false);
    assert.match(await page.locator('#finder-status').textContent(), /^\d+ results?\./);
  } finally {
    release();
    await page.close();
  }
});

test('recently updated distinguishes newest-result limits from incomplete scans', async () => {
  const page = await browser.newPage();
  let incomplete = false;
  await page.route('**/__serve_html__/api/search?**', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(incomplete
      ? { results: [], truncated: true, scan_complete: false, message: 'Scan exceeded the 30-second limit. Search a narrower directory.' }
      : { results: [{ path: 'updates/old.md', kind: 'file', url: '/updates/old.md', modified_at: '2023-11-14T22:13:20+00:00' }], truncated: true, scan_complete: true }),
  }));
  try {
    await page.goto(baseURL + 'updates/');
    await page.getByRole('button', { name: 'Recently updated', exact: true }).click();
    const status = page.locator('#finder-status');
    await page.waitForFunction(() => document.querySelector('#finder-status').textContent === '1 result. Showing the newest matches.');
    assert.equal(await page.getByRole('progressbar', { name: 'Search in progress' }).isVisible(), false);
    incomplete = true;
    await page.getByRole('searchbox', { name: 'Search query' }).fill('retry');
    await page.waitForFunction(() => document.querySelector('#finder-status').textContent.includes('Scan exceeded the 30-second limit.'));
    assert.equal(await page.locator('#finder-results [role="option"]').count(), 0);
    assert.equal(await page.locator('#finder-open').isVisible(), false);
    assert.equal((await status.textContent()).includes('Showing the newest'), false);
  } finally { await page.close(); }
});

test('recently updated keeps progress on query changes and clears it when closed', async () => {
  const page = await browser.newPage();
  page.setDefaultTimeout(5000);
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  await page.route('**/__serve_html__/api/search?**', async route => {
    await pending;
    await route.continue();
  });
  try {
    await page.goto(baseURL + 'updates/');
    const first = page.waitForRequest('**/__serve_html__/api/search?**');
    const trigger = page.getByRole('button', { name: 'Recently updated', exact: true });
    await trigger.click();
    await first;
    const second = page.waitForRequest(request => new URL(request.url()).searchParams.get('q') === 'old');
    await page.getByRole('searchbox', { name: 'Search query' }).fill('old');
    await second;
    assert.equal(await page.getByRole('progressbar', { name: 'Search in progress' }).isVisible(), true);
    assert.equal(await page.locator('#finder-results').getAttribute('aria-busy'), 'true');
    await page.getByRole('button', { name: 'Close', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('#finder-progress').hidden);
    assert.equal(await page.locator('#finder-progress').getAttribute('hidden'), '');
    assert.equal(await page.locator('#finder-elapsed').getAttribute('hidden'), '');
    assert.equal(await page.locator('#finder-results').getAttribute('aria-busy'), 'false');
    assert.equal(await trigger.evaluate(node => node === document.activeElement), true);
    release();
  } finally {
    release();
    await page.close();
  }
});

for (const width of [1920, 390, 320]) {
  test(`recently updated previews recursive files and allows clearing the default filename filter at ${width}px`, async () => {
    const page = await browser.newPage({ viewport: { width, height: 900 }, permissions: ['clipboard-read', 'clipboard-write'] });
    page.setDefaultTimeout(5000);
    try {
      await page.goto(baseURL + 'updates/');
      const trigger = page.getByRole('button', { name: 'Recently updated', exact: true });
      assert.equal(await trigger.evaluate(node => node.previousElementSibling.textContent), 'Recently visited');
      await trigger.click();
      await page.getByRole('dialog', { name: 'Recently updated', exact: true }).waitFor();
      const dialog = page.getByRole('dialog');
      const query = dialog.getByRole('searchbox', { name: 'Search query' });
      const filename = dialog.getByRole('textbox', { name: 'Include filenames (regex)' });
      const exclude = dialog.getByRole('textbox', { name: 'Exclude filenames (regex)' });
      const paths = dialog.locator('.finder-result-path');
      const copy = dialog.getByRole('button', { name: 'Copy path', exact: true });
      const copied = async relative => {
        await page.waitForFunction(() => document.querySelector('#finder-copy-path')?.disabled === false);
        await copy.click();
        await page.waitForFunction(async expected => await navigator.clipboard.readText() === expected, path.join(directory, relative));
        assert.equal(await dialog.locator('.copy-path-status').isVisible(), true);
      };
      const waitForPaths = expected => page.waitForFunction(expected =>
        JSON.stringify([...document.querySelectorAll('#finder-results .finder-result-path')].map(node => node.textContent)) === JSON.stringify(expected), expected);
      assert.equal(await filename.inputValue(), '\\.(html|md)$');
      assert.equal(await dialog.getByRole('combobox', { name: 'Search scope' }).inputValue(), 'root');
      await query.fill('updates');
      await waitForPaths(['updates/nested/new #.HTML', 'updates/old.md']);
      await page.frameLocator('#finder-preview iframe').getByRole('heading', { name: 'Recently updated HTML', exact: true }).waitFor();
      await copied('updates/nested/new #.HTML');
      const bounds = await dialog.boundingBox();
      assert.ok(bounds.width >= width * .95 && bounds.width <= width);
      assert.ok(bounds.height >= 900 * .93 && bounds.y >= 0 && bounds.y + bounds.height <= 900);
      const resultsBounds = await dialog.locator('#finder-results').boundingBox();
      const previewBounds = await dialog.locator('.finder-preview-pane').boundingBox();
      if (width >= 768) assert.ok(previewBounds.width > resultsBounds.width * 1.8);
      else assert.ok(previewBounds.height > resultsBounds.height);
      assert.equal(await page.evaluate(() => window.previewExecuted), undefined);
      assert.match(await dialog.locator('time').first().textContent(), /^Modified · /);
      assert.ok(await dialog.locator('time').first().getAttribute('datetime'));
      await filename.fill('');
      await waitForPaths(['updates/latest.txt', 'updates/nested/new #.HTML', 'updates/old.md']);
      await copied('updates/latest.txt');
      await exclude.fill('\\.txt$');
      await waitForPaths(['updates/nested/new #.HTML', 'updates/old.md']);
      await dialog.getByRole('tab', { name: 'Contents', exact: true }).click();
      assert.equal(await filename.inputValue(), '');
      assert.equal(await exclude.inputValue(), '');
      await filename.fill('\\.md$');
      await dialog.getByRole('tab', { name: 'Updated', exact: true }).click();
      assert.equal(await filename.inputValue(), '');
      assert.equal(await exclude.inputValue(), '\\.txt$');
      await waitForPaths(['updates/nested/new #.HTML', 'updates/old.md']);
      await exclude.fill('[');
      await page.waitForFunction(() => document.querySelector('#finder-status').textContent.startsWith('Exclude filenames:'));
      assert.equal(await dialog.getByRole('progressbar', { name: 'Search in progress' }).isVisible(), false);
      assert.equal(await dialog.locator('#finder-elapsed').isVisible(), false);
      assert.equal(await paths.count(), 0);
      assert.equal(await dialog.getByRole('link', { name: 'Open file', exact: true }).isVisible(), false);
      assert.equal(await copy.isVisible(), false);
      await exclude.fill('');
      await filename.fill('\\.(html|md)$');
      await dialog.getByRole('combobox', { name: 'Search scope' }).selectOption('current');
      await query.fill('');
      await waitForPaths(['updates/nested/new #.HTML', 'updates/old.md']);
      assert.equal(await dialog.evaluate(node => node.scrollWidth <= node.clientWidth), true);
      if (width < 768) {
        const resultsBounds = await dialog.locator('#finder-results').boundingBox();
        const previewBounds = await dialog.locator('.finder-preview-pane').boundingBox();
        assert.ok(previewBounds.y > resultsBounds.y);
      }
      await query.press('ArrowDown');
      await page.frameLocator('#finder-preview iframe').getByRole('heading', { name: 'Recently updated example', exact: true }).waitFor();
      await copied('updates/old.md');
      await query.press('Escape');
      assert.equal(await trigger.evaluate(node => node === document.activeElement), true);
      await trigger.click();
      await waitForPaths(['updates/nested/new #.HTML', 'updates/old.md']);
      await page.frameLocator('#finder-preview iframe').getByRole('heading', { name: 'Recently updated HTML', exact: true }).waitFor();
      await Promise.all([page.waitForURL(baseURL + 'updates/nested/new%20%23.HTML'), query.press('Enter')]);
      await page.frameLocator('#document-frame').getByRole('heading', { name: 'Recently updated HTML' }).waitFor();
      await page.locator('#directory-toggle').click();
      await page.getByRole('button', { name: 'Recently updated', exact: true }).click();
      await page.getByRole('combobox', { name: 'Search scope' }).selectOption('current');
      await waitForPaths(['updates/nested/new #.HTML']);
    } finally { await page.close(); }
  });
}

test("directory sorting and navigation work without JavaScript on a narrow screen", async () => {
  const page = await browser.newPage({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
  const labels = () => page.locator("tbody td:first-child a").allTextContents();
  try {
    await page.goto(baseURL + "ordering/");
    assert.deepEqual(await page.locator("th").allTextContents(), ["Title", "Created", "Modified"]);
    assert.deepEqual(await labels(), ["../", "zebra.md", "report2.md", "report10.md", "Alpha.md", "subdir/"]);
    assert.equal(await page.getByRole("navigation", { name: "Sort files" }).count(), 0);
    await page.getByRole("link", { name: "Title", exact: true }).click();
    assert.deepEqual(await labels(), ["../", "Alpha.md", "report10.md", "report2.md", "subdir/", "zebra.md"]);
    await page.getByRole("link", { name: "Title", exact: true }).click();
    assert.deepEqual(await labels(), ["../", "zebra.md", "subdir/", "report2.md", "report10.md", "Alpha.md"]);
    assert.equal(await page.locator('th[aria-sort="descending"]').innerText(), "Title");
    await page.getByRole("link", { name: "subdir/", exact: true }).click();
    assert.equal(new URL(page.url()).searchParams.get("sort"), "title");
    assert.equal(new URL(page.url()).searchParams.get("order"), "desc");
    await page.getByRole("link", { name: "../", exact: true }).click();
    assert.equal(new URL(page.url()).searchParams.get("sort"), "title");
    assert.equal(new URL(page.url()).searchParams.get("order"), "desc");
    await page.getByRole("link", { name: "Modified", exact: true }).click();
    assert.deepEqual(await labels(), ["../", "zebra.md", "report2.md", "report10.md", "Alpha.md", "subdir/"]);
    // Header links remain keyboard operable with JavaScript disabled.
    await page.getByRole("link", { name: "Modified", exact: true }).focus();
    await Promise.all([
      page.waitForURL((url) => url.searchParams.get("order") === "asc"),
      page.keyboard.press("Enter"),
    ]);
    assert.deepEqual(await labels(), ["../", "subdir/", "Alpha.md", "report10.md", "report2.md", "zebra.md"]);
    const dates = await page.locator("tbody tr").evaluateAll((rows) => rows.slice(1).map((row) => ({
      name: row.querySelector("a").textContent,
      created: row.children[1].querySelector("time")?.dateTime || null,
    })));
    for (const order of ["desc", "asc"]) {
      await page.getByRole("link", { name: "Created", exact: true }).click();
      const expected = dates.toSorted((a, b) => {
        if (a.created && b.created && a.created !== b.created) {
          return (a.created < b.created ? -1 : 1) * (order === "asc" ? 1 : -1);
        }
        if (!a.created !== !b.created) return a.created ? -1 : 1;
        return a.name.toLowerCase() < b.name.toLowerCase() ? -1 : 1;
      });
      assert.deepEqual(await labels(), ["../", ...expected.map((entry) => entry.name)]);
      assert.equal(await page.locator("th[aria-sort]").innerText(), "Created");
      assert.equal(await page.locator("th[aria-sort]").getAttribute("aria-sort"), order === "asc" ? "ascending" : "descending");
    }
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  } finally { await page.close(); }
});

test("clicking a listed Markdown file renders GFM, Mermaid, math and SVGs", async () => {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const external = await localOnly(page);
  try {
    await page.goto(baseURL + "nested/");
    await page.getByRole("link", { name: filename, exact: true }).click();
    await ready(page);
    assert.equal(await page.locator("h1").innerText(), "Markdown preview");
    const bounds = await page.locator("#content").boundingBox();
    assert.ok(Math.abs(bounds.x - (page.viewportSize().width - bounds.width) / 2) < 1, "Markdown layout remains centered");
    assert.equal(await page.locator("table tbody td").first().innerText(), "Markdown");
    assert.equal(await page.locator('input[type="checkbox"]:checked').count(), 1);
    assert.equal(await page.locator("del").innerText(), "Deleted");
    assert.equal(await page.locator(".diagram svg").count(), 2);
    assert.equal(await page.locator(".katex").count(), 2);
    assert.equal(await page.locator("#storage-layout").count(), 1);
    assert.equal(await page.locator("#storage-layout-1").count(), 1);
    assert.match(await page.locator("code.language-python").innerText(), /\$ordinary_code\$/);
    assert.equal(await page.locator("code").filter({ hasText: "$literal_math$" }).count(), 1);
    await page.waitForFunction(() => [...document.querySelectorAll("#content img")].every((image) => image.complete && image.naturalWidth > 0));
    assert.equal(await page.locator("#content img").count(), 3);
    assert.equal(await page.evaluate(() => globalThis.previewXss), undefined);
    assert.equal(await page.locator('#content script, #content [onload], #content a[href^="javascript:"]').count(), 0);
    assert.deepEqual(external, []);
    assert.deepEqual(errors, []);
    if (process.env.SERVE_HTML_SCREENSHOT) {
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: process.env.SERVE_HTML_SCREENSHOT, fullPage: true });
    }
    await page.getByRole("link", { name: "Next document", exact: true }).click();
    await ready(page);
    assert.equal(await page.locator("h1").innerText(), "Next heading");
    assert.equal(new URL(page.url()).hash, "#next-heading");
  } finally {
    await page.close();
  }
});

test("direct encoded URLs and Raw links work without a preview suffix", async () => {
  const page = await browser.newPage();
  try {
    const url = baseURL + "nested/" + encodeURIComponent(filename);
    await page.goto(url + "#storage-layout");
    await ready(page);
    assert.equal(await page.locator("#filename").innerText(), filename);
    await page.getByRole("link", { name: "Raw", exact: true }).click();
    assert.equal(new URL(page.url()).searchParams.get("raw"), "1");
    assert.match(await page.locator("body").innerText(), /^# Markdown preview/);
    assert.equal(await page.locator(".markdown-body").count(), 0);
  } finally {
    await page.close();
  }
});

test("invalid math and Mermaid blocks leave the rest of the document rendered", async () => {
  const page = await browser.newPage();
  try {
    await page.goto(baseURL + "broken.md");
    await page.locator('#content[aria-busy="false"]').waitFor();
    assert.equal(await page.locator(".render-error").count(), 2);
    assert.equal(await page.locator(".diagram svg").count(), 1);
    assert.match(await page.locator("#content").innerText(), /Final paragraph\./);
  } finally {
    await page.close();
  }
});

test("plain Markdown avoids downloading Mermaid and math bundles", async () => {
  const page = await browser.newPage();
  const urls = [];
  page.on("request", (request) => urls.push(request.url()));
  try {
    await page.goto(baseURL + "plain.md");
    await ready(page);
    assert.equal(await page.locator("h1").innerText(), "Plain document");
    await page.getByRole("button", { name: "Dark mode", exact: true }).click();
    assert.equal(urls.some((url) => /\/(mermaid|math)\.js|katex\.css/.test(url)), false);
  } finally {
    await page.close();
  }
});

test("light defaults override dark OS preference and the toggle persists across pages", async () => {
  const page = await browser.newPage({ colorScheme: "dark", viewport: { width: 390, height: 844 } });
  try {
    await page.goto(baseURL + "nested/" + encodeURIComponent(filename));
    await ready(page);
    assert.equal(await page.evaluate(() => getComputedStyle(document.body).backgroundColor), "rgb(255, 255, 255)");
    assert.equal(await page.locator(".markdown-body").evaluate((element) => getComputedStyle(element).backgroundColor), "rgb(255, 255, 255)");
    assert.equal(await page.locator(".diagram svg").count(), 2);
    assert.equal(await page.locator(".katex").count(), 2);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    const heading = await page.locator("#storage-layout").elementHandle();
    const math = await page.locator(".katex").first().elementHandle();
    const fill = () => page.locator(".diagram .node rect").first().evaluate((element) => getComputedStyle(element).fill);
    const lightFill = await fill();
    const button = page.getByRole("button", { name: "Dark mode", exact: true });
    await button.focus();
    await button.press("Space");
    await diagramsReady(page);
    assert.notEqual(await fill(), lightFill);
    assert.equal(await button.getAttribute("aria-pressed"), "true");
    assert.equal(await page.evaluate(() => getComputedStyle(document.body).backgroundColor), "rgb(13, 17, 23)");
    assert.equal(await page.locator(".markdown-body").evaluate((element) => getComputedStyle(element).backgroundColor), "rgb(13, 17, 23)");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.equal(await heading.evaluate((element) => element.isConnected), true);
    assert.equal(await math.evaluate((element) => element.isConnected), true);
    assert.equal(await button.evaluate((element) => document.activeElement === element), true);
    assert.equal(await button.evaluate((element) => getComputedStyle(element).outlineWidth), "2px");
    await page.getByRole("link", { name: "Next document", exact: true }).click();
    await ready(page);
    assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
    await page.reload();
    await ready(page);
    assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
    await button.click();
    await page.reload();
    await ready(page);
    assert.equal(await page.locator("html").getAttribute("data-theme"), "light");
  } finally {
    await page.close();
  }
});

test("initial theme and toggle do not wait for the Markdown fetch", { timeout: 30000 }, async () => {
  for (const saved of [null, "dark"]) {
    const page = await browser.newPage({ colorScheme: "dark" });
    let release, requested;
    const gate = new Promise((resolve) => { release = resolve; });
    const started = new Promise((resolve) => { requested = resolve; });
    try {
      if (saved) await page.addInitScript((value) => localStorage.setItem("serve-html.theme.v1", value), saved);
      await page.route("**/*", async (route) => {
        if (new URL(route.request().url()).searchParams.get("raw") === "1") {
          requested();
          await gate;
        }
        await route.continue();
      });
      await page.goto(baseURL + "plain.md", { waitUntil: "commit" });
      await started;
      const button = page.getByRole("button", { name: "Dark mode", exact: true });
      await button.waitFor();
      assert.equal(await page.evaluate(() => getComputedStyle(document.body).backgroundColor), saved ? "rgb(13, 17, 23)" : "rgb(255, 255, 255)");
      await button.click();
      assert.equal(await button.getAttribute("aria-pressed"), saved ? "false" : "true");
      release();
      await ready(page);
    } finally { release(); await page.close(); }
  }
});

test("invalid and denied storage still allow a usable theme toggle", async () => {
  for (const mode of ["invalid", "read-denied", "write-denied"]) {
    const page = await browser.newPage({ colorScheme: "dark" });
    try {
      await page.addInitScript((mode) => {
        if (mode === "invalid") localStorage.setItem("serve-html.theme.v1", "system");
        if (mode === "read-denied") Object.defineProperty(window, "localStorage", { get() { throw new DOMException("Denied", "SecurityError"); } });
        if (mode === "write-denied") Storage.prototype.setItem = () => { throw new DOMException("Full", "QuotaExceededError"); };
      }, mode);
      await page.goto(baseURL + "plain.md");
      await ready(page);
      assert.equal(await page.locator("html").getAttribute("data-theme"), "light");
      const button = page.getByRole("button", { name: "Dark mode", exact: true });
      await button.click();
      assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
      await button.click();
      assert.equal(await page.locator("html").getAttribute("data-theme"), "light");
    } finally { await page.close(); }
  }
});

test("rapid toggles during delayed Mermaid loading finish in the latest theme", { timeout: 30000 }, async () => {
  const page = await browser.newPage();
  let release, requested;
  const gate = new Promise((resolve) => { release = resolve; });
  const started = new Promise((resolve) => { requested = resolve; });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    await page.route("**/vendor/mermaid.js", async (route) => {
      requested();
      await gate;
      await route.continue();
    });
    await page.goto(baseURL + "nested/" + encodeURIComponent(filename), { waitUntil: "domcontentloaded" });
    await started;
    await page.getByRole("button", { name: "Dark mode", exact: true }).evaluate((button) => {
      button.click(); button.click(); button.click();
    });
    release();
    await ready(page);
    assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
    const fill = () => page.locator(".diagram .node rect").first().evaluate((element) => getComputedStyle(element).fill);
    const darkFill = await fill();
    const button = page.getByRole("button", { name: "Dark mode", exact: true });
    await button.click();
    await diagramsReady(page);
    assert.notEqual(await fill(), darkFill);
    await button.evaluate((button) => { for (let i = 0; i < 5; i += 1) button.click(); });
    await diagramsReady(page);
    assert.equal(await fill(), darkFill);
    assert.deepEqual(errors, []);
  } finally { release(); await page.close(); }
});

test("diagram errors do not prevent theme changes", async () => {
  const page = await browser.newPage();
  try {
    await page.goto(baseURL + "broken.md");
    await page.locator('#content[aria-busy="false"]').waitFor();
    await page.getByRole("button", { name: "Dark mode", exact: true }).click();
    await diagramsReady(page);
    assert.equal(await page.locator(".render-error").count(), 2);
    assert.equal(await page.locator(".diagram svg").count(), 1);
    assert.match(await page.locator("#content").innerText(), /Final paragraph\./);
  } finally { await page.close(); }
});

test("a failed theme script leaves a light preview and hides the inactive toggle", async () => {
  const page = await browser.newPage({ colorScheme: "dark" });
  try {
    await page.route("**/__serve_html__/theme.js", (route) => route.abort());
    await page.goto(baseURL + "plain.md");
    await ready(page);
    assert.equal(await page.evaluate(() => getComputedStyle(document.body).backgroundColor), "rgb(255, 255, 255)");
    assert.equal(await page.locator("#theme-toggle").isVisible(), false);
  } finally { await page.close(); }
});

test('Markdown absolute project links and absolute image paths resolve automatically', async () => {
  const page = await browser.newPage();
  page.setDefaultTimeout(5000);
  try {
    await page.goto(baseURL + 'absolute.md');
    await ready(page);
    assert.equal(await page.getByAltText('Absolute figure').evaluate(img => img.complete && img.naturalWidth > 0), true);
    await page.getByRole('link', { name: 'Project document', exact: true }).click();
    await ready(page);
    await page.waitForURL(baseURL + 'plain.md');
    assert.equal(await page.getByRole('heading', { name: 'Plain document', exact: true }).count(), 1);
  } finally { await page.close(); }
});

test('absolute links from Markdown and framed HTML retain queries, fragments, Back and Forward', { timeout: 30000 }, async () => {
  for (const source of ['absolute.md', 'absolute.html']) {
    const page = await browser.newPage();
    page.setDefaultTimeout(5000);
    const child = page.frameLocator('#document-frame');
    try {
      await page.goto(baseURL + source);
      if (source.endsWith('.md')) await ready(page);
      const document = source.endsWith('.md') ? page : child;
      await document.getByRole('link', { name: 'Extra document', exact: true }).click();
      await child.getByRole('heading', { name: 'Extra HTML', exact: true }).waitFor();
      await page.waitForURL(url => url.pathname.startsWith('/__docserve_fs__/') && url.hash === '#target');
      assert.equal(new URL(page.url()).search, '?keep=%20&other=%2B');
      assert.equal(await child.locator('body').evaluate(node => getComputedStyle(node).backgroundColor), 'rgb(17, 24, 39)');
      assert.equal(await child.locator('body').evaluate(() => window.extraScript), true);
      assert.equal(await child.locator('img').evaluate(img => img.complete && img.naturalWidth > 0), true);
      const mountedHTML = page.url();
      await page.goBack();
      await page.waitForURL(baseURL + source);
      await page.goForward();
      await page.waitForURL(mountedHTML);
      await child.getByRole('link', { name: 'Extra Markdown', exact: true }).click();
      await child.locator('#content[aria-busy="false"]').waitFor();
      await page.waitForURL(url => url.pathname.endsWith('/' + encodeURIComponent('한글 #?.md')));
      assert.equal(await child.getByAltText('Extra figure').evaluate(img => img.complete && img.naturalWidth > 0), true);
      await child.getByRole('link', { name: 'Next page', exact: true }).click();
      await child.getByRole('heading', { name: 'Extra next page', exact: true }).waitFor();
      await page.waitForURL(url => url.pathname.endsWith('/docs/next.md'));
      await page.getByRole('button', { name: 'Directory listing', exact: true }).first().click();
      const pane = page.locator('#document-directory');
      await pane.getByRole('link', { name: 'page.html', exact: true }).waitFor();
      assert.equal(await pane.locator('#directory-status').innerText(), '');
      await pane.getByRole('button', { name: 'Find files', exact: true }).click();
      await page.getByRole('searchbox', { name: 'Search query', exact: true }).fill('other');
      await page.locator('#finder-results [role="option"]').filter({ hasText: 'other.md' }).waitFor();
      await page.locator('#finder-close').click();
      await pane.getByRole('button', { name: 'Parent directory', exact: true }).click();
      await pane.getByRole('link', { name: 'other.md', exact: true }).waitFor();
      assert.equal(await pane.getByRole('button', { name: 'Parent directory', exact: true }).isDisabled(), true);
    } finally { await page.close(); }
  }
});

test('standalone HTML follows absolute links into another repository without configuration', async () => {
  const page = await browser.newPage();
  page.setDefaultTimeout(5000);
  try {
    await page.goto(baseURL + 'absolute.html?__docserve_standalone=1');
    assert.equal(await page.locator('#document-frame').count(), 0);
    await page.getByRole('link', { name: 'Extra document', exact: true }).click();
    await page.frameLocator('#document-frame').getByRole('heading', { name: 'Extra HTML', exact: true }).waitFor();
    await page.waitForURL(url => url.pathname.startsWith('/__docserve_fs__/') && url.hash === '#target');
  } finally { await page.close(); }
});

test("HTML documents keep their original content inside the navigation viewer", async () => {
  const page = await browser.newPage();
  try {
    await page.goto(baseURL + "existing.html");
    assert.equal(await page.title(), "Existing HTML");
    assert.equal(await page.frameLocator('#document-frame').locator("h1").innerText(), "Original page");
  } finally {
    await page.close();
  }
});

test('HTML navigation supports A/B, A/C and C/C-prime without reloading the document', { timeout: 30000 }, async () => {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(5000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const child = page.frameLocator('#document-frame');
  const view = async expected => assert.equal(await page.locator('body').getAttribute('data-document-view'), expected);
  try {
    const url = baseURL + 'navigation/' + encodeURIComponent(htmlFilename);
    await page.goto(url);
    await child.getByRole('heading', { name: 'Interactive document' }).waitFor();
    await view('banner');
    assert.equal(await child.locator('body').evaluate(node => getComputedStyle(node).backgroundColor), 'rgb(17, 24, 39)');
    await child.locator('#counter').click();
    const width = (await page.locator('#document-frame').boundingBox()).width;
    await page.locator('#directory-toggle').click();
    await page.locator('#directory-entries a[aria-current="page"]').waitFor();
    await view('directory');
    assert.equal(width - (await page.locator('#document-frame').boundingBox()).width, 272);
    const paneBounds = await page.locator('#document-directory').boundingBox();
    assert.ok(Math.abs(paneBounds.y + paneBounds.height - page.viewportSize().height) < 1, 'The directory pane fills the available height');
    await page.locator('#directory-filter').fill(htmlFilename);
    assert.equal(await page.locator('#directory-entries a').count(), 1);
    await page.locator('#directory-toggle').click();
    await view('banner');
    await page.locator('#compact-view').click();
    await view('compact');
    await page.locator('#expand-banner').click();
    await view('banner');
    await page.locator('#compact-view').click();
    await page.locator('#compact-directory-toggle').click();
    await view('compact-directory');
    assert.equal(await page.locator('#document-banner').isVisible(), false);
    assert.equal((await page.locator('#document-frame').boundingBox()).width, width);
    await page.locator('#compact-directory-toggle').click();
    await view('compact');
    await page.locator('#compact-directory-toggle').click();
    await page.locator('#close-directory').click();
    await view('compact');
    assert.equal(await page.locator('#compact-directory-toggle').evaluate(node => node === document.activeElement), true);
    await page.locator('#compact-directory-toggle').click();
    await page.locator('#directory-filter').press('Escape');
    await view('compact');
    assert.equal(await child.locator('#counter').innerText(), 'Count: 1');
    assert.equal(page.url(), url);
    const popupPromise = page.waitForEvent('popup');
    await page.locator('#compact-standalone').click();
    const popup = await popupPromise;
    await popup.waitForLoadState();
    assert.equal(await popup.locator('#document-banner').count(), 0);
    assert.equal(await popup.getByRole('heading').innerText(), 'Interactive document');
    assert.equal(new URL(popup.url()).searchParams.get('__docserve_standalone'), '1');
    await popup.close();
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('HTML relative navigation updates URLs, Back, Forward and recent visits without nested viewers', { timeout: 30000 }, async () => {
  const page = await browser.newPage();
  page.setDefaultTimeout(5000);
  const child = page.frameLocator('#document-frame');
  try {
    const first = baseURL + 'navigation/' + encodeURIComponent(htmlFilename);
    await page.goto(first);
    await child.getByRole('heading', { name: 'Interactive document' }).waitFor();
    await child.getByRole('link', { name: 'Next HTML', exact: true }).click();
    await child.getByRole('heading', { name: 'Second document' }).waitFor();
    await page.waitForURL(baseURL + 'navigation/second.htm?keep=%20&other=%2B#target');
    assert.equal(await child.locator('#document-frame').count(), 0);
    await page.goBack();
    await child.getByRole('heading', { name: 'Interactive document' }).waitFor();
    await page.waitForURL(first);
    await page.goForward();
    await child.getByRole('heading', { name: 'Second document' }).waitFor();
    await page.waitForURL(baseURL + 'navigation/second.htm?keep=%20&other=%2B#target');
    await page.reload();
    await child.getByRole('heading', { name: 'Second document' }).waitFor();
    await page.waitForFunction(async () => {
      const data = await (await fetch('/__serve_html__/api/recent')).json();
      return data.results.some(entry => entry.path === 'navigation/second.htm');
    });
    const history = await (await page.request.get(baseURL + '__serve_html__/api/recent')).json();
    assert.equal(history.results.some(entry => entry.path === 'navigation/helper.html'), false);
    await child.getByRole('link', { name: 'First HTML', exact: true }).click();
    await child.getByRole('link', { name: 'Read Markdown', exact: true }).click();
    await child.locator('#content[aria-busy="false"]').waitFor();
    await page.waitForURL(baseURL + 'plain.md');
    assert.equal(await child.locator('#document-banner').count(), 0);
    assert.equal(await child.getByRole('button', { name: 'Dark mode', exact: true }).isVisible(), true);
  } finally { await page.close(); }
});

test('HTML links avoid nested viewers when Fetch Metadata headers are absent on plain HTTP', { timeout: 30000 }, async () => {
  const page = await browser.newPage();
  page.setDefaultTimeout(5000);
  try {
    await page.route(/\/navigation\/[^/]+\.html?(?:\?|$)/i, async route => {
      const headers = await route.request().allHeaders();
      for (const name of Object.keys(headers)) if (name.startsWith('sec-fetch-')) delete headers[name];
      await route.fulfill({ response: await route.fetch({ headers }) });
    });
    await page.goto(baseURL + 'navigation/' + encodeURIComponent(htmlFilename));
    const child = page.frameLocator('#document-frame');
    await child.getByRole('heading', { name: 'Interactive document' }).waitFor();
    assert.equal(await child.frameLocator('iframe').locator('p').textContent(), 'Supporting content');
    assert.equal(await child.frameLocator('iframe').locator('#document-banner').count(), 0);
    const recent = await (await page.request.get(baseURL + '__serve_html__/api/recent')).json();
    assert.equal(recent.results.some(entry => entry.path === 'navigation/helper.html'), false);
    await child.getByRole('link', { name: 'Next HTML', exact: true }).click();
    await child.getByRole('heading', { name: 'Second document' }).waitFor();
    await page.waitForURL(baseURL + 'navigation/second.htm?keep=%20&other=%2B#target');
    assert.equal(await child.locator('#document-frame').count(), 0);
    await child.getByRole('link', { name: 'First HTML', exact: true }).click();
    await child.getByRole('heading', { name: 'Interactive document' }).waitFor();
    assert.equal(await child.locator('#document-frame').count(), 0);
    assert.equal(await child.frameLocator('iframe').locator('p').textContent(), 'Supporting content');
  } finally { await page.unrouteAll({ behavior: 'wait' }); await page.close(); }
});

test('Markdown shares directory and compact states and keeps rendering, theme and finder controls', { timeout: 30000 }, async () => {
  const page = await browser.newPage();
  page.setDefaultTimeout(5000);
  try {
    await page.goto(baseURL + 'nested/' + encodeURIComponent(filename));
    await ready(page);
    const heading = await page.locator('#content h1').elementHandle();
    await page.locator('#directory-toggle').click();
    await page.locator('#directory-entries a[aria-current="page"]').waitFor();
    const initialURL = page.url();
    await page.locator('#directory-entries').getByRole('link', { name: 'figures/', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('#directory-path').textContent === '/nested/figures');
    assert.equal(page.url(), initialURL);
    await page.locator('#directory-up').click();
    await page.waitForFunction(() => document.querySelector('#directory-path').textContent === '/nested');
    await page.getByRole('button', { name: 'Find contents', exact: true }).click();
    await page.getByRole('combobox', { name: 'Search scope' }).selectOption('current');
    await page.getByRole('searchbox', { name: 'Search query' }).fill('Needle.literal');
    await page.waitForFunction(() => document.querySelector('#finder-status').textContent === '0 results.');
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#document-directory').isVisible(), true);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#document-directory').isVisible(), false);
    await page.locator('#compact-view').click();
    await page.locator('#compact-directory-toggle').click();
    await page.locator('#close-directory').click();
    assert.equal(await page.locator('body').getAttribute('data-document-view'), 'compact');
    await page.locator('#expand-banner').click();
    await page.getByRole('button', { name: 'Dark mode', exact: true }).click();
    await diagramsReady(page);
    assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
    assert.equal(await heading.evaluate(node => node.isConnected), true);
    assert.equal(await page.locator('.diagram svg').count(), 2);
    assert.equal(await page.locator('.katex').count(), 2);
    assert.equal(page.url(), initialURL);
  } finally { await page.close(); }
});

test('directory drawers and compact popups fit mobile screens and return to their own layout', { timeout: 30000 }, async () => {
  for (const width of [390, 320]) {
    const page = await browser.newPage({ viewport: { width, height: 844 } });
    page.setDefaultTimeout(5000);
    try {
      await page.goto(baseURL + 'navigation/' + encodeURIComponent(htmlFilename));
      await page.frameLocator('#document-frame').getByRole('heading', { name: 'Interactive document' }).waitFor();
      await page.locator('#directory-toggle').click();
      await page.locator('#directory-entries a[aria-current="page"]').waitFor();
      assert.equal(await page.locator('#document-reader').evaluate(node => node.inert), true);
      assert.equal(await page.locator('#directory-backdrop').isVisible(), true);
      await page.locator('#close-directory').focus();
      await page.keyboard.press('Shift+Tab');
      assert.equal(await page.locator('#document-directory').evaluate(node => node.contains(document.activeElement)), true);
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('body').getAttribute('data-document-view'), 'banner');
      await page.locator('#compact-view').click();
      await page.locator('#compact-directory-toggle').click();
      await page.locator('#directory-entries').getByRole('link', { name: 'second.htm', exact: true }).click();
      await page.frameLocator('#document-frame').getByRole('heading', { name: 'Second document' }).waitFor();
      assert.equal(await page.locator('body').getAttribute('data-document-view'), 'compact');
      assert.equal(await page.locator('#document-reader').evaluate(node => node.inert), false);
      await page.locator('#compact-directory-toggle').click();
      await page.locator('#close-directory').click();
      assert.equal(await page.locator('body').getAttribute('data-document-view'), 'compact');
      await page.locator('#expand-banner').click();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    } finally { await page.close(); }
  }
});

test('HTML remains readable without JavaScript and directory API failures can be dismissed', { timeout: 30000 }, async () => {
  const noJS = await browser.newPage({ javaScriptEnabled: false });
  try {
    await noJS.goto(baseURL + 'navigation/' + encodeURIComponent(htmlFilename));
    assert.equal(await noJS.frameLocator('#document-frame').getByRole('heading').innerText(), 'Interactive document');
    await noJS.getByRole('link', { name: 'Directory listing', exact: true }).click();
    assert.equal(new URL(noJS.url()).pathname, '/navigation/');
  } finally { await noJS.close(); }
  const page = await browser.newPage();
  page.setDefaultTimeout(5000);
  try {
    await page.route('**/__serve_html__/api/directory?*', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"error":"Directory unavailable"}' }));
    await page.goto(baseURL + 'plain.md');
    await ready(page);
    await page.locator('#directory-toggle').click();
    await page.waitForFunction(() => document.querySelector('#directory-status').textContent.includes('Directory unavailable'));
    await page.locator('#close-directory').click();
    assert.equal(await page.locator('body').getAttribute('data-document-view'), 'banner');
    assert.equal(await page.locator('#content h1').innerText(), 'Plain document');
  } finally { await page.close(); }
});
