#!/usr/bin/env python3
"""Preview HTML and Markdown for development and print access links until Ctrl+C."""

import argparse
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import errno
from functools import partial
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import time
from typing import Optional
from urllib.parse import parse_qs, quote, unquote, urlsplit

if __package__:
    from .finder import Finder, FinderError
    from .history import VisitHistory
else:
    from finder import Finder, FinderError
    from history import VisitHistory


VPN_PREFIXES = ("tailscale", "tun", "tap", "wg", "ppp", "vpn", "zt")
CONTAINER_PREFIXES = (
    "docker", "podman", "veth", "virbr", "br-", "cni", "flannel", "cali", "lxc",
)
REPEATED_PORTS = (7777, 8888, 9999, 5555, 4444, 3333, 2222, 1111)
# Four-digit entries from https://fetch.spec.whatwg.org/#port-blocking.
BLOCKED_HTTP_PORTS = frozenset({
    1719, 1720, 1723, 2049, 3659, 4045, 4190, 5060, 5061, 6000, 6566,
    6665, 6666, 6667, 6668, 6669, 6679, 6697,
})
MARKDOWN_SUFFIXES = (".md", ".markdown")
HTML_SUFFIXES = (".html", ".htm")
STANDALONE_QUERY = "__docserve_standalone"
PREVIEW_PREFIX = "/__serve_html__/"
PREVIEW_ASSETS = Path(__file__).resolve().parent / "assets"


@dataclass
class DirectoryEntry:
    name: str
    is_directory: bool = False
    is_symlink: bool = False
    modified_ns: Optional[int] = None
    created: Optional[datetime] = None


def birth_times(directory, names, diagnostic=None):
    """Read optional GNU stat birth times in bounded, byte-framed batches."""
    batches = deque()
    batch, size = [], 0
    for name in names:
        operand_size = len(os.fsencode(name)) + 3  # ./ prefix and argv terminator
        if batch and (len(batch) >= 128 or size + operand_size > 32768):
            batches.append(batch)
            batch, size = [], 0
        batch.append(name)
        size += operand_size
    if batch:
        batches.append(batch)
    found = {}
    deadline = time.monotonic() + 2
    environment = {**os.environ, "LC_ALL": "C", "TZ": "UTC0"}

    def report(message):
        if diagnostic:
            diagnostic(f"Creation dates: {message}")

    while batches:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            report("lookup deadline reached")
            break
        batch = batches.popleft()
        operands = {b"./" + os.fsencode(name): name for name in batch}
        try:
            result = subprocess.run(
                ["stat", "--dereference", r"--printf=%n\0%w\0", "--",
                 *("./" + name for name in batch)],
                cwd=directory, env=environment, capture_output=True, timeout=remaining,
            )
        except OSError as error:
            if error.errno == errno.E2BIG and len(batch) > 1:
                middle = len(batch) // 2
                batches.appendleft(batch[middle:])
                batches.appendleft(batch[:middle])
                continue
            report(str(error))
            break
        except subprocess.TimeoutExpired:
            report("lookup timed out")
            break
        if result.returncode:
            report(f"stat exited with status {result.returncode}; preserving valid results")
        fields = result.stdout.split(b"\0")
        # A missing operand emits no record; identify every successful row by name.
        for index in range(0, len(fields) - 2, 2):
            operand, timestamp = fields[index:index + 2]
            if operand not in operands or timestamp == b"-":
                continue
            try:
                timestamp = re.sub(rb"(\.\d{6})\d+", rb"\1", timestamp)
                created = datetime.fromisoformat(timestamp.decode("ascii"))
                if created.utcoffset() != timedelta(0):
                    raise ValueError("expected a UTC creation date")
            except (ValueError, UnicodeDecodeError):
                report("stat returned an invalid creation date")
                continue
            found[operands[operand]] = created
    return found


def directory_entries(path, diagnostic=None):
    """Describe direct children, following targets while retaining link names."""
    entries = []
    with os.scandir(path) as children:
        for child in children:
            entry = DirectoryEntry(child.name)
            try:
                entry.is_symlink = child.is_symlink()
                metadata = child.stat()
                entry.is_directory = stat.S_ISDIR(metadata.st_mode)
                entry.modified_ns = metadata.st_mtime_ns
                born_ns = getattr(metadata, "st_birthtime_ns", None)
                born = born_ns / 1_000_000_000 if born_ns is not None else getattr(metadata, "st_birthtime", None)
                if born is not None:
                    try:
                        entry.created = datetime.fromtimestamp(born, timezone.utc)
                    except (ValueError, OverflowError, OSError):
                        pass
            except OSError:
                pass  # Keep disappearing entries and dangling links visible.
            entries.append(entry)
    missing = [entry.name for entry in entries if entry.created is None]
    created = birth_times(path, missing, diagnostic) if missing else {}
    for entry in entries:
        if entry.created is None:
            entry.created = created.get(entry.name)
    return entries


def render_directory(entries, request_path, sort_mode, *, sort_order=None, has_parent=False,
                     server_directory=None):
    """Return a complete listing without depending on browser JavaScript."""
    def name_key(entry):
        return entry.name.casefold(), entry.name

    defaults = {"title": "asc", "created": "desc", "modified": "desc"}
    sort_order = sort_order or defaults[sort_mode]
    entries = sorted(entries, key=name_key)
    if sort_mode == "title":
        if sort_order == "desc":
            entries.reverse()
    else:
        field = "created" if sort_mode == "created" else "modified_ns"
        known = [entry for entry in entries if getattr(entry, field) is not None]
        unknown = [entry for entry in entries if getattr(entry, field) is None]
        # Stable sorting keeps equal dates alphabetical; unavailable dates stay last.
        entries = sorted(known, key=lambda entry: getattr(entry, field),
                         reverse=sort_order == "desc") + unknown

    def sort_query(column, order):
        return "?sort=" + column + ("&order=" + order if order != defaults[column] else "")

    def column_header(column, label):
        active = column == sort_mode
        order = ("desc" if sort_order == "asc" else "asc") if active else defaults[column]
        direction = "ascending" if order == "asc" else "descending"
        current = (' aria-sort="ascending"' if sort_order == "asc" else ' aria-sort="descending"') if active else ""
        href = escape(sort_query(column, order), quote=True)
        return (f'<th scope="col"{current}><a href="{href}" aria-label="{label}" '
                f'title="Sort by {label}, {direction}">{label}</a></th>')

    def date_cell(value):
        if value is None:
            return "Unavailable"
        try:
            local = value.astimezone()
            iso = local.isoformat()
            return f'<time datetime="{iso}" title="{iso}">{local:%Y-%m-%d %H:%M:%S}</time>'
        except (ValueError, OverflowError, OSError):
            return "Unavailable"

    def copy_button(path, label):
        if path is None:
            return ''
        # Character references preserve carriage returns in unusual filenames.
        value = escape(os.path.abspath(path), quote=True).replace('\r', '&#13;')
        return (f'<button type="button" class="copy-path-button" data-copy-path="{value}" '
                f'aria-label="{escape(label, quote=True)}" hidden>Copy path</button>')

    title = "Directory listing for " + unquote(request_path, errors="replace")
    query = sort_query(sort_mode, sort_order)
    rows = []
    if has_parent:
        rows.append(f'<tr><td><a href="../{escape(query, quote=True)}">../</a></td><td>—</td><td>—</td></tr>')
    for entry in entries:
        label = entry.name + ("@" if entry.is_symlink else "/" if entry.is_directory else "")
        href = quote(entry.name, safe="", errors="surrogatepass")
        if entry.is_directory:
            href += "/" + query
        modified = None
        if entry.modified_ns is not None:
            try:
                modified = datetime.fromtimestamp(entry.modified_ns / 1_000_000_000, timezone.utc)
            except (ValueError, OverflowError, OSError):
                pass
        button = copy_button(Path(server_directory) / entry.name if server_directory is not None else None,
                             'Copy path for ' + entry.name)
        rows.append(f'<tr><td><a href="{escape(href, quote=True)}">{escape(label, quote=False)}</a>{button}</td>'
                    f'<td>{date_cell(entry.created)}</td><td>{date_cell(modified)}</td></tr>')
    headers = "".join(column_header(column, label) for column, label in
                      (("title", "Title"), ("created", "Created"), ("modified", "Modified")))
    html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light"><title>{escape(title)}</title>
<link rel="stylesheet" href="/__serve_html__/navigation.css">
<script type="module" src="/__serve_html__/navigation.js"></script>
<style>
:root {{ color-scheme: light; }}
body {{ max-width: 1120px; margin: auto; padding: 24px; color: #1f2328; background: #fff; font: 16px system-ui, sans-serif; }}
h1 {{ font-size: 1.5rem; overflow-wrap: anywhere; }}
a {{ color: #0969da; }}
a:focus-visible {{ outline: 2px solid #0969da; outline-offset: 3px; }}
p {{ color: #59636e; }}
.table-scroll {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #d1d9e0; }}
th {{ padding: 0; }}
th a {{ display: block; padding: 12px; white-space: nowrap; text-decoration: none; }}
th a:hover {{ text-decoration: underline; }}
th[aria-sort="ascending"] a::after {{ content: " ↑"; }}
th[aria-sort="descending"] a::after {{ content: " ↓"; }}
td:first-child {{ min-width: 160px; overflow-wrap: anywhere; }}
td:not(:first-child) {{ white-space: nowrap; font-variant-numeric: tabular-nums; }}
@media (max-width: 767px) {{ body {{ padding: 16px; }} }}
</style></head><body><h1>{escape(title)}</h1>
<nav aria-label="Directory"><a href="/">Go to root</a> {copy_button(server_directory, 'Copy directory path')}</nav>
<div id="navigation-tools" hidden></div>
<p>Select a column to sort; select it again to reverse. Times: server local.
Creation dates are unavailable when the filesystem does not provide them.</p>
<div class="table-scroll" role="region" aria-label="Files" tabindex="0"><table>
<thead><tr>{headers}</tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></body></html>'''
    return html.encode("utf-8", errors="replace")


class PreviewHTTPRequestHandler(SimpleHTTPRequestHandler):
    """List directories and render Markdown at its original URL."""

    def __init__(self, *args, verbose=False, finder=None, history=None, **kwargs):
        self.verbose = verbose
        self.finder = finder or Finder(kwargs.get('directory', os.getcwd()))
        self.history = history or VisitHistory(kwargs.get('directory', os.getcwd()))
        self.response_status = None
        super().__init__(*args, **kwargs)

    def send_response(self, code, message=None):
        self.response_status = code
        super().send_response(code, message)

    def log_request(self, code="-", size="-"):
        if self.verbose:
            super().log_request(code, size)

    def log_error(self, format, *args):
        self.log_message('%s — "%s"', format % args, self.requestline)

    def list_directory(self, path):
        diagnostic = (lambda message: self.log_message("%s", message)) if self.verbose else None
        try:
            entries = directory_entries(path, diagnostic)
        except OSError:
            self.send_error(404, "No permission to list directory")
            return None
        request = urlsplit(self.path)
        values = parse_qs(request.query, keep_blank_values=True).get("sort")
        sort_mode = values[0] if values in (["title"], ["created"], ["modified"]) else "modified"
        orders = parse_qs(request.query, keep_blank_values=True).get("order")
        sort_order = orders[0] if orders in (["asc"], ["desc"]) else None
        encoded = render_directory(entries, request.path, sort_mode, sort_order=sort_order,
                                   has_parent=os.path.abspath(path) != os.path.abspath(self.directory),
                                   server_directory=path)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        return io.BytesIO(encoded)

    def preview_file(self, path, content_type=None):
        """Share response headers and file opening between GET and HEAD."""
        try:
            stream = path.open("rb")
        except OSError:
            self.send_error(404, "File not found")
            return None
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type or self.guess_type(str(path)))
            self.send_header("Content-Length", str(os.fstat(stream.fileno()).st_size))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return stream
        except BaseException:
            stream.close()
            raise

    def end_headers(self):
        # Complete history I/O before exposing a response whose body is still pending.
        request = urlsplit(self.path)
        headers = getattr(self, 'headers', {})
        if getattr(self, 'html_response', False):
            self.send_header('Vary', 'Sec-Fetch-Dest, Accept')
        destination = headers.get('Sec-Fetch-Dest')
        navigation = (destination == 'document' if destination is not None
                      else 'text/html' in headers.get('Accept', ''))
        if destination is None:
            # Headerless LAN browsers load both the document and its supporting
            # frames as HTML. Viewer navigation is recorded explicitly instead.
            try:
                referrer = urlsplit(headers.get('Referer', ''))
            except ValueError:
                referrer = urlsplit('')
            if ('1' in parse_qs(request.query).get(STANDALONE_QUERY, [])
                    or '1' in parse_qs(referrer.query).get(STANDALONE_QUERY, [])):
                navigation = False
        if (self.command == 'GET' and navigation and self.response_status in (200, 304)
                and not request.path.startswith(PREVIEW_PREFIX)):
            path = Path(self.translate_path(self.path))
            relative = path.relative_to(Path(self.directory)).as_posix()
            self.history.record('' if relative == '.' else relative,
                                'directory' if path.is_dir() else 'file')
        super().end_headers()

    def send_head(self):
        self.html_response = False
        request = urlsplit(self.path)
        if request.path.startswith(PREVIEW_PREFIX + 'api/'):
            return self.finder_api(request)
        if request.path.startswith(PREVIEW_PREFIX):
            relative = Path(unquote(request.path[len(PREVIEW_PREFIX):]))
            assets = PREVIEW_ASSETS.resolve()
            path = (assets / relative).resolve()
            if (relative.is_absolute() or ".." in relative.parts
                    or not path.is_relative_to(assets) or not path.is_file()):
                self.send_error(404, "Preview asset not found")
                return None
            return self.preview_file(path)

        path = Path(self.translate_path(self.path))
        if path.is_dir():
            if not request.path.endswith(("/", "%2f", "%2F")):
                self.send_response(301)
                self.send_header("Location", request._replace(path=request.path + "/").geturl())
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            # Bypass SimpleHTTPRequestHandler's implicit index.html/index.htm lookup.
            return self.list_directory(str(path))
        if (not request.path.endswith('/') and path.suffix.lower() in HTML_SUFFIXES
                and path.is_file()):
            self.html_response = True
            destination = self.headers.get('Sec-Fetch-Dest')
            navigation = (destination == 'document' if destination is not None
                          else 'text/html' in self.headers.get('Accept', ''))
            if navigation and '1' not in parse_qs(request.query).get(STANDALONE_QUERY, []):
                try:
                    with path.open('rb'):
                        pass
                except OSError:
                    self.send_error(404, 'File not found')
                    return None
                try:
                    template = (PREVIEW_ASSETS / 'html-viewer.html').read_text(encoding='utf-8')
                except OSError:
                    self.send_error(500, 'HTML preview assets are missing; reinstall docserve')
                    return None
                source = request.geturl()
                standalone = source + ('&' if request.query else '?') + STANDALONE_QUERY + '=1'
                encoded = template.replace('{{source}}', escape(standalone, quote=True)).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(encoded)))
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                return io.BytesIO(encoded)
        if (not request.path.endswith("/") and path.suffix.lower() in MARKDOWN_SUFFIXES
                and path.is_file()):
            if parse_qs(request.query).get("raw") == ["1"]:
                return self.preview_file(path, "text/plain; charset=utf-8")
            # Check readability before returning a viewer for an unreadable document.
            try:
                with path.open("rb"):
                    pass
            except OSError:
                self.send_error(404, "File not found")
                return None
            if not (PREVIEW_ASSETS / "viewer.html").is_file():
                self.send_error(500, "Markdown preview assets are missing; reinstall docserve")
                return None
            return self.preview_file(PREVIEW_ASSETS / "viewer.html", "text/html; charset=utf-8")
        return super().send_head()

    def navigation_path(self, url):
        """Resolve an ordinary served URL, retaining direct-link symlink behavior."""
        request = urlsplit(url)
        decoded = unquote(request.path, errors='surrogatepass')
        parts = PurePosixPath(decoded).parts[1:]
        if (request.scheme or request.netloc or not decoded.startswith('/')
                or '..' in parts or '\x00' in decoded or decoded.startswith(PREVIEW_PREFIX)):
            raise FinderError('Path must be a document URL inside the serving root.')
        relative = '/'.join(parts)
        return Path(self.directory).joinpath(*parts), relative

    def navigation_directory(self, url):
        path, relative = self.navigation_path(url)
        if not path.is_dir():
            raise FinderError('Directory was not found.', 404)
        base = '/' + quote(relative, safe='/', errors='surrogatepass') + ('/' if relative else '')
        entries = []
        with os.scandir(path) as children:
            for child in children:
                try:
                    directory = child.is_dir()
                except OSError:
                    directory = False
                entries.append({'name': child.name, 'kind': 'directory' if directory else 'file',
                                'url': base + quote(child.name, safe='', errors='surrogatepass')
                                + ('/' if directory else ''), 'symlink': child.is_symlink(),
                                'server_path': os.path.abspath(child.path)})
        entries.sort(key=lambda entry: (entry['kind'] != 'directory', entry['name'].casefold(), entry['name']))
        parent = base.rstrip('/').rsplit('/', 1)[0] + '/' if relative else None
        return {'url': base, 'path': relative, 'parent': parent, 'entries': entries}

    def json_response(self, result, status=200):
        encoded = json.dumps(result).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        return io.BytesIO(encoded)

    def do_POST(self):
        """Record reader navigation inside the viewer, excluding supporting frames."""
        self.html_response = False
        if urlsplit(self.path).path != PREVIEW_PREFIX + 'api/visit':
            self.send_error(501, "Unsupported method ('POST')")
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if (not 0 < length <= 8192 or self.headers.get_content_type() != 'application/json'
                    or self.headers.get('Sec-Fetch-Site') == 'cross-site'):
                raise FinderError('Expected a same-origin JSON document visit.')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict) or not isinstance(data.get('url'), str):
                raise FinderError('Expected a document URL.')
            path, relative = self.navigation_path(data['url'])
            if not (path.is_file() or path.is_dir()):
                raise FinderError('Visited path was not found.', 404)
            self.history.record(relative, 'directory' if path.is_dir() else 'file')
            stream = self.json_response({'recorded': True})
        except (ValueError, OSError) as error:
            stream = self.json_response({'error': str(error)}, getattr(error, 'status', 400))
        self.wfile.write(stream.getvalue())

    def finder_api(self, request):
        query = parse_qs(request.query, keep_blank_values=True)
        def value(name, default=''):
            values = query.get(name, [default])
            if len(values) != 1:
                raise FinderError('Repeated query parameters are not supported.')
            return values[0]
        try:
            endpoint = request.path.removeprefix(PREVIEW_PREFIX + 'api/')
            if endpoint == 'search':
                scope = value('scope') if 'scope' in query else unquote(value('scope_url', '/'), errors='surrogatepass')
                result = self.finder.search(value('mode', 'files'), value('q'), scope,
                                            value('include') == '1', value('regex') == '1',
                                            value('filename'), value('exclude_filename'))
            elif endpoint == 'preview':
                path = value('path') if 'path' in query else unquote(value('url'), errors='surrogatepass')
                result = self.finder.preview(path, int(value('line', '1')), int(value('column', '0')))
            elif endpoint == 'recent':
                result = self.history.recent(value('q'), value('kind', 'all'))
            elif endpoint == 'directory':
                result = self.navigation_directory(value('url', '/'))
            elif endpoint == 'path':
                path, _ = self.navigation_path(value('url', '/'))
                if not (path.is_file() or path.is_dir()):
                    raise FinderError('Path was not found.', 404)
                result = {'server_path': os.path.abspath(path)}
            else:
                raise FinderError('Unknown finder endpoint.', 404)
            status = 200
        except (ValueError, OSError) as error:
            status = error.status if isinstance(error, FinderError) else 400
            result = {'error': str(error)}
        return self.json_response(result, status)


def network_addresses(interface=None):
    """Find active IPv4 addresses, preferring VPN interfaces."""
    try:
        result = subprocess.run(
            ["ip", "-j", "address", "show"],
            check=True, capture_output=True, text=True, timeout=5,
        )
        interfaces = json.loads(result.stdout)
    except FileNotFoundError as error:
        raise ValueError("'ip' is required; install the Linux iproute2 tools") from error
    except (subprocess.SubprocessError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read network addresses from 'ip': {error}") from error
    if not isinstance(interfaces, list):
        raise ValueError("'ip' returned an unexpected address list")

    addresses = []
    for entry in interfaces:
        name = entry["ifname"]
        if interface is not None and name != interface:
            continue
        if "UP" not in entry.get("flags", []) or entry.get("operstate") == "DOWN":
            continue
        if "LOOPBACK" in entry.get("flags", []) or name == "lo":
            continue
        if interface is None and name.startswith(CONTAINER_PREFIXES):
            continue
        for info in entry.get("addr_info", []):
            if info.get("family") != "inet" or info.get("scope") != "global":
                continue
            address = ipaddress.IPv4Address(info["local"])
            if (address.is_loopback or address.is_link_local or address.is_unspecified
                    or address.is_multicast):
                continue
            addresses.append({"interface": name, "address": str(address)})

    addresses.sort(key=lambda item: not item["interface"].startswith(VPN_PREFIXES))
    seen = set()
    unique = []
    for item in addresses:
        if item["address"] not in seen:
            unique.append(item)
            seen.add(item["address"])
    if not unique:
        target = f" on interface {interface!r}" if interface else ""
        raise ValueError(f"no active VPN/LAN IPv4 address found{target}")
    return unique


def review_file(directory, filename):
    directory = Path(directory).expanduser().absolute()
    if not directory.is_dir():
        raise ValueError(f"serving directory does not exist: {directory}")
    if filename is None:
        return directory, ""
    relative = Path(filename)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("--file must be a relative path inside --directory")
    document = directory / relative
    if not document.is_file():
        raise ValueError(f"file does not exist or is not a regular file: {document}")
    with document.open("rb"):
        pass
    return directory, quote(relative.as_posix(), safe="/")


def path_serving_target(target):
    """Use a positional path's Git root, falling back to its containing directory."""
    is_directory = target.is_dir()
    parent = target.resolve() if is_directory else target.parent.resolve()
    try:
        result = subprocess.run(
            ["git", "-C", str(parent), "rev-parse", "--show-toplevel"],
            check=True, capture_output=True, text=True, timeout=5,
        )
        root = Path(result.stdout.rstrip("\n"))
        if root.is_absolute():
            # Resolve directory aliases, but preserve the selected file's symlink name.
            selected = parent if is_directory else parent / target.name
            return root, selected.relative_to(root)
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return (target, Path(".")) if is_directory else (target.parent, Path(target.name))


def serving_target(path=None, directory=None, filename=None):
    """Resolve a positional file/directory or an explicit root and relative file."""
    if path is not None:
        if directory is not None:
            raise ValueError("PATH and --directory/-d cannot be used together; choose one serving root")
        target = Path(path).expanduser().absolute()
        if target.is_dir():
            if filename is None:
                root, relative = path_serving_target(target)
                link = "" if relative == Path(".") else quote(relative.as_posix(), safe="/") + "/"
                return root, link
            directory = target
        elif target.is_file():
            if filename is not None:
                raise ValueError("a positional file and --file/-f cannot be used together; choose one file")
            directory, filename = path_serving_target(target)
        else:
            raise ValueError(f"path does not exist or is not a regular file or directory: {target}")
    return review_file(directory if directory is not None else ".", filename)


def addresses_for_bind(bind, interface=None):
    if ipaddress.IPv4Address(bind).is_loopback:
        if interface is not None:
            raise ValueError("--interface requires a VPN/LAN bind address")
        return [{"interface": "lo", "address": bind}]
    addresses = network_addresses(interface)
    if bind != "0.0.0.0":
        addresses = [item for item in addresses if item["address"] == bind]
        if not addresses:
            raise ValueError(f"no active address matches --bind {bind}")
    return addresses


def print_links(directory, port, selected_path, addresses):
    hyperlinks = sys.stdout.isatty() and os.environ.get("TERM") != "dumb"
    print(f"Serving {directory} on port {port}\n\nThen open from your PC:\n")
    links = [("Root directory", "")]
    if selected_path:
        links.append(("Selected path", selected_path))
    for title, path in links:
        print(f"{title}:")
        for item in addresses:
            name = item["interface"]
            if name.startswith("tailscale"):
                label = "Tailscale"
            elif name.startswith(VPN_PREFIXES):
                label = "VPN"
            elif name == "lo":
                label = "Local"
            else:
                label = "LAN"
            url = f"http://{item['address']}:{port}/{path}"
            # OSC 8 carries the entire target even when the visible URL wraps.
            link = f"\033]8;;{url}\033\\{url}\033]8;;\033\\" if hyperlinks else url
            print(f"- {link} — {label}\n")
    print("Press **Ctrl+C** in the SSH terminal when finished.", flush=True)


def port_preference(port):
    """Rank four-digit ports by patterns that are easy to remember and type."""
    a, b, c, d = map(int, str(port))
    if port in REPEATED_PORTS:
        return 0, REPEATED_PORTS.index(port)
    if a == b and c == d and abs(a - c) == 1:  # 2233, 3322
        return 1, port
    if (a == b == c or b == c == d) and abs(a - d) == 1:  # 2223, 2333
        return 2, port
    if b - a == c - b == d - c and abs(b - a) == 1:  # 5678, 8765
        return 3, port
    if a == b and c == d:  # 2255, 5577
        return 4, port
    if a == c and b == d:  # 1212, 8080
        return 5, port
    if a == d and b == c:  # 1221, 8008
        return 6, port
    if port % 1000 == 0:  # 7000, 8000
        return 7, port
    if port % 100 == 0:  # 2500, 8100
        return 8, port
    return 9, port


def preferred_ports():
    """Try memorable patterns, then the remaining unprivileged four-digit ports."""
    return sorted((port for port in range(1024, 10000)
                   if port not in BLOCKED_HTTP_PORTS), key=port_preference)


def create_server(bind, port, handler):
    """Reserve a requested port or the first available preferred port."""
    if port:
        return ThreadingHTTPServer((bind, port), handler)
    for candidate in preferred_ports():
        try:
            # Bind the actual server; retain its socket instead of probing ports.
            return ThreadingHTTPServer((bind, candidate), handler)
        except OSError as error:
            if error.errno not in (errno.EADDRINUSE, errno.EACCES):
                raise
    # Exhausted four-digit choices: let the kernel reserve an available port.
    return ThreadingHTTPServer((bind, 0), handler)


def port_number(value):
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 0 and 65535")
    return port


def ipv4_address(value):
    try:
        return str(ipaddress.IPv4Address(value))
    except ipaddress.AddressValueError as error:
        raise argparse.ArgumentTypeError("--bind must be an IPv4 address") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", metavar="PATH",
                        help="directory or file to link to (serves its Git root, "
                             "or containing directory outside Git); default: current directory")
    parser.add_argument("--bind", type=ipv4_address, default="0.0.0.0",
                        help="IPv4 bind address (default: 0.0.0.0)")
    parser.add_argument("-d", "--directory",
                        help="directory to serve instead of PATH (default: current directory)")
    parser.add_argument("-f", "--file",
                        help="file relative to the serving directory; may accompany a directory PATH (default: listing)")
    parser.add_argument("--port", type=port_number, default=0,
                        help="use a fixed port; 0 prefers memorable four-digit ports (default: 0)")
    parser.add_argument("--interface", help="print links for only this active interface")
    parser.add_argument("--verbose", action="store_true",
                        help="print HTTP request logs (disabled by default)")
    args = parser.parse_args()
    try:
        directory, selected_path = serving_target(args.path, args.directory, args.file)
        addresses = addresses_for_bind(args.bind, args.interface)
        handler = partial(PreviewHTTPRequestHandler, directory=str(directory), verbose=args.verbose,
                          finder=Finder(directory), history=VisitHistory(directory))
        with create_server(args.bind, args.port, handler) as server:
            print_links(directory, server.server_port, selected_path, addresses)
            server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.", flush=True)
    except (ValueError, OSError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
