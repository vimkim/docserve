"""Visit history shared across ports and processes serving the same root."""

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import threading

if __package__:
    from .finder import fuzzy_rank, path_url
else:
    from finder import fuzzy_rank, path_url


class VisitHistory:
    def __init__(self, root):
        self.root = Path(root).resolve()
        cache = os.environ.get('XDG_CACHE_HOME')
        cache = Path(cache) if cache and Path(cache).is_absolute() else Path.home() / '.cache'
        identity = hashlib.sha256(os.fsencode(self.root)).hexdigest()
        self.path = cache / 'html-serve' / 'visits' / (identity + '.json')
        self.memory = []
        self.unsaved = {}
        self.warning = ''
        self.lock = threading.Lock()

    @contextmanager
    def disk_lock(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.path.with_suffix('.lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def read(self):
        try:
            with self.path.open('rb') as stream:
                document = json.loads(stream.read(1024 * 1024))
        except FileNotFoundError:
            return []
        except (ValueError, UnicodeDecodeError):
            self.warning = 'Unreadable history cache. New visits will replace it.'
            return []
        entries = document.get('entries', []) if isinstance(document, dict) else []
        if not isinstance(entries, list):
            return []
        valid = []
        for entry in entries[:100]:
            if not isinstance(entry, dict):
                continue
            path, kind = entry.get('path'), entry.get('kind')
            if (not isinstance(path, str) or '\x00' in path or PurePosixPath(path).is_absolute()
                    or '..' in PurePosixPath(path).parts or kind not in ('file', 'directory')
                    or not isinstance(entry.get('visited_at'), str)):
                continue
            valid.append(entry)
        return valid

    def save(self, entries):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             prefix='.visits-', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({'version': 1, 'entries': entries}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def record(self, path, kind):
        entry = {'path': path, 'kind': kind, 'visited_at': datetime.now(timezone.utc).isoformat()}
        with self.lock:
            self.unsaved[path] = entry
            self.unsaved = {item['path']: item for item in self.merge([], self.unsaved.values())}
            self.memory = self.merge(self.memory, self.unsaved.values())
            try:
                with self.disk_lock():
                    self.memory = self.merge(self.read(), self.unsaved.values())
                    self.save(self.memory)
                    self.unsaved.clear()
                    self.warning = ''
            except OSError:
                self.warning = 'History cannot be saved. Recent visits remain available for this server session.'

    @staticmethod
    def merge(stored, unsaved):
        entries = {}
        for item in [*stored, *unsaved]:
            previous = entries.get(item['path'])
            if previous is None or previous['visited_at'] < item['visited_at']:
                entries[item['path']] = item
        return sorted(entries.values(), key=lambda item: item['visited_at'], reverse=True)[:100]

    def recent(self, query=''):
        with self.lock:
            try:
                with self.disk_lock():
                    self.memory = self.merge(self.read(), self.unsaved.values())
            except OSError:
                self.warning = 'History cannot be loaded. Showing visits from this server session.'
            results = []
            for entry in self.memory:
                path, kind = entry['path'], entry['kind']
                target = self.root / path
                try:
                    exists = target.is_dir() if kind == 'directory' else target.is_file()
                except OSError:
                    exists = False
                if exists and fuzzy_rank(query, path or '/') is not None:
                    results.append({**entry, 'url': path_url(path, kind == 'directory')})
            return {'results': results, 'truncated': False, 'message': self.warning}
