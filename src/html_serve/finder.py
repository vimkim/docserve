"""Bounded, read-only search of a serving tree without browser dependencies."""

import base64
import codecs
from dataclasses import dataclass
from datetime import datetime, timezone
import fnmatch
from itertools import islice
import json
import os
from pathlib import Path, PurePosixPath
import selectors
import shutil
import stat
import subprocess
import tempfile
import time
from urllib.parse import quote


RESULT_LIMIT = 200
ENTRY_LIMIT = 20000
SCAN_SECONDS = 3
PREVIEW_BYTES = 65536
FILE_BYTES = 2 * 1024 * 1024


class FinderError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class TreeEntry:
    """A scanned path and reusable directory entry, kept only for this request."""

    path: str
    directory: bool
    source: os.DirEntry


def segment_matches(pattern, value):
    # Git uses backslashes to quote literal characters within a pattern.
    translated, index = [], 0
    while index < len(pattern):
        char = pattern[index]
        if char == '\\' and index + 1 < len(pattern):
            index += 1
            literal = pattern[index]
            translated.append({'*': '[*]', '?': '[?]', '[': '[[]'}.get(literal, literal))
        else:
            translated.append(char)
        index += 1
    return fnmatch.fnmatchcase(value, ''.join(translated))


def path_url(path, directory=False):
    return '/' + quote(path, safe='/', errors='surrogatepass') + ('/' if directory and path else '')


def glob_parts(pattern, parts):
    """Match Git-style path segments, with ** spanning directory boundaries."""
    positions = {0}
    for number, segment in enumerate(pattern):
        if not positions:
            return False
        if segment == '**':
            minimum = min(positions) + (1 if number == len(pattern) - 1 and number else 0)
            positions = set(range(minimum, len(parts) + 1))
        else:
            positions = {index + 1 for index in positions if index < len(parts)
                         and segment_matches(segment, parts[index])}
    return len(parts) in positions


class IgnoreRules:
    def __init__(self, rules=()):
        self.rules = list(rules)

    def beneath(self, directory, relative):
        rules = list(self.rules)
        # Later sources take precedence, as in ripgrep.
        for priority, name in enumerate(('.gitignore', '.ignore', '.rgignore')):
            try:
                with (directory / name).open(encoding='utf-8', errors='replace') as stream:
                    lines = stream.read(PREVIEW_BYTES).splitlines()
            except OSError:
                continue
            for line in lines:
                # Preserve a final space when an odd number of backslashes quotes it.
                while line.endswith(' '):
                    preceding = len(line[:-1]) - len(line[:-1].rstrip('\\'))
                    if preceding % 2:
                        break
                    line = line[:-1]
                if not line or line.startswith('#'):
                    continue
                negate = line.startswith('!')
                if negate:
                    line = line[1:]
                directory_only = line.endswith('/')
                line = line.removesuffix('/')
                anchored = line.startswith('/') or '/' in line
                line = line.removeprefix('/')
                if line:
                    rules.append((priority, relative, line, anchored, directory_only, negate))
        rules.sort(key=lambda rule: rule[0])
        return IgnoreRules(rules)

    def excludes(self, relative, directory):
        ignored = False
        for _, base, pattern, anchored, directory_only, negate in self.rules:
            if directory_only and not directory:
                continue
            local = relative[len(base) + 1:] if base else relative
            matched = (glob_parts(pattern.split('/'), local.split('/')) if anchored
                       else segment_matches(pattern, local.rsplit('/', 1)[-1]))
            if matched:
                ignored = not negate
        return ignored


def fuzzy_rank(query, path):
    folded = path.casefold()
    score = len(path) / 100
    for token in query.casefold().split():
        positions = []
        start = 0
        for char in token:
            found = folded.find(char, start)
            if found < 0:
                return None
            positions.append(found)
            start = found + 1
        score += positions[0] + (positions[-1] - positions[0] + 1 - len(token)) * 2
        if token in folded.rsplit('/', 1)[-1]:
            score -= 30
        if folded.rsplit('/', 1)[-1].startswith(token):
            score -= 20
    return score


def text_window(text, column=0, limit=4000):
    """Keep a selected UTF-8 byte column visible when shortening a long line."""
    position = len(text.encode('utf-8')[:max(0, column)].decode('utf-8', errors='ignore'))
    start = max(0, position - limit // 4) if len(text) > limit else 0
    return text[start:start + limit], len(text[:start].encode('utf-8'))


class Finder:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def target(self, path):
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root) or '.git' in resolved.relative_to(self.root).parts:
            raise FinderError('Path must stay inside the serving root and outside Git internals.')
        return resolved

    def resolve(self, value, directory=False):
        relative = PurePosixPath(value.lstrip('/'))
        if '..' in relative.parts or '.git' in relative.parts or '\x00' in value:
            raise FinderError('Path must stay inside the serving root.')
        path = self.root.joinpath(*relative.parts)
        try:
            self.target(path)
            parents = relative.parts if directory else relative.parts[:-1]
            ancestor = self.root
            for part in parents:
                ancestor /= part
                if ancestor.is_symlink():
                    raise FinderError('Search does not follow symlinked directories.')
            if not (path.is_dir() if directory else path.is_file()):
                raise FinderError('Search path was not found.', 404)
        except (OSError, RuntimeError) as error:
            raise FinderError('Search path is unavailable.', 404) from error
        return path

    def entries(self, scope, include):
        start = self.resolve(scope, directory=True)
        relative = start.relative_to(self.root).as_posix()
        relative = '' if relative == '.' else relative
        rules = IgnoreRules()
        # Retain ancestor rules when the reader limits the search scope.
        ancestor = self.root
        for part in start.relative_to(self.root).parts:
            base = '' if ancestor == self.root else ancestor.relative_to(self.root).as_posix()
            rules = rules.beneath(ancestor, base)
            ancestor /= part
        stack = [(start, relative, rules)]
        found, visited, truncated = [], 0, False
        deadline = time.monotonic() + SCAN_SECONDS
        while stack:
            directory, base, inherited = stack.pop()
            rules = inherited if include else inherited.beneath(directory, base)
            try:
                with os.scandir(directory) as stream:
                    children = list(islice(stream, ENTRY_LIMIT - visited + 1))
            except OSError:
                truncated = True
                continue
            for child in sorted(children, key=lambda item: item.name):
                visited += 1
                if visited > ENTRY_LIMIT or time.monotonic() >= deadline:
                    return found, True
                if child.name == '.git' or (not base and child.name == '__serve_html__'):
                    continue
                if not include and child.name.startswith('.'):
                    continue
                path = base + '/' + child.name if base else child.name
                try:
                    is_directory = child.is_dir(follow_symlinks=False)
                    if not include and rules.excludes(path, is_directory):
                        continue
                    if child.is_symlink():
                        target = self.target(Path(child.path))
                        if not target.is_file():
                            continue
                    elif not is_directory and not child.is_file(follow_symlinks=False):
                        continue
                except (OSError, RuntimeError, FinderError):
                    continue
                found.append(TreeEntry(path, is_directory, child))
                if is_directory:
                    stack.append((Path(child.path), path, rules))
        return found, truncated

    def search(self, mode='files', q='', scope='/', include=False, regex=False,
               filename=None, exclude_filename=''):
        if mode not in ('files', 'directories', 'contents', 'updated'):
            raise FinderError('Unknown search mode.')
        if filename is None:
            filename = r'\.(html|md)$' if mode == 'updated' else ''
        if len(q) > 500:
            raise FinderError('Search queries must contain at most 500 characters.')
        if len(filename) > 500 or len(exclude_filename) > 500:
            raise FinderError('Filename filters must contain at most 500 characters.')
        entries, truncated = self.entries(scope, include)
        if mode == 'contents':
            return self.contents(entries, q, regex, truncated, filename, exclude_filename)
        if mode == 'updated':
            return self.updated(entries, q, truncated, filename, exclude_filename)
        matches = []
        for entry in entries:
            path, directory = entry.path, entry.directory
            if directory != (mode == 'directories'):
                continue
            rank = fuzzy_rank(q, path)
            if rank is not None:
                matches.append((rank, path, directory))
        matches.sort()
        return {'results': [{'path': path, 'kind': 'directory' if directory else 'file',
                             'url': path_url(path, directory)}
                            for _, path, directory in matches[:RESULT_LIMIT]],
                'truncated': truncated or len(matches) > RESULT_LIMIT}

    def updated(self, entries, query, truncated, filename, exclude_filename):
        """Filter paths, then order the scanned files by nanosecond modification time."""
        deadline = time.monotonic() + SCAN_SECONDS
        if filename or exclude_filename:
            executable = shutil.which('rg')
            if not executable:
                raise FinderError('Filename filtering requires ripgrep (rg). Install rg on the server '
                                  'or clear the filename filters.', 503)
            entries, limited = self.filter_filenames(executable, entries, filename, exclude_filename, deadline)
            truncated = truncated or limited
        matches = []
        for entry in entries:
            if time.monotonic() >= deadline:
                truncated = True
                break
            if entry.directory or fuzzy_rank(query, entry.path) is None:
                continue
            try:
                # Ordinary files already passed the tree's traversal checks. Reuse
                # scandir metadata instead of resolving every ancestor again.
                # Symlink targets still need validation before following them.
                metadata = entry.source.stat(follow_symlinks=False)
                if stat.S_ISLNK(metadata.st_mode):
                    metadata = self.resolve(entry.path).stat()
                if not stat.S_ISREG(metadata.st_mode):
                    truncated = True
                    continue
            except (OSError, FinderError):
                truncated = True
                continue
            matches.append((metadata.st_mtime_ns, entry.path))
        matches.sort(key=lambda item: (-item[0], item[1].casefold(), item[1]))
        results = []
        for modified_ns, path in matches[:RESULT_LIMIT]:
            try:
                modified_at = datetime.fromtimestamp(modified_ns / 1_000_000_000, timezone.utc).isoformat()
            except (OverflowError, OSError, ValueError):
                modified_at = None
            results.append({'path': path, 'kind': 'file', 'url': path_url(path), 'modified_at': modified_at})
        return {'results': results, 'truncated': truncated or len(matches) > RESULT_LIMIT}

    def filter_filenames(self, executable, entries, filename, exclude_filename, deadline):
        """Use rg's bounded regex engine on NUL-delimited basenames, including newlines."""
        entries = [entry for entry in entries if not entry.directory]
        for pattern, exclude, label in ((filename, False, 'Include filenames'),
                                        (exclude_filename, True, 'Exclude filenames')):
            if not pattern:
                continue
            command = [executable, '--no-config', '--null-data', '--smart-case',
                       '--encoding', 'none', '--color', 'never', '--no-filename', '--no-line-number']
            if exclude:
                command.append('--invert-match')
            command.extend(['-e', pattern, '--', '-'])
            names = {os.fsencode(entry.path.rsplit('/', 1)[-1]) for entry in entries}
            data = b''.join(name + b'\x00' for name in sorted(names))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return [], True
            try:
                result = subprocess.run(command, input=data, capture_output=True, timeout=remaining)
            except subprocess.TimeoutExpired:
                return [], True
            except OSError as error:
                raise FinderError('Could not start ripgrep on the server.', 503) from error
            if result.returncode not in (0, 1):
                detail = result.stderr[:4096].decode('utf-8', errors='replace').strip()
                raise FinderError(f'{label}: {detail or "Invalid filename pattern."}')
            matching = set(result.stdout.split(b'\x00'))
            entries = [entry for entry in entries
                       if os.fsencode(entry.path.rsplit('/', 1)[-1]) in matching]
        return entries, False

    def contents(self, entries, query, regex, truncated, filename='', exclude_filename=''):
        executable = shutil.which('rg')
        if not executable:
            raise FinderError('Content search requires ripgrep (rg). Install rg on the server to enable it.', 503)
        deadline = time.monotonic() + SCAN_SECONDS
        entries, limited = self.filter_filenames(executable, entries, filename, exclude_filename, deadline)
        if limited:
            return {'results': [], 'truncated': True}
        if not query:
            return {'results': [], 'truncated': False, 'message': 'Type text to search file contents.'}
        command = [executable, '--no-config', '--json', '--smart-case', '--max-count', '40',
                   '--max-filesize', '2M', '--color', 'never']
        if not regex:
            command.append('--fixed-strings')
        command.extend(['-e', query, '--'])
        paths, oversized = [], False
        for entry in entries:
            path = entry.path
            if not entry.directory:
                try:
                    if (self.root / path).stat().st_size > FILE_BYTES:
                        oversized = True
                        continue
                except OSError:
                    continue
                paths.append('./' + path)
        paths.sort()
        batches, batch, size = [], [], 0
        for path in paths:
            length = len(os.fsencode(path)) + 1
            if batch and (len(batch) >= 128 or size + length > 32768):
                batches.append(batch)
                batch, size = [], 0
            batch.append(path)
            size += length
        if batch:
            batches.append(batch)
        # Validate a regex even when the tree contains no searchable files.
        if not batches:
            batches = [[os.devnull]]
        results, counts = [], {}
        for batch in batches:
            remaining = RESULT_LIMIT - len(results)
            matches, limited = self.rg_batch(command + batch, deadline, remaining)
            results.extend(matches)
            truncated = truncated or limited
            for result in matches:
                counts[result['path']] = counts.get(result['path'], 0) + 1
                if counts[result['path']] >= 40:
                    truncated = True
            if len(results) >= RESULT_LIMIT or time.monotonic() >= deadline:
                truncated = True
                break
        return {'results': results, 'truncated': truncated,
                'message': 'Files larger than 2 MiB were skipped.' if oversized else ''}

    def rg_batch(self, command, deadline, limit):
        """Read rg incrementally so output, execution time, and results remain bounded."""
        results, pending, received, limited = [], b'', 0, False
        with tempfile.TemporaryFile() as errors:
            try:
                process = subprocess.Popen(command, cwd=self.root, stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=errors)
            except OSError as error:
                raise FinderError('Could not start ripgrep on the server.', 503) from error
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while selector.get_map():
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            limited = True
                            break
                        events = selector.select(remaining)
                        if not events:
                            limited = True
                            break
                        chunk = os.read(process.stdout.fileno(), 65536)
                        if not chunk:
                            selector.unregister(process.stdout)
                            continue
                        received += len(chunk)
                        if received > 4 * FILE_BYTES:
                            limited = True
                            break
                        pending += chunk
                        while b'\n' in pending:
                            record, pending = pending.split(b'\n', 1)
                            event = json.loads(record)
                            if event.get('type') != 'match':
                                continue
                            data = event['data']
                            path = data['path'].get('text')
                            if path is None and 'bytes' in data['path']:
                                path = os.fsdecode(base64.b64decode(data['path']['bytes']))
                            text = data['lines'].get('text')
                            if path is None or text is None:
                                limited = True
                                continue
                            path = path.removeprefix('./')
                            try:
                                self.resolve(path)
                            except FinderError:
                                limited = True
                                continue
                            snippet, offset = text_window(text.rstrip('\r\n'), data['submatches'][0]['start'], 500)
                            results.append({'path': path, 'kind': 'file', 'url': path_url(path),
                                            'line': data['line_number'], 'text': ('…' if offset else '') + snippet,
                                            'matches': [{'start': m['start'], 'end': m['end']}
                                                        for m in data['submatches'][:100]]})
                            if len(results) >= limit:
                                limited = True
                                break
                        if len(results) >= limit:
                            break
                if limited:
                    process.kill()
                try:
                    code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    limited, code = True, 0
                if code not in (0, 1) and not limited:
                    errors.seek(0)
                    detail = errors.read(4096).decode('utf-8', errors='replace').strip()
                    raise FinderError(detail or 'ripgrep could not complete the search.')
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                process.stdout.close()
        return results, limited

    def preview(self, path, line=1, column=0):
        selected = self.resolve(path)
        try:
            with selected.open('rb') as stream:
                data = stream.read(FILE_BYTES + 1)
        except OSError as error:
            raise FinderError('This file cannot be previewed.', 404) from error
        if b'\x00' in data:
            return {'lines': [], 'message': 'Binary file. Open the file to view or download it.'}
        try:
            text = codecs.getincrementaldecoder('utf-8')().decode(
                data[:FILE_BYTES], final=len(data) <= FILE_BYTES)
        except UnicodeDecodeError:
            return {'lines': [], 'message': 'Preview is available for UTF-8 text files.'}
        source = text.split('\n') if text else []
        if text.endswith('\n'):
            source.pop()
        source = [value.removesuffix('\r') for value in source]
        first = max(0, min(line - 20, len(source) - 60)) if line > 1 else 0
        lines, size = [], 0
        for number, value in enumerate(source[first:first + 200], first + 1):
            value, offset = text_window(value, column if number == line else 0)
            size += len(value.encode('utf-8'))
            if size > PREVIEW_BYTES:
                break
            lines.append({'number': number, 'text': value, **({'offset': offset} if offset else {})})
        return {'lines': lines, 'truncated': len(data) > FILE_BYTES or first > 0
                or first + len(lines) < len(source) or any(len(s) > 4000 for s in source),
                'message': 'Empty file.' if not source else ''}
