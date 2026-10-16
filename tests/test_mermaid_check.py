"""Exercise the checker CLI, actual renderer, deadlines, and resource failures."""

from contextlib import contextmanager, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from urllib.request import urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from html_serve import check
sys.path.pop(0)


class CheckHarness:
    def run_check(self, *arguments):
        output = io.StringIO()
        with redirect_stdout(output):
            code = check.main(["mermaid", *map(str, arguments), "--json"])
        report = json.loads(output.getvalue())
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["summary"]["exit_code"], code)
        return code, report


class CheckCLI(CheckHarness, unittest.TestCase):

    def test_usage_and_input_errors_are_machine_readable(self):
        for args in ((), ("--unknown",), ("x.md", "--timeout", "nan"),
                     ("x.md", "--timeout", "0")):
            with self.subTest(args=args):
                code, report = self.run_check(*args)
                self.assertEqual(code, 2)
                self.assertEqual(report["errors"][0]["code"], "usage")
        code, report = self.run_check("/nonexistent/docserve-input.md")
        self.assertEqual(code, 2)
        self.assertEqual(report["files"][0]["errors"][0]["code"], "input")
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid.md"
            invalid.write_bytes(b"\xff\xfe")
            code, report = self.run_check(invalid, directory)
            self.assertEqual(code, 2)
            self.assertTrue(all(file["errors"][0]["code"] == "input" for file in report["files"]))

    def test_missing_optional_dependency_has_setup_instructions(self):
        with tempfile.TemporaryDirectory() as directory:
            document = Path(directory) / "a.md"
            document.write_text("# Hello", encoding="utf-8")
            with patch.dict(sys.modules, {"playwright.async_api": None}):
                code, report = self.run_check(document)
        self.assertEqual(code, 2)
        self.assertEqual(report["files"][0]["status"], "error")
        self.assertEqual(report["errors"][0]["code"], "dependency")
        self.assertIn(".[check]", report["errors"][0]["message"])

    def test_missing_packaged_asset_fails_before_browser_start(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory)
            (assets / "vendor").mkdir()
            (assets / "vendor/manifest.json").write_text(
                '{"files": {}, "packages": []}', encoding="utf-8")
            with patch.object(check, "ASSETS", assets):
                code, report = self.run_check(__file__)
        self.assertEqual(code, 2)
        self.assertIn("Missing viewer asset", report["errors"][0]["message"])

    def test_loopback_server_exposes_snapshots_and_cleans_up_on_failure(self):
        with self.assertRaisesRegex(RuntimeError, "stop"):
            with check.checker_server({"/a.md": "# Snapshot"}) as origin:
                address = urlsplit(origin)
                self.assertEqual(address.hostname, "127.0.0.1")
                with urlopen(origin + "/a.md?raw=1", timeout=2) as response:
                    self.assertEqual(response.read(), b"# Snapshot")
                raise RuntimeError("stop")
        with socket.socket() as client:
            self.assertNotEqual(client.connect_ex((address.hostname, address.port)), 0)


@unittest.skipUnless(importlib.util.find_spec("playwright"), "install .[check] for browser checks")
class MermaidBrowser(CheckHarness, unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def document(self, name, source):
        document = self.directory / name
        document.write_text(source, encoding="utf-8")
        return document

    def test_valid_flowchart_sequence_multiple_files_unicode_paths_and_no_diagrams(self):
        document = self.document("한글 review #1's ?.MD", "\n".join([
            "# Diagrams", "", "```mermaid", "flowchart LR", "A --> B", "```", "",
            "~~~Mermaid title", "sequenceDiagram", "Alice->>Bob: Hello", "~~~", "",
        ]))
        plain = self.document("plain.md", "# No diagrams\n\n`mermaid`\n\n"
                              '<div class="diagram">Author HTML</div>\n\n'
                              '<details class="render-error"><summary>Author details</summary></details>\n')
        for render in (False, True):
            with self.subTest(render=render):
                code, report = self.run_check(document, plain, *(["--render"] if render else []))
                self.assertEqual(code, 0, report)
                self.assertEqual(report["renderer"]["mermaid"], "12.2.0")
                first, second = report["files"]
                self.assertEqual([item["line"] for item in first["diagrams"]], [3, 8])
                for diagram in first["diagrams"]:
                    self.assertEqual([item["theme"] for item in diagram["checks"]],
                                     ["light", "dark"] if render else [None])
                self.assertEqual(second["diagrams"], [])
                self.assertEqual(second["status"], "passed")

    def test_mixed_valid_invalid_diagrams_do_not_hide_later_results(self):
        document = self.document("mixed.md", "\n".join([
            "```mermaid", "not a diagram", "```", "",
            "```mermaid", "flowchart LR", "A --> B", "```", "",
            "```mermaid", "flowchart LR", "A[unterminated", "```",
        ]))
        for render in (False, True):
            code, report = self.run_check(document, *(["--render"] if render else []))
            self.assertEqual(code, 1, report)
            self.assertEqual([item["status"] for item in report["files"][0]["diagrams"]],
                             ["failed", "passed", "failed"])

    def test_recognition_and_locations_match_viewer_in_markdown_containers(self):
        document = self.document("containers.md", "\r\n".join([
            "[reference]: /target", "", "````text", "```mermaid", "ignored", "```", "````", "",
            "> Quote", ">", "> ~~~mermaid", "> flowchart LR", "> A --> B", "> ~~~", "",
            "- List item", "", "  ```mermaid", "  sequenceDiagram", "  A->>B: Hi", "  ```", "",
            "- [x] Task", "", "  > ```mermaid", "  > flowchart LR", "  > A --> B", "  > ```", "",
            "<pre>", "```mermaid", "ignored", "```", "</pre>", "",
            "```mermaid", "flowchart LR", "A --> B",  # CommonMark permits an unclosed fence.
        ]) + "\n")
        for render in (False, True):
            code, report = self.run_check(document, *(["--render"] if render else []))
            self.assertEqual(code, 0, report)
            self.assertEqual([item["line"] for item in report["files"][0]["diagrams"]],
                             [11, 18, 25, 36])

    def test_missing_browser_is_an_environment_error(self):
        document = self.document("plain.md", "# Hello\n")
        with patch.dict(os.environ, {"SERVE_HTML_CHROMIUM_EXECUTABLE": "/missing/chromium"}):
            code, report = self.run_check(document)
        self.assertEqual(code, 2)
        self.assertEqual(report["errors"][0]["code"], "dependency")
        self.assertIn("headless Chromium", report["errors"][0]["message"])

    def test_duplicate_reference_definitions_preserve_preview_and_fence_location(self):
        document = self.document("references.md", "[reference]\n\n"
                                 "[reference]: /first\n[reference]: /second\n\n"
                                 "```mermaid\nflowchart LR\nA --> B\n```\n")
        title = self.document("reference-title.md", '[r]: /first\n[r]: /second "\n'
                              '```mermaid\nflowchart LR\nA --> B\n```\n"\n\n'
                              '```mermaid\nflowchart LR\nA --> B\n```\n')
        code, report = self.run_check(document, title, "--render")
        self.assertEqual(code, 0, report)
        self.assertEqual([[item["line"] for item in file["diagrams"]] for file in report["files"]],
                         [[6], [9]])

    def test_generated_svg_is_required_for_every_diagram(self):
        document = self.document("diagram.md", "```mermaid\nflowchart LR\nA --> B\n```\n")
        with self.altered_assets() as assets:
            viewer = assets / "viewer.js"
            viewer.write_text(viewer.read_text(encoding="utf-8").replace(
                "else element.innerHTML = svg;", 'else element.innerHTML = "";'), encoding="utf-8")
            code, report = self.run_check(document, "--render")
        self.assertEqual(code, 1, report)
        diagram = report["files"][0]["diagrams"][0]
        self.assertEqual(diagram["status"], "failed")
        self.assertTrue(all("visible SVG" in item["message"] for item in diagram["checks"]))

    @contextmanager
    def altered_assets(self):
        assets = self.directory / "assets"
        shutil.copytree(check.ASSETS, assets)
        with patch.object(check, "ASSETS", assets):
            yield assets

    def test_failed_dynamic_asset_request_is_not_a_diagram_failure(self):
        document = self.document("diagram.md", "```mermaid\nflowchart LR\nA --> B\n```\n")
        with self.altered_assets() as assets:
            original = assets / "mermaid-check-original.js"
            (assets / "mermaid-check.js").rename(original)
            (assets / "mermaid-check.js").write_text(
                "export {collect} from './mermaid-check-original.js';\n"
                "export async function syntax() { await import('./vendor/missing-chunk.js'); }\n",
                encoding="utf-8")
            code, report = self.run_check(document)
        self.assertEqual(code, 2)
        self.assertTrue(any(item["code"] == "asset" for item in report["files"][0]["errors"]), report)

    def test_hung_browser_evaluation_times_out_and_releases_server(self):
        document = self.document("diagram.md", "```mermaid\nflowchart LR\nA --> B\n```\n")
        plain = self.document("plain.md", "# No diagrams\n")
        origins = []
        server = check.checker_server

        @contextmanager
        def capture_server(*args):
            with server(*args) as origin:
                origins.append(urlsplit(origin))
                yield origin

        with self.altered_assets() as assets:
            (assets / "mermaid-check.js").rename(assets / "mermaid-check-original.js")
            (assets / "mermaid-check.js").write_text(
                "export {collect} from './mermaid-check-original.js';\n"
                "export async function syntax(diagrams) { if (diagrams.length) await new Promise(() => {}); return []; }\n",
                encoding="utf-8")
            with patch.object(check, "checker_server", capture_server):
                code, report = self.run_check(document, plain, "--timeout", "2")
        self.assertEqual(code, 2, report)
        self.assertEqual(report["files"][0]["errors"][0]["code"], "timeout")
        self.assertEqual(report["files"][0]["diagrams"][0]["status"], "error")
        self.assertEqual(report["files"][1]["status"], "passed")
        with socket.socket() as client:
            self.assertNotEqual(client.connect_ex((origins[0].hostname, origins[0].port)), 0)
        code, report = self.run_check(document)
        self.assertEqual(code, 0, report)


if __name__ == "__main__":
    unittest.main()
