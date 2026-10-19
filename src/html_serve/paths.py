"""Map document URLs and filesystem roots without changing the main tree."""

import base64
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import subprocess
import threading
from urllib.parse import quote, unquote, urlsplit

if __package__:
    from .finder import Finder, FinderError
    from .history import VisitHistory
else:
    from finder import Finder, FinderError
    from history import VisitHistory


FILES_PREFIX = '/__docserve_fs__/'


def path_serving_target(target):
    """Use a document path's Git root, falling back to its containing directory."""
    is_directory = target.is_dir()
    parent = target.resolve() if is_directory else target.parent.resolve()
    try:
        result = subprocess.run(
            ['git', '-C', str(parent), 'rev-parse', '--show-toplevel'],
            check=True, capture_output=True, text=True, timeout=5,
        )
        root = Path(result.stdout.rstrip('\n'))
        if root.is_absolute():
            # Resolve directory aliases, but preserve the selected file's symlink name.
            selected = parent if is_directory else parent / target.name
            return root, selected.relative_to(root)
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return (target, Path('.')) if is_directory else (target.parent, Path(target.name))


@dataclass
class DocumentRoot:
    directory: Path
    resolved: Path
    prefix: str
    aliases: tuple
    finder: Finder
    history: VisitHistory
    automatic: bool = False

    def contains(self, path):
        try:
            return path.resolve().is_relative_to(self.resolved)
        except (OSError, RuntimeError):
            return False

    def url(self, relative='', directory=False):
        return self.prefix + quote(relative, safe='/', errors='surrogatepass') + (
            '/' if relative and directory else '')


class DocumentRoots:
    def __init__(self, directory, allowed=(), finder=None, history=None):
        directory = Path(os.path.abspath(directory))
        resolved = directory.resolve()
        self.primary = DocumentRoot(directory, resolved, '/', (directory, resolved),
                                    finder or Finder(directory), history or VisitHistory(directory))
        self.roots = [self.primary]
        self.mounted = {}
        self.lock = threading.Lock()
        for value in allowed:
            alias = Path(os.path.abspath(Path(value).expanduser()))
            if not alias.is_dir():
                raise ValueError(f'--allow-root requires an existing directory: {alias}')
            self.mount(alias)

    @staticmethod
    def automatic_identity(directory):
        # Encode the root itself so bookmarked URLs work in a fresh server process.
        return 'auto-' + base64.urlsafe_b64encode(os.fsencode(directory)).decode('ascii').rstrip('=')

    def mount(self, alias, automatic=False):
        resolved = alias.resolve()
        with self.lock:
            existing = next((root for root in self.roots if root.resolved == resolved), None)
            if existing:
                if alias not in existing.aliases:
                    existing.aliases = (*existing.aliases, alias)
                return existing
            identity = (self.automatic_identity(resolved) if automatic else
                        hashlib.sha256(os.fsencode(resolved)).hexdigest()[:16])
            root = DocumentRoot(resolved, resolved, FILES_PREFIX + identity + '/',
                                (alias, resolved), Finder(resolved), VisitHistory(resolved), automatic)
            self.roots.append(root)
            self.mounted[identity] = root
            return root

    def restore(self, identity):
        if not identity.startswith('auto-'):
            raise FinderError('Document directory was not found.', 404)
        try:
            encoded = identity.removeprefix('auto-')
            directory = Path(os.fsdecode(base64.b64decode(
                encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True)))
            if (not directory.is_absolute() or not directory.is_dir()
                    or self.automatic_identity(directory.resolve()) != identity):
                raise ValueError('Invalid directory')
        except (ValueError, OSError, RuntimeError) as error:
            raise FinderError('Document directory was not found.', 404) from error
        root = self.mount(directory, automatic=True)
        with self.lock:
            self.mounted[identity] = root
        return root

    @staticmethod
    def is_mounted(url):
        path = unquote(urlsplit(url).path, errors='surrogatepass')
        return path == FILES_PREFIX.rstrip('/') or path.startswith(FILES_PREFIX)

    def navigation(self, url):
        """Return the root, target, and relative path for a document URL."""
        request = urlsplit(url)
        decoded = unquote(request.path, errors='surrogatepass')
        parts = PurePosixPath(decoded).parts[1:]
        if (request.scheme or request.netloc or not decoded.startswith('/')
                or '..' in parts or '\x00' in decoded or decoded.startswith('/__serve_html__/')):
            raise FinderError('Path must be a document URL inside a serving or document root.')
        root = self.primary
        if self.is_mounted(url):
            if len(parts) < 2:
                raise FinderError('Document directory was not found.', 404)
            root = self.mounted.get(parts[1]) or self.restore(parts[1])
            parts = parts[2:]
        relative = '/'.join(parts)
        path = root.directory.joinpath(*parts)
        if root is not self.primary and not root.contains(path):
            raise FinderError('Path leaves its document root.', 403)
        return root, path, relative

    def absolute_url(self, url):
        """Map an absolute filesystem link after ordinary web-path lookup failed."""
        request = urlsplit(url)
        decoded = unquote(request.path, errors='surrogatepass')
        if ('\x00' in decoded or '..' in PurePosixPath(decoded).parts
                or not decoded.startswith('/') or request.netloc or request.scheme):
            return None
        candidate = Path(decoded)
        with self.lock:
            # Discover each automatic root independently of previously opened paths.
            matches = [(alias, root) for root in self.roots if not root.automatic
                       for alias in root.aliases if candidate.is_relative_to(alias)]
        if matches:
            alias, root = max(matches, key=lambda match: len(match[0].parts))
            relative = candidate.relative_to(alias)
        else:
            if not (candidate.is_file() or candidate.is_dir()):
                return None
            directory, relative = path_serving_target(candidate)
            root = self.mount(directory, automatic=True)
        relative = relative.as_posix()
        relative = '' if relative == '.' else relative
        target = root.directory / relative
        if not root.contains(target):
            raise FinderError('Absolute link leaves its document root through a symbolic link.', 403)
        return request._replace(path=root.url(relative, decoded.endswith('/'))).geturl()

    @staticmethod
    def result_urls(root, result):
        """Keep finder/history paths relative while publishing usable mounted URLs."""
        if root.prefix != '/':
            result['results'] = [dict(item, url=root.prefix + item['url'].lstrip('/'))
                                 for item in result['results'] if root.contains(root.directory / item['path'])]
        return result
