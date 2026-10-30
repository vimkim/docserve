"""Verify build timestamps through real wheels and installed entry points."""

import base64
import csv
from datetime import datetime, timezone
import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
UV = shutil.which("uv")


@unittest.skipUnless(UV, "uv is required for package build checks")
class BuildMetadata(unittest.TestCase):
    def run_command(self, *arguments, env=None):
        result = subprocess.run(arguments, cwd=ROOT, env=env, capture_output=True,
                                text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_built_wheel_installs_with_timestamp_and_all_browser_assets(self):
        environment = dict(os.environ)
        environment.pop("SOURCE_DATE_EPOCH", None)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "dist"
            before = datetime.now(timezone.utc).replace(microsecond=0)
            self.run_command(UV, "build", "--out-dir", str(output), env=environment)
            after = datetime.now(timezone.utc)
            wheel, = output.glob("*.whl")
            version = wheel.name.split("-")[1]
            sdist, = output.glob("*.tar.gz")
            with tarfile.open(sdist) as archive:
                self.assertTrue(any(name.endswith("/build_backend.py") for name in archive.getnames()))
            with ZipFile(wheel) as archive:
                timestamp_file, = (name for name in archive.namelist() if name.endswith("/build-time.txt"))
                timestamp = archive.read(timestamp_file).decode().strip()
                built_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                self.assertLessEqual(before, built_at)
                self.assertLessEqual(built_at, after)
                record, = (name for name in archive.namelist() if name.endswith(".dist-info/RECORD"))
                for name, digest, size in csv.reader(io.StringIO(archive.read(record).decode())):
                    if name == record:
                        continue
                    content = archive.read(name)
                    expected = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
                    self.assertEqual(digest, "sha256=" + expected, name)
                    self.assertEqual(int(size), len(content), name)
                for asset in (ROOT / "src/html_serve/assets").rglob("*"):
                    if asset.is_file():
                        name = asset.relative_to(ROOT / "src").as_posix()
                        self.assertEqual(archive.read(name), asset.read_bytes(), name)

            virtualenv = Path(temporary) / "venv"
            self.run_command(sys.executable, "-m", "venv", "--without-pip", str(virtualenv))
            self.run_command(UV, "pip", "install", "--no-deps", "--python",
                             str(virtualenv / "bin/python"), str(wheel))
            runtime = {**environment, "PATH": "", "SOURCE_DATE_EPOCH": "0"}
            for name in ("docserve", "html-serve", "md-serve"):
                with self.subTest(command=name):
                    self.assertEqual(self.run_command(str(virtualenv / "bin" / name), "--version", env=runtime),
                                     f"docserve {version} (built {timestamp})\n")
            self.assertIn("--version", self.run_command(str(virtualenv / "bin/docserve"), "--help"))

    def test_reproducible_and_editable_builds_record_source_date_epoch(self):
        environment = {**os.environ, "SOURCE_DATE_EPOCH": "1760000000"}
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "dist"
            self.run_command(UV, "build", "--wheel", "--out-dir", str(output), env=environment)
            wheel, = output.glob("*.whl")
            version = wheel.name.split("-")[1]
            first_digest = hashlib.sha256(wheel.read_bytes()).digest()
            self.run_command(UV, "build", "--wheel", "--out-dir", str(output), env=environment)
            self.assertEqual(hashlib.sha256(wheel.read_bytes()).digest(), first_digest)

            virtualenv = Path(temporary) / "venv"
            self.run_command(sys.executable, "-m", "venv", "--without-pip", str(virtualenv))
            self.run_command(UV, "pip", "install", "--no-deps", "--python",
                             str(virtualenv / "bin/python"), "--editable", str(ROOT), env=environment)
            expected = datetime.fromtimestamp(1760000000, timezone.utc).isoformat().replace("+00:00", "Z")
            self.assertEqual(self.run_command(str(virtualenv / "bin/docserve"), "--version"),
                             f"docserve {version} (built {expected})\n")


if __name__ == "__main__":
    unittest.main()
