"""Exercise the recent-file CLI without an HTTP server."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'src'


class RecentCLI(unittest.TestCase):
    def find_environment(self, directory):
        """Exercise the actual find fallback without exposing fd or rg on PATH."""
        directory.mkdir(exist_ok=True)
        (directory / 'find').symlink_to(shutil.which('find'))
        return {'PATH': str(directory)}

    def run_recent(self, *arguments, cwd=None, env=None):
        return subprocess.run([sys.executable, '-B', '-m', 'html_serve.recent', *map(str, arguments)],
                              cwd=cwd, env={**os.environ, 'PYTHONPATH': str(SOURCE), **(env or {})},
                              capture_output=True, text=True, timeout=10)

    def test_home_sized_tree_finds_newest_document_after_more_than_twenty_thousand_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'a-newest').mkdir()
            (root / 'a-newest/latest.md').write_text('# Newest document')
            (root / 'z-noise').mkdir()
            for index in range(20100):
                (root / 'z-noise' / f'{index:05}.txt').touch()
            for env in ({}, self.find_environment(root / 'bin')):
                with self.subTest(env=env):
                    result = self.run_recent(root, '--json', env=env)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    report = json.loads(result.stdout)
                    self.assertEqual([entry['path'] for entry in report['results']], ['a-newest/latest.md'])
                    self.assertTrue(report['scan_complete'])
                    self.assertFalse(report['truncated'])

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
                                     str(root / 'old.md'), str(root / 'alpha.md'), str(root / 'Alpha.md')])
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
                              ((root, '--filename', '['), {}),
                              ((root, '--filename', r'\.md$'), {'PATH': ''}), ((root,), {'PATH': ''})):
                with self.subTest(args=args, env=env):
                    result = self.run_recent(*args, env=env)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, '')
                    self.assertIn('docserve-recent:', result.stderr)
            result = self.run_recent(root, '--json', env=self.find_environment(root / 'bin'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['results'][0]['path'], 'guide.md')

    def test_result_limit_preserves_global_order_and_is_a_successful_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index in range(205):
                path = root / f'{index:03}.md'
                path.touch()
                os.utime(path, (1700000000 + index, 1700000000 + index))
            result = self.run_recent(root, '--json')
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report['truncated'])
            self.assertTrue(report['scan_complete'])
            self.assertEqual(len(report['results']), 200)
            self.assertEqual(report['results'][0]['path'], '204.md')
            self.assertEqual(report['results'][-1]['path'], '005.md')
            self.assertEqual(result.stderr, '')
            result = self.run_recent(root)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(len(result.stdout.splitlines()), 200)
            self.assertEqual(result.stderr, '')
            for limit, expected in ((7, [f'{index:03}.md' for index in range(204, 197, -1)]),
                                    (0, [f'{index:03}.md' for index in range(204, -1, -1)])):
                result = self.run_recent(root, '--json', '--limit', limit)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual([entry['path'] for entry in report['results']], expected)
                self.assertEqual(report['truncated'], bool(limit))

    def test_complex_ignore_globs_finish_without_backtracking(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'nested').mkdir()
            name = 'a' * 80 + '.md'
            (root / 'nested' / name).touch()
            (root / '.gitignore').write_text('nested/' + '*a' * 12 + 'b.md\n')
            for env in ({}, self.find_environment(root / 'bin')):
                with self.subTest(env=env):
                    result = self.run_recent(root, '--json', '--timeout', '1', env=env)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual([entry['path'] for entry in json.loads(result.stdout)['results']], ['nested/' + name])

    def test_recent_docs_rules_use_parent_and_fd_ignores_and_exclude_dependencies_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'root'
            (root / 'nested').mkdir(parents=True)
            (root / 'cache').mkdir()
            (root / '.git').mkdir()
            (root / '__serve_html__').mkdir()
            (root / 'node_modules').mkdir()
            (Path(temp) / '.ignore').write_text('parent-ignored.md\n')
            (root / '.gitignore').write_text('**/draft*.md\ncache/**\nspace\\ name.md\nliteral\\*.md\n')
            (root / '.ignore').write_text('!draft-keep.md\n')
            (root / '.rgignore').write_text('nested/omit.md\n')
            (root / '.fdignore').write_text('fd-ignored.md\npriority.md\n')
            (root / 'nested/.gitignore').write_text('!priority.md\n')
            names = ['nested/view.MD', 'nested/draft-keep.md', 'nested/draft-drop.md', 'nested/omit.md',
                     'cache/secret.md', 'space name.md', 'literal*.md', '한글 #\n?.md',
                     'fd-ignored.md', 'parent-ignored.md', 'node_modules/dependency.md', 'nested/priority.md',
                     '.hidden.md', '.git/private.md', '__serve_html__/private.md']
            for name in names:
                (root / name).write_text('document')
                os.utime(root / name, (1700000000, 1700000000))
            (root / 'alias.md').symlink_to('nested/view.MD')
            (root / 'linked-directory.md').symlink_to('nested')
            (Path(temp) / 'outside.md').touch()
            (root / 'outside.md').symlink_to('../outside.md')
            expected = {'nested/view.MD', 'nested/draft-keep.md', 'nested/omit.md', '한글 #\n?.md',
                        '__serve_html__/private.md'}
            fallback = self.find_environment(Path(temp) / 'bin')
            for include in (False, True):
                reports = []
                for env in ({}, fallback):
                    result = self.run_recent(root, '--json', *(['--include'] if include else []), env=env)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    reports.append(json.loads(result.stdout))
                self.assertEqual(reports[0], reports[1])
                paths = {entry['path'] for entry in reports[0]['results']}
                if include:
                    self.assertTrue(expected | {'.hidden.md', 'cache/secret.md', 'nested/draft-drop.md',
                                                'fd-ignored.md', 'parent-ignored.md'} <= paths)
                    self.assertFalse({'.git/private.md', 'node_modules/dependency.md', 'alias.md',
                                      'outside.md', 'linked-directory.md'} & paths)
                else:
                    self.assertEqual(paths, expected)

    def test_native_global_ignores_and_non_utf8_extensions_follow_fd(self):
        if not (shutil.which('fd') or shutil.which('fdfind')):
            self.skipTest('fd is not installed')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'root'
            root.mkdir()
            config = Path(temp) / 'config'
            (config / 'fd').mkdir(parents=True)
            (config / 'fd/ignore').write_text('global.md\n')
            unusual = os.fsdecode(b'bad-\xff.md')
            for name in ('guide.md', 'global.md', unusual):
                (root / name).touch()
            env = {'XDG_CONFIG_HOME': str(config)}
            result = self.run_recent(root, '--json', env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([entry['path'] for entry in json.loads(result.stdout)['results']], ['guide.md'])
            result = self.run_recent(root, '--json', '--filename', '', env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({entry['path'] for entry in json.loads(result.stdout)['results']}, {'guide.md', unusual})
            result = self.run_recent(root, '--json', env=self.find_environment(Path(temp) / 'bin'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({entry['path'] for entry in json.loads(result.stdout)['results']},
                             {'guide.md', 'global.md', unusual})

    def test_explicit_search_root_is_traversed_even_when_its_parent_ignores_it(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp)
            root = parent / 'docs'
            (root / 'nested').mkdir(parents=True)
            (parent / '.gitignore').write_text('docs/\n/parent-only.md\n')
            (root / '.gitignore').write_text('/root-only.md\n')
            for name in ('guide.md', 'root-only.md', 'nested/root-only.md', 'parent-only.md'):
                (root / name).touch()
            for env in ({}, self.find_environment(parent / 'bin')):
                with self.subTest(env=env):
                    result = self.run_recent(root, '--json', env=env)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual({entry['path'] for entry in json.loads(result.stdout)['results']},
                                     {'guide.md', 'nested/root-only.md', 'parent-only.md'})

    def test_find_reports_patterns_that_need_native_fd(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'guide.md').touch()
            (root / '.fdignore').write_text('draft{1,2}.md\n')
            result = self.run_recent(root, '--json', env=self.find_environment(root / 'bin'))
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, '')
            self.assertIn('Extended ignore patterns require fd', result.stderr)

    def test_timeout_kills_scanner_and_does_not_emit_a_misleading_partial_ranking(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'guide.md').touch()
            executable = root / 'fd'
            pid = root / 'scanner.pid'
            for close_stdout in (False, True):
                with self.subTest(close_stdout=close_stdout):
                    executable.write_text(f'#!{sys.executable}\nimport os, time\n'
                                          f'open({str(pid)!r}, "w").write(str(os.getpid()))\n'
                                          'print("guide.md\\0", end="", flush=True)\n'
                                          + ('os.close(1)\n' if close_stdout else '') + 'time.sleep(60)\n')
                    executable.chmod(0o755)
                    result = self.run_recent(root, '--json', '--timeout', '0.2', env={'PATH': str(root)})
                    self.assertEqual(result.returncode, 3)
                    report = json.loads(result.stdout)
                    self.assertEqual(report['results'], [])
                    self.assertFalse(report['scan_complete'])
                    self.assertTrue(report['truncated'])
                    self.assertIn('Increase --timeout', result.stderr)
                    with self.assertRaises(ProcessLookupError):
                        os.kill(int(pid.read_text()), 0)

    def test_find_timeout_is_not_silently_reported_as_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'unrelated.txt').touch()
            result = self.run_recent(root, '--json', '--timeout', '0.000001',
                                     env=self.find_environment(root / 'bin'))
            self.assertEqual(result.returncode, 3)
            report = json.loads(result.stdout)
            self.assertFalse(report['scan_complete'])
            self.assertEqual(report['results'], [])

    def test_invalid_limits_and_scanner_errors_do_not_look_like_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for option, value in (('--limit', '-1'), ('--limit', 'no'), ('--timeout', '0'),
                                  ('--timeout', 'nan'), ('--timeout', 'inf')):
                with self.subTest(option=option, value=value):
                    result = self.run_recent(root, option, value)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, '')
            executable = root / 'fd'
            (root / 'guide.md').touch()
            executable.write_text(f'#!{sys.executable}\nimport sys\n'
                                  'print("guide.md\\0", end="", flush=True)\n'
                                  'print("scanner failure", file=sys.stderr)\nsys.exit(2)\n')
            executable.chmod(0o755)
            result = self.run_recent(root, '--json', env={'PATH': str(root)})
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, '')
            self.assertIn('scanner failure', result.stderr)
