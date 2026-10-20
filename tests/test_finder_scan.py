"""Exercise native Finder scans, complete ranking, and filesystem-root exclusions."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from urllib.request import ProxyHandler, build_opener

import test_serve_html as existing


class NativeFinderTests(unittest.TestCase):
    server = existing.ServeHTML.server

    def test_all_find_modes_reach_paths_after_twenty_thousand_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'a-target/empty').mkdir(parents=True)
            (root / 'a-target/RESULTS.md').write_text('unique content needle\n')
            (root / 'z-noise').mkdir()
            for index in range(20100):
                (root / 'z-noise' / f'{index:05}.txt').touch()
            client = build_opener(ProxyHandler({}))
            with self.server(root, '--bind', '127.0.0.1') as (_, urls, _):
                for mode, query, expected in (
                    ('files', 'a-target/RESULTS.md', 'a-target/RESULTS.md'),
                    ('directories', 'a-target/empty', 'a-target/empty'),
                    ('contents', 'unique content needle', 'a-target/RESULTS.md'),
                ):
                    with self.subTest(mode=mode):
                        params = urlencode({'mode': mode, 'q': query, 'filename': r'\.md$'})
                        with client.open(urls[0] + '__serve_html__/api/search?' + params) as response:
                            report = json.load(response)
                        self.assertEqual([r['path'] for r in report['results']], [expected])
                        self.assertFalse(report['truncated'])

    def test_root_ignore_file_excludes_system_trees_and_preserves_nested_names(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            names = ['var/drop.txt', 'usr/drop.txt', 'proc/drop.txt', 'sys/drop.txt', 'dev/drop.txt',
                     'home/reader/usr/keep.txt', 'home/reader/var/keep.txt', 'home/reader/keep.txt']
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            popen = subprocess.Popen

            def simulated_filesystem(command, **kwargs):
                # Run the real scanner against a miniature / without modifying the host tree.
                return popen(command, **{**kwargs, 'cwd': root})

            finder = existing.helper.Finder('/')
            with patch('subprocess.Popen', side_effect=simulated_filesystem):
                for include in (False, True):
                    with self.subTest(include=include):
                        report = finder.search(mode='files', include=include)
                        self.assertEqual({r['path'] for r in report['results']}, set(names[5:]))
                        self.assertFalse(report['truncated'])
                report = finder.search(mode='files', scope='/usr/')
                self.assertEqual([r['path'] for r in report['results']], ['usr/drop.txt'])

    def test_scan_timeout_discards_partial_ranking_and_reaps_fd(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pid = root / 'scanner.pid'
            executable = root / 'fd'
            executable.write_text(
                f'#!{sys.executable}\nimport os, time\n'
                f'open({str(pid)!r}, "w").write(str(os.getpid()))\n'
                'os.write(1, b"early.txt\\0")\ntime.sleep(60)\n')
            executable.chmod(0o755)
            with patch.dict(os.environ, {'PATH': str(root)}):
                result = existing.helper.Finder(root).search(mode='files', timeout=0.2)
            self.assertEqual(result['results'], [])
            self.assertTrue(result['truncated'])
            self.assertFalse(result['scan_complete'])
            self.assertIn('0.2-second', result['message'])
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pid.read_text()), 0)

    def test_missing_fd_reports_dependency_and_fdfind_is_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'RESULTS.md').write_text('result')
            tools = root / '.bin'
            tools.mkdir()
            finder = existing.helper.Finder(root)
            with patch.dict(os.environ, {'PATH': str(tools)}):
                with self.assertRaisesRegex(existing.helper.FinderError, 'requires fd') as caught:
                    finder.search(mode='files')
                self.assertEqual(caught.exception.status, 503)
                self.assertTrue(finder.preview('RESULTS.md')['lines'])
            (tools / 'fdfind').symlink_to(shutil.which('fd') or shutil.which('fdfind'))
            with patch.dict(os.environ, {'PATH': str(tools)}):
                report = finder.search(mode='files', q='RESULTS.md')
            self.assertEqual([r['path'] for r in report['results']], ['RESULTS.md'])

    def test_scanner_errors_do_not_return_partial_results(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            executable = root / 'fd'
            for body, message in (
                ('import os\nos.write(1, b"early.txt\\0")\n'
                 'os.write(2, b"scanner fixture failure")\nraise SystemExit(2)\n', 'scanner fixture failure'),
                ('import os\nos.write(1, b"unfinished filename")\n', 'incomplete filename'),
            ):
                with self.subTest(message=message):
                    executable.write_text(f'#!{sys.executable}\n' + body)
                    executable.chmod(0o755)
                    with patch.dict(os.environ, {'PATH': str(root)}):
                        with self.assertRaisesRegex(existing.helper.FinderError, message):
                            existing.helper.Finder(root).search(mode='files')

    def test_native_path_filter_preserves_fuzzy_casefold_and_newline_matches(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cases = [('ssreport', 'ß-report.md'), ('ffi notes', 'ﬃ-notes.md'),
                     ('ab', 'a\nb.md'), ('docsrev', 'docs/design-review.md'),
                     ('kguide', 'K-guide.md')]
            for _, name in cases:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            finder = existing.helper.Finder(root)
            for query, expected in cases:
                with self.subTest(query=query):
                    report = finder.search(mode='files', q=query)
                    self.assertEqual([r['path'] for r in report['results']], [expected])
            self.assertEqual(finder.search(mode='files', q='\x00')['results'], [])

    def test_result_limit_selects_best_matches_after_a_complete_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'report.md').touch()
            (root / 'noise').mkdir()
            for index in range(250):
                (root / 'noise' / f'long-prefix-{index:03}-report.md').touch()
            report = existing.helper.Finder(root).search(mode='files', q='report')
            self.assertEqual(len(report['results']), 200)
            self.assertEqual(report['results'][0]['path'], 'report.md')
            self.assertTrue(report['truncated'])
            self.assertTrue(report['scan_complete'])


if __name__ == '__main__':
    unittest.main()
