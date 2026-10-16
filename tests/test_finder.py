"""Verify search and recent visits through a live HTTP server."""

import json
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener
from urllib.error import HTTPError

import test_serve_html as existing


class FinderTests(unittest.TestCase):
    server = existing.ServeHTML.server

    def request_json(self, base, endpoint, **query):
        client = build_opener(ProxyHandler({}))
        with client.open(base + '__serve_html__/api/' + endpoint + '?' + urlencode(query)) as response:
            return json.load(response)

    def visit(self, base, path, method='GET', metadata=True):
        headers = {'Accept': 'text/html'}
        if metadata:
            headers.update({'Sec-Fetch-Dest': 'document', 'Sec-Fetch-Mode': 'navigate'})
        client = build_opener(ProxyHandler({}))
        with client.open(Request(base + path, headers=headers, method=method)) as response:
            response.read()

    def test_recent_visits_exclude_previews_and_assets_and_survive_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'root'
            root.mkdir()
            (root / 'docs').mkdir()
            (root / 'docs/readme.md').write_text('# Read me\n')
            (root / 'page.html').write_text('<h1>Page</h1>')
            env = {**os.environ, 'XDG_CACHE_HOME': str(Path(temp) / 'cache')}
            with self.server(root, '--bind', '127.0.0.1', env=env) as (_, urls, _):
                base = urls[0]
                self.visit(base, '')
                self.visit(base, 'docs/')
                self.visit(base, 'docs/readme.md')
                self.request_json(base, 'preview', path='page.html')
                self.visit(base, '__serve_html__/navigation.js')
                self.visit(base, '', method='HEAD')
                client = build_opener(ProxyHandler({}))
                with client.open(base + 'docs/readme.md?raw=1') as response:
                    response.read()
                result = self.request_json(base, 'recent')
                self.assertEqual([r['path'] for r in result['results']], ['docs/readme.md', 'docs', ''])
                self.visit(base, 'page.html', metadata=False)
                self.visit(base, 'docs/')
                result = self.request_json(base, 'recent')
                self.assertEqual([r['path'] for r in result['results']], ['docs', 'page.html', 'docs/readme.md', ''])
            with self.server(root, '--bind', '127.0.0.1', env=env) as (_, urls, _):
                result = self.request_json(urls[0], 'recent', q='readme')
                self.assertEqual([r['path'] for r in result['results']], ['docs/readme.md'])
                (root / 'docs/readme.md').unlink()
                self.assertEqual(self.request_json(urls[0], 'recent', q='readme')['results'], [])
            other = Path(temp) / 'other'
            other.mkdir()
            with self.server(other, '--bind', '127.0.0.1', env=env) as (_, urls, _):
                self.assertEqual(self.request_json(urls[0], 'recent')['results'], [])

    def test_history_merges_concurrent_servers_and_degrades_without_a_writable_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'root'
            root.mkdir()
            for index in range(12):
                (root / f'{index}.txt').write_text(str(index))
            env = {**os.environ, 'XDG_CACHE_HOME': str(Path(temp) / 'cache')}
            with self.server(root, '--bind', '127.0.0.1', env=env) as (_, first, _):
                with self.server(root, '--bind', '127.0.0.1', env=env) as (_, second, _):
                    with ThreadPoolExecutor(max_workers=4) as executor:
                        list(executor.map(lambda i: self.visit((first if i % 2 else second)[0], f'{i}.txt'), range(12)))
                    result = self.request_json(first[0], 'recent')
                    self.assertEqual({r['path'] for r in result['results']}, {f'{i}.txt' for i in range(12)})
            invalid_cache = Path(temp) / 'not-a-directory'
            invalid_cache.write_text('cache unavailable')
            env['XDG_CACHE_HOME'] = str(invalid_cache)
            with self.server(root, '--bind', '127.0.0.1', env=env) as (_, urls, _):
                self.visit(urls[0], '1.txt')
                result = self.request_json(urls[0], 'recent')
                self.assertEqual([r['path'] for r in result['results']], ['1.txt'])
                self.assertIn('server session', result['message'])

    def test_recent_type_filters_preserve_query_order_and_stored_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'root'
            (root / 'docs/nested').mkdir(parents=True)
            (root / 'docs/one.txt').write_text('one')
            (root / 'docs/two.txt').write_text('two')
            env = {**os.environ, 'XDG_CACHE_HOME': str(Path(temp) / 'cache')}
            with self.server(root, '--bind', '127.0.0.1', env=env) as (_, urls, _):
                base = urls[0]
                for path in ('', 'docs/', 'docs/one.txt', 'docs/nested/', 'docs/two.txt'):
                    self.visit(base, path)
                expected = ['docs/two.txt', 'docs/nested', 'docs/one.txt', 'docs', '']
                for kind, paths in [('all', expected), ('file', ['docs/two.txt', 'docs/one.txt']),
                                    ('directory', ['docs/nested', 'docs', ''])]:
                    with self.subTest(kind=kind):
                        result = self.request_json(base, 'recent', kind=kind)
                        self.assertEqual([r['path'] for r in result['results']], paths)
                result = self.request_json(base, 'recent', kind='directory', q='nested')
                self.assertEqual([r['path'] for r in result['results']], ['docs/nested'])
                self.assertEqual(self.request_json(base, 'recent', kind='directory', q='one.txt')['results'], [])
                result = self.request_json(base, 'recent', kind='file', q='one')
                self.assertEqual([r['path'] for r in result['results']], ['docs/one.txt'])
                (root / 'docs/two.txt').unlink()
                result = self.request_json(base, 'recent', kind='file')
                self.assertEqual([r['path'] for r in result['results']], ['docs/one.txt'])
                with self.assertRaises(HTTPError) as caught:
                    self.request_json(base, 'recent', kind='unknown')
                self.assertEqual(caught.exception.code, 400)
                caught.exception.close()
            with self.server(root, '--bind', '127.0.0.1', env=env) as (_, urls, _):
                result = self.request_json(urls[0], 'recent')
                self.assertEqual([r['path'] for r in result['results']], expected[1:])

    @unittest.skipIf(os.geteuid() == 0, 'Root bypasses the cache permission fixture')
    def test_history_keeps_unsaved_visits_when_existing_cache_remains_readable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'root'
            root.mkdir()
            for name in ('one.txt', 'two.txt', 'three.txt'):
                (root / name).write_text(name)
            cache = Path(temp) / 'cache'
            env = {**os.environ, 'XDG_CACHE_HOME': str(cache)}
            with self.server(root, '--bind', '127.0.0.1', env=env) as (_, urls, _):
                base = urls[0]
                self.visit(base, 'one.txt')
                cache_directory = cache / 'html-serve/visits'
                cache_directory.chmod(0o500)
                try:
                    self.visit(base, 'two.txt')
                    self.assertEqual([r['path'] for r in self.request_json(base, 'recent')['results']],
                                     ['two.txt', 'one.txt'])
                    self.visit(base, 'three.txt')
                    self.assertEqual([r['path'] for r in self.request_json(base, 'recent')['results']],
                                     ['three.txt', 'two.txt', 'one.txt'])
                finally:
                    cache_directory.chmod(0o700)
                self.visit(base, 'one.txt')
            with self.server(root, '--bind', '127.0.0.1', env=env) as (_, urls, _):
                self.assertEqual([r['path'] for r in self.request_json(urls[0], 'recent')['results']],
                                 ['one.txt', 'three.txt', 'two.txt'])

    def test_content_results_are_limited_and_large_files_are_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'many.txt').write_text('needle\n' * 100)
            (root / 'huge.txt').write_bytes(b'needle\n' + b'x' * (2 * 1024 * 1024))
            with self.server(root, '--bind', '127.0.0.1') as (_, urls, _):
                result = self.request_json(urls[0], 'search', mode='contents', q='needle')
                self.assertTrue(result['truncated'])
                self.assertEqual(len(result['results']), 40)
                self.assertIn('2 MiB', result['message'])

    def test_fuzzy_paths_empty_directories_ignores_scope_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'root'
            root.mkdir()
            (root / 'notes/empty').mkdir(parents=True)
            (root / 'notes/guide.md').write_text('# Guide\n')
            (root / 'notes/secret.md').write_text('ignored\n')
            (root / 'notes/.gitignore').write_text('secret.md\n')
            (root / '.gitignore').write_text('ignored/\n*.log\n!keep.log\n')
            (root / 'ignored').mkdir()
            (root / 'ignored/file.md').write_text('ignore me')
            (root / '.hidden.md').write_text('hidden')
            (root / 'drop.log').write_text('ignored')
            (root / 'keep.log').write_text('included')
            (root / '.git').mkdir()
            (root / '.git/config').write_text('never search')
            (root / 'metadata-link').symlink_to('.git/config')
            (Path(temp) / 'outside.md').write_text('outside')
            (root / 'outside.md').symlink_to('../outside.md')
            (root / 'linked.md').symlink_to('notes/guide.md')
            (root / 'loop').symlink_to('.')
            with self.server(root, '--bind', '127.0.0.1') as (_, urls, _):
                base = urls[0]
                result = self.request_json(base, 'search', mode='files', q='ngmd')
                self.assertEqual([r['path'] for r in result['results']], ['notes/guide.md'])
                result = self.request_json(base, 'search', mode='files')
                self.assertEqual({r['path'] for r in result['results']},
                                 {'notes/guide.md', 'linked.md', 'keep.log'})
                result = self.request_json(base, 'search', mode='directories', q='nemp')
                self.assertEqual([r['path'] for r in result['results']], ['notes/empty'])
                result = self.request_json(base, 'search', mode='files', scope='/notes/')
                self.assertEqual([r['path'] for r in result['results']], ['notes/guide.md'])
                result = self.request_json(base, 'search', mode='files', include='1')
                paths = {r['path'] for r in result['results']}
                self.assertTrue({'notes/secret.md', '.hidden.md', 'drop.log', 'ignored/file.md'} <= paths)
                self.assertFalse(any(p.startswith('.git/') or p in ('outside.md', 'metadata-link') for p in paths))
                with self.assertRaises(HTTPError) as caught:
                    self.request_json(base, 'preview', path='metadata-link')
                self.assertEqual(caught.exception.code, 400)
                caught.exception.close()

    def test_updated_defaults_to_recursive_html_and_md_in_modification_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'root'
            (root / 'nested/deep').mkdir(parents=True)
            names = ['old.md', 'nested/deep/new.HTML', 'nested/한글 # ?.MD', 'Alpha.md', 'alpha.md',
                     'notes.txt', 'page.htm', 'guide.markdown']
            timestamp = 1700000000_000000000
            for index, name in enumerate(names):
                (root / name).write_text(name)
                # The first three differ only by nanoseconds.
                modified = timestamp + (index if index < 3 else 0)
                os.utime(root / name, ns=(modified, modified))
            (root / 'directory.md').mkdir()
            (Path(temp) / 'outside.md').write_text('outside')
            (root / 'outside.md').symlink_to('../outside.md')
            (root / 'loop').symlink_to('.')
            env = {**os.environ, 'XDG_CACHE_HOME': str(Path(temp) / 'cache')}
            with self.server(root, '--bind', '127.0.0.1', env=env) as (_, urls, _):
                base = urls[0]
                self.visit(base, 'old.md')
                result = self.request_json(base, 'search', mode='updated')
                expected = ['nested/한글 # ?.MD', 'nested/deep/new.HTML', 'Alpha.md', 'alpha.md', 'old.md']
                self.assertEqual([r['path'] for r in result['results']], expected)
                self.assertFalse(result['truncated'])
                self.assertTrue(all(r['kind'] == 'file' and r['modified_at'].endswith('+00:00')
                                    for r in result['results']))
                selected = result['results'][0]
                self.assertIn('%23', selected['url'])
                preview = self.request_json(base, 'preview', url=selected['url'])
                self.assertEqual(preview['lines'][0]['text'], selected['path'])
                self.assertEqual([r['path'] for r in self.request_json(base, 'recent')['results']], ['old.md'])
                result = self.request_json(base, 'search', mode='updated', q='nd')
                self.assertEqual([r['path'] for r in result['results']], expected[:2])
                os.utime(root / 'old.md', ns=(timestamp + 100, timestamp + 100))
                result = self.request_json(base, 'search', mode='updated')
                self.assertEqual(result['results'][0]['path'], 'old.md')

    def test_updated_filename_filters_can_be_changed_cleared_and_combined_with_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'nested.md').mkdir()
            names = ['guide.md', 'Guide.MD', 'draft.md', '.hidden.md', 'notes.txt', 'nested.md/plain.txt']
            for name in names:
                (root / name).write_text('text')
                os.utime(root / name, (1700000000, 1700000000))
            (root / '.gitignore').write_text('draft.md\n')
            (root / '.git').mkdir()
            (root / '.git/private.md').write_text('internal')
            (root / 'git-link.md').symlink_to('.git/private.md')
            with self.server(root, '--bind', '127.0.0.1') as (_, urls, _):
                base = urls[0]
                def paths(**options):
                    return [r['path'] for r in self.request_json(base, 'search', mode='updated', **options)['results']]
                self.assertEqual(paths(), ['Guide.MD', 'guide.md'])
                self.assertEqual(set(paths(include='1')), {'Guide.MD', 'guide.md', 'draft.md', '.hidden.md'})
                self.assertEqual(paths(filename=''), ['Guide.MD', 'guide.md', 'nested.md/plain.txt', 'notes.txt'])
                self.assertEqual(paths(filename=r'\.txt$'), ['nested.md/plain.txt', 'notes.txt'])
                self.assertEqual(paths(filename=r'^Guide\.MD$'), ['Guide.MD'])
                self.assertEqual(paths(exclude_filename=r'^guide'), [])
                self.assertEqual(paths(filename='', scope_url='/nested.md/'), ['nested.md/plain.txt'])
                self.assertEqual(paths(scope='/nested.md/'), [])  # Match the basename, not directory names.
                for field in ('filename', 'exclude_filename'):
                    for pattern in ('[', 'x' * 501):
                        with self.subTest(field=field, pattern=pattern), self.assertRaises(HTTPError) as caught:
                            self.request_json(base, 'search', mode='updated', **{field: pattern})
                        self.assertEqual(caught.exception.code, 400)
                        caught.exception.close()

    def test_updated_limits_choose_newest_files_across_the_scan_and_report_timeouts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index in range(205):
                selected = root / f'{index:03}.md'
                selected.write_text('text')
                os.utime(selected, (1700000000 + index, 1700000000 + index))
            finder = existing.helper.Finder(root)
            result = finder.search(mode='updated')
            self.assertEqual([r['path'] for r in result['results']], [f'{i:03}.md' for i in range(204, 4, -1)])
            self.assertTrue(result['truncated'])
            with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('rg', 3)):
                result = finder.search(mode='updated')
            self.assertEqual(result['results'], [])
            self.assertTrue(result['truncated'])

    def test_updated_metadata_avoids_rewalking_every_parent_for_each_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            nested = root.joinpath(*['nested'] * 8)
            nested.mkdir(parents=True)
            for index in range(80):
                (nested / f'{index:03}.md').touch()
            finder = existing.helper.Finder(root)
            # Count filesystem calls instead of relying on machine-dependent timings.
            with patch('os.lstat', wraps=os.lstat) as lookups:
                result = finder.search(mode='updated')
            self.assertEqual(len(result['results']), 80)
            self.assertLess(lookups.call_count, 100)

    def test_updated_metadata_validates_symlinks_and_handles_files_changed_after_scanning(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'root'
            root.mkdir()
            for name in ('target.md', 'changed.md', 'directory.md', 'removed.md'):
                (root / name).touch()
                os.utime(root / name, (1700000000, 1700000000))
            (root / 'alias.md').symlink_to('target.md')
            outside = Path(temp) / 'outside.md'
            outside.touch()
            finder = existing.helper.Finder(root)
            scan = finder.entries

            def scan_then_change(scope, include):
                entries, truncated = scan(scope, include)
                for name in ('changed.md', 'directory.md', 'removed.md'):
                    (root / name).unlink()
                (root / 'changed.md').symlink_to(outside)
                (root / 'directory.md').mkdir()
                return entries, truncated

            with patch.object(finder, 'entries', side_effect=scan_then_change):
                result = finder.search(mode='updated')
            self.assertEqual([r['path'] for r in result['results']], ['alias.md', 'target.md'])
            self.assertEqual(result['results'][0]['modified_at'], result['results'][1]['modified_at'])
            self.assertTrue(result['truncated'])

    def test_ignore_patterns_preserve_escaped_names_and_root_anchors_in_scoped_search(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'sub').mkdir()
            (root / 'cache').mkdir()
            (root / '.gitignore').write_text('space\\ name.md\nliteral\\*.md\n/root-only.md\ncache/**\n')
            for name in ['space name.md', 'literal*.md', 'root-only.md', 'sub/root-only.md']:
                (root / name).write_text('text')
            with self.server(root, '--bind', '127.0.0.1') as (_, urls, _):
                result = self.request_json(urls[0], 'search', mode='files')
                self.assertEqual([r['path'] for r in result['results']], ['sub/root-only.md'])
                result = self.request_json(urls[0], 'search', mode='files', scope='/sub/')
                self.assertEqual([r['path'] for r in result['results']], ['sub/root-only.md'])
                result = self.request_json(urls[0], 'search', mode='directories', q='cache')
                self.assertEqual([r['path'] for r in result['results']], ['cache'])

    def test_ignore_source_priority_survives_nested_gitignore_overrides(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'sub').mkdir()
            (root / '.rgignore').write_text('secret.txt\n')
            (root / 'sub/.gitignore').write_text('!secret.txt\n')
            (root / 'sub/secret.txt').write_text('secret')
            (root / 'sub/visible.txt').write_text('visible')
            with self.server(root, '--bind', '127.0.0.1') as (_, urls, _):
                result = self.request_json(urls[0], 'search', mode='files')
                self.assertEqual([r['path'] for r in result['results']], ['sub/visible.txt'])

    def test_preview_uses_rg_line_boundaries_and_handles_truncated_utf8(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'lines.txt').write_text('alpha\u2028beta\nneedle\n', encoding='utf-8')
            (root / 'large.txt').write_text('한글\n' * 400000, encoding='utf-8')
            with self.server(root, '--bind', '127.0.0.1') as (_, urls, _):
                result = self.request_json(urls[0], 'search', mode='contents', q='needle')
                self.assertEqual(result['results'][0]['line'], 2)
                result = self.request_json(urls[0], 'preview', path='lines.txt', line=2)
                self.assertEqual(result['lines'][1], {'number': 2, 'text': 'needle'})
                result = self.request_json(urls[0], 'preview', path='large.txt')
                self.assertEqual(result['lines'][0]['text'], '한글')
                self.assertTrue(result['truncated'])

    def test_non_utf8_filename_does_not_break_search_preview_or_recent_visits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            name = os.fsdecode(b'bad-\xff.txt')
            (root / name).write_text('Valid UTF-8 content')
            with self.server(root, '--bind', '127.0.0.1') as (_, urls, _):
                result = self.request_json(urls[0], 'search', mode='files')
                self.assertEqual(result['results'][0]['path'], name)
                url = result['results'][0]['url']
                result = self.request_json(urls[0], 'preview', url=url)
                self.assertEqual(result['lines'][0]['text'], 'Valid UTF-8 content')
                self.visit(urls[0], url.lstrip('/'))
                self.assertEqual(self.request_json(urls[0], 'recent')['results'][0]['path'], name)

    def test_preview_keeps_a_match_visible_far_into_a_long_unicode_line(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'long.txt').write_text('한' * 5000 + 'farneedle\n', encoding='utf-8')
            with self.server(root, '--bind', '127.0.0.1') as (_, urls, _):
                result = self.request_json(urls[0], 'search', mode='contents', q='farneedle')
                match = result['results'][0]
                self.assertIn('farneedle', match['text'])
                result = self.request_json(urls[0], 'preview', path='long.txt', line=1,
                                           column=match['matches'][0]['start'])
                self.assertIn('farneedle', result['lines'][0]['text'])
                self.assertEqual(result['lines'][0]['offset'], 12000)

    def test_content_search_literal_smart_case_regex_and_match_preview(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / '한글 # ?.md').write_text('Header\n한글 Needle.literal\nneedleXliteral\n', encoding='utf-8')
            (root / '.hidden.txt').write_text('Needle.literal\n')
            with self.server(root, '--bind', '127.0.0.1') as (_, urls, _):
                base = urls[0]
                result = self.request_json(base, 'search', mode='contents', q='needle.literal')
                self.assertEqual([(r['path'], r['line']) for r in result['results']], [('한글 # ?.md', 2)])
                self.assertEqual(result['results'][0]['matches'], [{'start': 7, 'end': 21}])
                self.assertIn('%23', result['results'][0]['url'])
                result = self.request_json(base, 'search', mode='contents', q='Needle')
                self.assertEqual([r['line'] for r in result['results']], [2])
                result = self.request_json(base, 'search', mode='contents', q='needle.literal', regex='1')
                self.assertEqual([r['line'] for r in result['results']], [2, 3])
                result = self.request_json(base, 'search', mode='contents', q='Needle', include='1')
                self.assertEqual(len(result['results']), 2)
                result = self.request_json(base, 'preview', path='한글 # ?.md', line=2)
                self.assertEqual(result['lines'][1], {'number': 2, 'text': '한글 Needle.literal'})
                with self.assertRaises(HTTPError) as caught:
                    self.request_json(base, 'search', mode='contents', q='[', regex='1')
                self.assertEqual(caught.exception.code, 400)
                self.assertIn('error', json.load(caught.exception))
                caught.exception.close()

    def test_missing_rg_keeps_file_finding_and_preview_available(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'readme.md').write_text('# Find me\n')
            (root / 'ignored.md').write_text('ignored')
            (root / '.gitignore').write_text('ignored.md\n')
            env = {**os.environ, 'PATH': str(root / 'empty-bin')}
            with self.server(root, '--bind', '127.0.0.1', env=env) as (_, urls, _):
                result = self.request_json(urls[0], 'search', mode='files', q='md')
                self.assertEqual([r['path'] for r in result['results']], ['readme.md'])
                result = self.request_json(urls[0], 'preview', path='readme.md')
                self.assertEqual(result['lines'][0]['text'], '# Find me')
                with self.assertRaises(HTTPError) as caught:
                    self.request_json(urls[0], 'search', mode='updated')
                self.assertEqual(caught.exception.code, 503)
                self.assertIn('clear the filename filters', json.load(caught.exception)['error'])
                caught.exception.close()
                result = self.request_json(urls[0], 'search', mode='updated', filename='')
                self.assertEqual([r['path'] for r in result['results']], ['readme.md'])
                with self.assertRaises(HTTPError) as caught:
                    self.request_json(urls[0], 'search', mode='contents', q='Find')
                self.assertEqual(caught.exception.code, 503)
                self.assertIn('requires ripgrep', json.load(caught.exception)['error'])
                caught.exception.close()

    def test_content_filename_regex_filters_match_basenames_and_compose_with_search_options(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'nested.md').mkdir()
            (root / 'empty').mkdir()
            names = ['guide.md', 'Guide.MD', 'draft.md', 'notes.txt', 'nested.md/plain.txt',
                     'nested.md/guide.md', '한글 #\n?.md', '\ufeffguide.md', os.fsdecode(b'bad-\xff.md'), '.hidden.md']
            for name in names:
                (root / name).write_text('needle.literal\nneedleXliteral\n')
            (root / '.gitignore').write_text('draft.md\n')
            (root / 'huge.bin').write_bytes(b'x' * (2 * 1024 * 1024 + 1))
            with self.server(root, '--bind', '127.0.0.1') as (_, urls, _):
                base = urls[0]
                def paths(**options):
                    result = self.request_json(base, 'search', mode='contents', q='needle.literal', **options)
                    self.assertFalse(result['truncated'])
                    return [r['path'] for r in result['results']]
                markdown = {n for n in names if n.lower().endswith('.md') and n not in ('draft.md', '.hidden.md')}
                self.assertEqual(set(paths(filename=r'\.md$')), markdown)
                self.assertEqual(set(paths(filename=r'\.md$', exclude_filename=r'^guide')), markdown - {'guide.md', 'Guide.MD', 'nested.md/guide.md'})
                self.assertEqual(paths(filename=r'^Guide\.MD$'), ['Guide.MD'])
                self.assertEqual(paths(filename='^\ufeff', exclude_filename='^draft'), ['\ufeffguide.md'])
                self.assertEqual(set(paths(filename=r'^guide\.md$')), {'Guide.MD', 'guide.md', 'nested.md/guide.md'})
                self.assertEqual(set(paths(exclude_filename=r'\.md$')), {'notes.txt', 'nested.md/plain.txt'})
                self.assertEqual(paths(filename=r'nested'), [])
                self.assertEqual(paths(filename=r'\.md$', scope='/nested.md/'), ['nested.md/guide.md'])
                self.assertEqual(set(paths(filename=r'\.md$', include='1')), markdown | {'draft.md', '.hidden.md'})
                self.assertEqual(paths(filename=r'\.md$', exclude_filename=r'\.md$'), [])
                self.assertEqual(paths(filename=r'^notes', regex='1'), ['notes.txt', 'notes.txt'])
                result = self.request_json(base, 'search', mode='contents', q='needle', filename=r'\.md$')
                self.assertEqual(result['message'], '')  # Excluded large files do not count as skipped.
                for field, label in [('filename', 'Include filenames'), ('exclude_filename', 'Exclude filenames')]:
                    for options in ({'q': 'needle'}, {'q': ''}, {'q': 'needle', 'scope': '/empty/'},
                                    {'q': 'needle', 'filename': 'no-match'}):
                        with self.subTest(field=field, options=options), self.assertRaises(HTTPError) as caught:
                            self.request_json(base, 'search', mode='contents', **{**options, field: '['})
                        self.assertEqual(caught.exception.code, 400)
                        self.assertIn(label, json.load(caught.exception)['error'])
                        caught.exception.close()
                    with self.assertRaises(HTTPError) as caught:
                        self.request_json(base, 'search', mode='contents', q='needle', **{field: 'x' * 501})
                    self.assertEqual(caught.exception.code, 400)
                    caught.exception.close()

    def test_content_filename_filter_timeout_reports_limited_results(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'readme.md').write_text('needle')
            finder = existing.helper.Finder(temp)
            with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('rg', 3)):
                result = finder.search(mode='contents', q='needle', filename=r'\.md$')
            self.assertEqual(result['results'], [])
            self.assertTrue(result['truncated'])

    def test_preview_boundaries_binary_files_and_invalid_requests(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'root'
            root.mkdir()
            (Path(temp) / 'outside.txt').write_text('outside')
            (root / 'outside-link').symlink_to('../outside.txt')
            (root / 'binary').write_bytes(b'one\x00two')
            (root / 'large.txt').write_text(('x' * 100 + '\n') * 30000)
            (root / '.git').mkdir()
            (root / '.git/config').write_text('internal')
            with self.server(root, '--bind', '127.0.0.1') as (_, urls, _):
                for path in ('../outside.txt', 'outside-link', '.git/config'):
                    with self.subTest(path=path), self.assertRaises(HTTPError) as caught:
                        self.request_json(urls[0], 'preview', path=path)
                    self.assertEqual(caught.exception.code, 400)
                    caught.exception.close()
                self.assertIn('Binary', self.request_json(urls[0], 'preview', path='binary')['message'])
                result = self.request_json(urls[0], 'preview', path='large.txt', line=15000)
                self.assertTrue(result['truncated'])
                self.assertLessEqual(len(result['lines']), 200)
                self.assertIn(15000, [r['number'] for r in result['lines']])

    def test_renderable_previews_require_supported_complete_utf8_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('한글 #?.MD', 'guide.markdown', 'page.HTML', 'page.htm', 'plain.txt'):
                (root / name).write_text('# Heading\n', encoding='utf-8')
            (root / 'large.md').write_bytes(b'# Heading\n' + b'x' * (2 * 1024 * 1024))
            (root / 'binary.html').write_bytes(b'<h1>Binary</h1>\x00')
            (root / 'invalid.md').write_bytes(b'\xff')
            (root / 'long.md').write_text('# Heading\n' + 'paragraph\n\n' * 300)
            with self.server(root, '--bind', '127.0.0.1') as (_, urls, _):
                for name, kind in (('한글 #?.MD', 'markdown'), ('guide.markdown', 'markdown'),
                                   ('page.HTML', 'html'), ('page.htm', 'html'),
                                   ('plain.txt', None), ('large.md', None),
                                   ('binary.html', None), ('invalid.md', None)):
                    with self.subTest(name=name):
                        result = self.request_json(urls[0], 'preview', path=name)
                        self.assertEqual(result.get('render_kind'), kind)
                result = self.request_json(urls[0], 'preview', path='long.md')
                self.assertTrue(result['truncated'])
                self.assertEqual(result['render_kind'], 'markdown')


if __name__ == '__main__':
    unittest.main()
