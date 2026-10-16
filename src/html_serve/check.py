"""Check Markdown Mermaid blocks with docserve's packaged renderer."""

import argparse
import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
import os
from pathlib import Path
import sys
import threading
from urllib.parse import parse_qs, quote, unquote, urlsplit


ASSETS = Path(__file__).resolve().parent / "assets"
PREFIX = "/__serve_html__/"
SETUP = ("Run `just checker-setup` from docserve's primary main checkout to install .[check] "
         "and Chromium. For a virtual environment, install docserve[check] and run "
         "`python -m playwright install chromium --only-shell` in that environment. "
         "See docs/guide.md#mermaid-checks.")


class UsageError(Exception):
    pass


class CheckParser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def report_template(mode):
    return {"schema_version": 1, "mode": mode, "renderer": {}, "files": [], "errors": []}


def file_result(path):
    return {"path": path, "status": "unchecked", "diagrams": [], "errors": []}


def fail(result, code, message):
    result["errors"].append({"code": code, "message": message})
    if "status" in result:
        result["status"] = "error"


def validate_assets(assets):
    manifest = json.loads((assets / "vendor/manifest.json").read_text(encoding="utf-8"))
    required = ["viewer.html", "viewer.js", "markdown.js", "mermaid-check.js",
                *("vendor/" + name for name in manifest["files"])]
    for name in required:
        if not (assets / name).is_file():
            raise OSError(f"Missing viewer asset: {name}; reinstall docserve")
    return {"mermaid": next(item["version"] for item in manifest["packages"]
                            if item["name"] == "mermaid")}


@contextmanager
def checker_server(documents, assets=ASSETS):
    """Expose only document snapshots and package assets on an ephemeral loopback port."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            request = urlsplit(self.path)
            path = unquote(request.path)
            if path == "/":
                body, content_type = b"<!doctype html><title>docserve-check</title>", "text/html"
            elif path in documents:
                if parse_qs(request.query).get("raw") == ["1"]:
                    body, content_type = documents[path].encode("utf-8"), "text/plain"
                else:
                    body = (assets / "viewer.html").read_bytes()
                    content_type = "text/html"
            elif path.startswith(PREFIX):
                target = (assets / path[len(PREFIX):]).resolve()
                if not target.is_relative_to(assets.resolve()) or not target.is_file():
                    self.send_error(404)
                    return
                body = target.read_bytes()
                content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join()


async def check_document(browser, origin, url, source, result, render, timeout):
    context = await browser.new_context(service_workers="block")
    asset_errors = set()
    try:
        # A diagram check is offline. Do not fetch author images, links or CDNs.
        async def route(request_route):
            if request_route.request.url.startswith(origin + "/"):
                await request_route.continue_()
            else:
                await request_route.abort()

        await context.route("**/*", route)
        await context.add_init_script("localStorage.setItem('serve-html.theme.v1', 'light')")
        page = await context.new_page()
        page.set_default_timeout(timeout * 1000)
        page.on("response", lambda response: asset_errors.add(
            f"HTTP {response.status}: {response.url}")
            if response.status >= 400 and response.url.startswith(origin + PREFIX) else None)
        page.on("requestfailed", lambda request: asset_errors.add(
            f"{request.failure}: {request.url}")
            if request.url.startswith(origin + PREFIX) else None)
        await page.goto(origin + "/", wait_until="load")
        diagrams = await page.evaluate("""async source => {
            const checker = await import('/__serve_html__/mermaid-check.js');
            return checker.collect(source);
        }""", source)
        result["diagrams"] = [{"index": diagram["index"], "line": diagram["line"],
                               "status": "passed", "checks": []} for diagram in diagrams]
        if not render:
            checks = await page.evaluate("""async diagrams => {
                const checker = await import('/__serve_html__/mermaid-check.js');
                return checker.syntax(diagrams);
            }""", diagrams)
            if len(checks) != len(diagrams):
                fail(result, "checker", "Syntax results do not match the Markdown Mermaid blocks")
            for diagram, check in zip(result["diagrams"], checks):
                diagram["checks"].append({"theme": None, **check})
        else:
            await page.goto(origin + url + "?__docserve_standalone=1", wait_until="load")
            await page.locator('#content[aria-busy="false"]').wait_for()
            for theme in ("light", "dark"):
                if theme == "dark":
                    await page.locator("#theme-toggle").click()
                await page.evaluate("document.fonts.ready")
                state = await page.evaluate("""async () => {
                    const checker = await import('/__serve_html__/mermaid-check.js');
                    return checker.rendered();
                }""")
                if state["error"]:
                    fail(result, "viewer", state["error"])
                    break
                checks = state["diagrams"]
                if len(checks) != len(diagrams):
                    fail(result, "viewer", "Viewer diagrams do not match the Markdown Mermaid blocks")
                    break
                for diagram, check in zip(result["diagrams"], checks):
                    diagram["checks"].append({"theme": theme, "status": check["status"],
                                              "message": check["message"]})
        for diagram in result["diagrams"]:
            if any(check["status"] == "failed" for check in diagram["checks"]):
                diagram["status"] = "failed"
                if result["status"] != "error":
                    result["status"] = "failed"
        if result["status"] == "unchecked":
            result["status"] = "passed"
    finally:
        for message in sorted(asset_errors):
            fail(result, "asset", message)
        await context.close()


async def run_browser(report, documents, render, timeout, assets=ASSETS):
    try:
        from playwright.async_api import Error, TimeoutError as BrowserTimeout, async_playwright
    except ImportError:
        fail(report, "dependency", "Python Playwright is unavailable. " + SETUP)
        return
    try:
        with checker_server({unquote(url): source for url, source, _ in documents}, assets) as origin:
            async with async_playwright() as playwright:
                executable = os.environ.get("SERVE_HTML_CHROMIUM_EXECUTABLE")
                browser = await playwright.chromium.launch(
                    headless=True, timeout=timeout * 1000,
                    **({"executable_path": executable} if executable else {}))
                try:
                    for url, source, result in documents:
                        try:
                            await asyncio.wait_for(check_document(
                                browser, origin, url, source, result, render, timeout), timeout)
                        except (asyncio.TimeoutError, BrowserTimeout):
                            fail(result, "timeout", f"Check exceeded {timeout:g} seconds")
                        except Error as error:
                            fail(result, "browser", str(error))
                        if result["status"] == "error":
                            for diagram in result["diagrams"]:
                                if len(diagram["checks"]) < (2 if render else 1):
                                    diagram["status"] = "error"
                finally:
                    await browser.close()
    except Error as error:
        fail(report, "dependency", f"Could not run headless Chromium: {error}\n{SETUP}")


def emit(report, as_json):
    files = report["files"]
    diagrams = [diagram for file in files for diagram in file["diagrams"]]
    code = (2 if report["errors"] or any(file["status"] == "error" for file in files)
            else 1 if any(file["status"] == "failed" for file in files) else 0)
    report["summary"] = {"files": len(files), "diagrams": len(diagrams),
                         "failed": sum(item["status"] == "failed" for item in diagrams),
                         "exit_code": code}
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for file in files:
            for diagram in file["diagrams"]:
                print(f"{diagram['status'].upper():6} {file['path']}:{diagram['line']} "
                      f"(diagram {diagram['index']}, {report['mode']})")
                for check in diagram["checks"]:
                    if check["message"]:
                        print(f"       {check['theme'] or 'syntax'}: {check['message']}")
            if not file["diagrams"] and file["status"] == "passed" and not report["errors"]:
                print(f"PASSED {file['path']} (no Mermaid blocks)")
            for error in file["errors"]:
                print(f"ERROR  {file['path']}: {error['message']}")
        for error in report["errors"]:
            print(f"ERROR  {error['message']}")
        print(f"{report['mode'].capitalize()} check: {len(diagrams)} Mermaid block(s); exit {code}")
    return code


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    report = report_template("render" if "--render" in argv else "syntax")
    parser = CheckParser(prog="docserve-check", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    mermaid = commands.add_parser("mermaid", help="check Mermaid in Markdown files")
    mermaid.add_argument("files", nargs="+", help="UTF-8 Markdown files")
    mermaid.add_argument("--render", action="store_true", help="render in the viewer in light and dark themes")
    mermaid.add_argument("--json", action="store_true", help="emit schema version 1 JSON")
    mermaid.add_argument("--timeout", type=float, default=30, metavar="SECONDS",
                         help="deadline per file and for browser launch (default: 30)")
    try:
        args = parser.parse_args(argv)
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise UsageError("--timeout must be a positive finite number")
    except UsageError as error:
        fail(report, "usage", str(error))
        return emit(report, "--json" in argv)
    documents = []
    for index, path in enumerate(args.files):
        result = file_result(path)
        report["files"].append(result)
        try:
            document = Path(path)
            if not document.is_file():
                raise OSError(f"Not a regular Markdown file: {path}")
            source = document.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            fail(result, "input", str(error))
            continue
        url = f"/documents/{index}/{quote(Path(path).name, safe='')}"
        documents.append((url, source, result))
    try:
        report["renderer"] = validate_assets(ASSETS)
        if documents:
            asyncio.run(run_browser(report, documents, args.render, args.timeout, ASSETS))
    except (OSError, ValueError, KeyError, StopIteration) as error:
        fail(report, "environment", str(error))
    except KeyboardInterrupt:
        fail(report, "interrupted", "Check interrupted")
    for result in report["files"]:
        if result["status"] == "unchecked":
            result["status"] = "error"
    return emit(report, args.json)


if __name__ == "__main__":
    sys.exit(main())
