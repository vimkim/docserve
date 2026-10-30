"""Read committed document history without changing a repository."""

from dataclasses import asdict, dataclass
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import subprocess
import time
from urllib.parse import quote

LIMIT = 8 * 1024 * 1024


class GitError(ValueError):
    pass


class MissingEntry(GitError):
    pass


def git(root, *args, limit=LIMIT, deadline=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0',
               GIT_NO_LAZY_FETCH='1', GIT_CONFIG_NOSYSTEM='1')
    try:
        process = subprocess.Popen(['git', '-C', str(root), '--literal-pathspecs', *args],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    except OSError as error:
        raise GitError('Git is unavailable.') from error
    data = bytearray()
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = min(deadline or float("inf"), time.monotonic() + 8)
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise GitError('Git operation timed out.')
            chunk = os.read(process.stdout.fileno(), min(65536, limit + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > limit:
                raise GitError('Git output exceeds the size limit.')
        try:
            code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as error:
            raise GitError('Git operation timed out.') from error
        if code:
            raise GitError('Git could not read this revision.')
        return bytes(data)
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()


def repo_for(path, deadline=None):
    result = git(path.parent, 'rev-parse', '--show-toplevel', limit=8192, deadline=deadline)
    root = Path(os.fsdecode(result.rstrip(b'\n'))).resolve()
    return root, path.relative_to(root).as_posix()


def blob(root, commit, path, deadline=None):
    if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit):
        raise GitError('Invalid revision.')
    parts = PurePosixPath(path).parts
    if not parts or path.startswith('/') or any(p in ('.', '..') for p in parts) or '\0' in path:
        raise GitError('Invalid historical path.')
    result = git(root, 'ls-tree', '-z', commit, '--', path, limit=16384, deadline=deadline)
    entries = result.rstrip(b'\0').split(b'\0')
    if len(entries) != 1 or b'\t' not in entries[0]:
        raise MissingEntry('Historical file was not found.')
    meta, name = entries[0].split(b'\t', 1)
    fields = meta.split()
    if len(fields) != 3 or fields[0] not in (b'100644', b'100755') or os.fsdecode(name) != path:
        raise MissingEntry('Historical file is not a regular file.')
    return fields[2].decode('ascii')


@dataclass(frozen=True)
class Revision:
    commit: str
    short: str
    datetime: str
    subject: str
    path: str
    blob: str
    url: str


@dataclass(frozen=True)
class DocumentHistory:
    url: str
    revisions: tuple
    default: str | None
    reason: str | None
    truncated: bool = False

    def json(self):
        return asdict(self)


def history(path, url, roots):
    try:
        deadline = time.monotonic() + 12
        if not path.is_file() or path.is_symlink():
            raise GitError('The document is not a regular file.')
        if path.stat().st_size > LIMIT:
            raise GitError('The document exceeds the size limit.')
        current = path.read_bytes()
        root, relative = repo_for(path, deadline)
        output = git(root, 'log', '--follow', '--first-parent', '-m', '--max-count=101',
                     '--format=%x00%H%x00%cI%x00%s%x00', '--name-status', '--no-ext-diff', '--no-textconv', '-z', '--', relative, deadline=deadline)
        fields = output.split(b'\0')
        revisions = []
        i = 0
        while i < len(fields):
            if fields[i] != b'' or i + 4 >= len(fields):
                break
            commit, date, subject = (os.fsdecode(x) for x in fields[i + 1:i + 4])
            i += 5
            if i >= len(fields) or not fields[i]:
                break
            status = fields[i].lstrip(b'\n').decode('ascii', 'replace')
            i += 1
            if i >= len(fields):
                break
            first = os.fsdecode(fields[i]); i += 1
            if status.startswith(('R', 'C')):
                if i >= len(fields):
                    break
                second = os.fsdecode(fields[i]); i += 1
                historical = second
                relative = first
            else:
                historical = first
            try:
                object_id = blob(root, commit, historical, deadline)
            except MissingEntry:
                continue
            identity = roots.automatic_identity(root)
            tree_url = '/__serve_html__/git/' + identity + '/' + commit + '/' + quote(historical, safe='/', errors='surrogatepass')
            revisions.append(Revision(commit, commit[:12], date, subject, historical, object_id, tree_url))
        truncated = len(revisions) > 100
        revisions = revisions[:100]
        if not revisions:
            return DocumentHistory(url, (), None, 'No committed history for this document.')
        latest = git(root, 'cat-file', 'blob', revisions[0].blob, deadline=deadline)
        default = revisions[0].commit if current != latest else next(
            (r.commit for r in revisions[1:] if r.blob != revisions[0].blob), None)
        return DocumentHistory(url, tuple(revisions), default,
                               None if default else 'No previous distinct committed version.', truncated)
    except (GitError, OSError, ValueError) as error:
        return DocumentHistory(url, (), None, str(error) or 'Git history is unavailable.')
