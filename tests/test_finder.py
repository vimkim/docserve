"""Verify search and recent visits through a live HTTP server."""

import json
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import unittest
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
                    self.request_json(urls[0], 'search', mode='contents', q='Find')
                self.assertEqual(caught.exception.code, 503)
                self.assertIn('requires ripgrep', json.load(caught.exception)['error'])
                caught.exception.close()

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


if __name__ == '__main__':
    unittest.main()
