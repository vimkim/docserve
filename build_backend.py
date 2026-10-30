"""Add a build timestamp to uv-built wheels without changing the source tree."""

import base64
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import tempfile
from zipfile import ZipFile, ZipInfo

import uv_build


def __getattr__(name):
    return getattr(uv_build, name)


def _stamp_wheel(wheel_directory, filename):
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    built_at = (datetime.fromtimestamp(int(epoch), timezone.utc) if epoch is not None
                else datetime.now(timezone.utc))
    content = (built_at.isoformat(timespec="seconds").replace("+00:00", "Z") + "\n").encode()
    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
    wheel = Path(wheel_directory) / filename
    with tempfile.TemporaryDirectory(dir=wheel.parent) as temporary:
        stamped = Path(temporary) / filename
        with ZipFile(wheel) as source, ZipFile(stamped, "w") as target:
            record = next(name for name in source.namelist() if name.endswith(".dist-info/RECORD"))
            timestamp = record.removesuffix("RECORD") + "build-time.txt"
            for entry in source.infolist():
                if entry.filename != record:
                    target.writestr(entry, source.read(entry))
            target.writestr(ZipInfo(timestamp, source.getinfo(record).date_time), content)
            rows = source.read(record) + f"{timestamp},sha256={digest},{len(content)}\n".encode()
            target.writestr(source.getinfo(record), rows)
        stamped.replace(wheel)
    return filename


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    return _stamp_wheel(wheel_directory, uv_build.build_wheel(
        wheel_directory, config_settings, metadata_directory))


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    return _stamp_wheel(wheel_directory, uv_build.build_editable(
        wheel_directory, config_settings, metadata_directory))
