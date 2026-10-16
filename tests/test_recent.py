"""Exercise the recent-file CLI without an HTTP server."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'src'


class RecentCLI(unittest.TestCase):
    def run_recent(self, *arguments, cwd=None, env=None):
        return subprocess.run([sys.executable, '-B', '-m', 'html_serve.recent', *map(str, arguments)],
                              cwd=cwd, env={**os.environ, 'PYTHONPATH': str(SOURCE), **(env or {})},
                              capture_output=True, text=True, timeout=10)

    def test_default_directory_is_exact_and_text_paths_are_escaped_and_sorted(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            (parent / '.git').mkdir()
            (parent / 'outside.md').touch()
            root = parent / 'docs'
            root.mkdir()
            names = ['old.md', 'new\nline\t\\.HTML', 'Alpha.md', 'alpha.md', 'skip.txt']
            for name in names:
                (root / name).touch()
                stamp = 1700000000_000000000 + (1 if name.startswith('new') else 0)
                os.utime(root / name, ns=(stamp, stamp))
            result = self.run_recent(cwd=root)
            self.assertEqual(result.returncode, 0, result.stderr)
            paths = [line.split('  ', 1)[1] for line in result.stdout.splitlines()]
            self.assertEqual(paths, [str(root) + '/new\\nline\\t\\\\.HTML',
                                     str(root / 'Alpha.md'), str(root / 'alpha.md'), str(root / 'old.md')])
            self.assertEqual(result.stderr, '')

    def test_json_uses_finder_filters_and_preserves_relative_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'nested').mkdir()
            for name in ('guide.md', 'nested/new.HTML', 'nested/draft.md', 'notes.txt', '.hidden.md'):
                (root / name).touch()
            (root / '.gitignore').write_text('draft.md\n')
            result = self.run_recent(root, '--json')
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['root'], str(root.resolve()))
            self.assertEqual({entry['path'] for entry in report['results']}, {'guide.md', 'nested/new.HTML'})
            self.assertFalse(report['truncated'])
            self.assertTrue(all(entry['modified_at'].endswith('+00:00') for entry in report['results']))
            result = self.run_recent(root, '--json', '--include', '--query', 'nested',
                                     '--filename', '', '--exclude-filename', '^draft')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([entry['path'] for entry in json.loads(result.stdout)['results']], ['nested/new.HTML'])
            result = self.run_recent(root, '--json', '--include', '--filename', r'^\.hidden')
            self.assertEqual([entry['path'] for entry in json.loads(result.stdout)['results']], ['.hidden.md'])

    def test_errors_leave_stdout_empty_and_clear_filters_work_without_rg(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'guide.md').touch()
            for args, env in (((root / 'missing',), {}), ((root / 'guide.md',), {}),
                              ((root, '--filename', '['), {}), ((root,), {'PATH': ''})):
                with self.subTest(args=args, env=env):
                    result = self.run_recent(*args, env=env)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, '')
                    self.assertIn('docserve-recent:', result.stderr)
            result = self.run_recent(root, '--filename', '', '--json', env={'PATH': ''})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['results'][0]['path'], 'guide.md')

    def test_limited_results_have_a_distinct_exit_code_in_both_formats(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index in range(205):
                path = root / f'{index:03}.md'
                path.touch()
                os.utime(path, (1700000000 + index, 1700000000 + index))
            result = self.run_recent(root, '--json')
            self.assertEqual(result.returncode, 3, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report['truncated'])
            self.assertEqual(len(report['results']), 200)
            self.assertEqual(report['results'][0]['path'], '204.md')
            self.assertEqual(report['results'][-1]['path'], '005.md')
            self.assertEqual(result.stderr, '')
            result = self.run_recent(root)
            self.assertEqual(result.returncode, 3)
            self.assertEqual(len(result.stdout.splitlines()), 200)
            self.assertIn('scan may be incomplete', result.stderr)
