"""Map document URLs and configured filesystem roots without widening the main tree."""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit

if __package__:
    from .finder import Finder, FinderError
    from .history import VisitHistory
else:
    from finder import Finder, FinderError
    from history import VisitHistory


FILES_PREFIX = '/__docserve_fs__/'


@dataclass
class DocumentRoot:
    directory: Path
    resolved: Path
    prefix: str
    aliases: tuple
    finder: Finder
    history: VisitHistory

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
        for value in allowed:
            alias = Path(os.path.abspath(Path(value).expanduser()))
            if not alias.is_dir():
                raise ValueError(f'--allow-root requires an existing directory: {alias}')
            resolved = alias.resolve()
            existing = next((root for root in self.roots if root.resolved == resolved), None)
            if existing:
                existing.aliases = (*existing.aliases, alias)
                continue
            identity = hashlib.sha256(os.fsencode(resolved)).hexdigest()[:16]
            self.roots.append(DocumentRoot(resolved, resolved, FILES_PREFIX + identity + '/',
                                           (alias, resolved), Finder(resolved), VisitHistory(resolved)))
        self.mounted = {root.prefix.split('/')[-2]: root for root in self.roots[1:]}

    @staticmethod
    def is_mounted(url):
        path = unquote(urlsplit(url).path, errors='surrogatepass')
        return path == FILES_PREFIX.rstrip('/') or path.startswith(FILES_PREFIX)

    def navigation(self, url):
        """Return the root, target, and relative path for an ordinary document URL."""
        request = urlsplit(url)
        decoded = unquote(request.path, errors='surrogatepass')
        parts = PurePosixPath(decoded).parts[1:]
        if (request.scheme or request.netloc or not decoded.startswith('/')
                or '..' in parts or '\x00' in decoded or decoded.startswith('/__serve_html__/')):
            raise FinderError('Path must be a document URL inside a configured directory.')
        root = self.primary
        if self.is_mounted(url):
            if len(parts) < 2 or parts[1] not in self.mounted:
                raise FinderError('Allowed directory was not found.', 404)
            root = self.mounted[parts[1]]
            parts = parts[2:]
        relative = '/'.join(parts)
        path = root.directory.joinpath(*parts)
        if root is not self.primary and not root.contains(path):
            raise FinderError('Path leaves the configured --allow-root directory.', 403)
        return root, path, relative

    def absolute_url(self, url):
        """Map an absolute filesystem link after ordinary web-path lookup failed."""
        request = urlsplit(url)
        decoded = unquote(request.path, errors='surrogatepass')
        if ('\x00' in decoded or '..' in PurePosixPath(decoded).parts
                or not decoded.startswith('/') or request.netloc or request.scheme):
            return None
        candidate = Path(decoded)
        matches = [(alias, root) for root in self.roots for alias in root.aliases
                   if candidate.is_relative_to(alias)]
        if not matches:
            return None
        alias, root = max(matches, key=lambda match: len(match[0].parts))
        relative = candidate.relative_to(alias).as_posix()
        relative = '' if relative == '.' else relative
        target = root.directory / relative
        if not root.contains(target):
            raise FinderError('Absolute link leaves its configured directory through a symbolic link.', 403)
        return request._replace(path=root.url(relative, decoded.endswith('/'))).geturl()

    @staticmethod
    def result_urls(root, result):
        """Keep finder/history paths relative while publishing usable mounted URLs."""
        if root.prefix != '/':
            result['results'] = [dict(item, url=root.prefix + item['url'].lstrip('/'))
                                 for item in result['results'] if root.contains(root.directory / item['path'])]
        return result
