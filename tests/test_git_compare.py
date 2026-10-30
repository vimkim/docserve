import os
from pathlib import Path
import subprocess
import time
from unittest.mock import patch
import tempfile
import unittest

from html_serve.git_compare import GitError, blob, git, history
from html_serve.paths import DocumentRoots


class GitComparisonTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run_git('init', '-q')
        self.run_git('config', 'user.email', 'test@example.com')
        self.run_git('config', 'user.name', 'Test')
        self.path = self.root / 'a #?.md'
        self.path.write_text('first')
        self.commit('first')
        self.first = self.run_git('rev-parse', 'HEAD').strip()
        self.run_git('mv', self.path.name, 'renamed #?.md')
        self.path = self.root / 'renamed #?.md'
        self.commit('rename')
        self.second = self.run_git('rev-parse', 'HEAD').strip()
        self.path.write_text('third')
        self.commit('third')
        self.third = self.run_git('rev-parse', 'HEAD').strip()
        self.roots = DocumentRoots(self.root)

    def run_git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True)

    def commit(self, message):
        self.run_git('add', '-A')
        self.run_git('commit', '-qm', message)

    def history(self):
        return history(self.path, '/renamed%20%23%3F.md', self.roots)

    def test_clean_dirty_and_historical_paths(self):
        before = self.run_git('status', '--porcelain=v1')
        result = self.history()
        self.assertEqual(result.default, self.second)
        self.assertEqual([r.commit for r in result.revisions], [self.third, self.second, self.first])
        self.assertEqual(result.revisions[-1].path, 'a #?.md')
        self.assertEqual(git(self.root, 'cat-file', 'blob', result.revisions[-1].blob), b'first')
        self.path.write_text('working')
        self.assertEqual(self.history().default, self.third)
        self.assertEqual(before, '')
        self.assertEqual(self.run_git('status', '--porcelain=v1').strip(), 'M "renamed #?.md"')

    def test_merge_resolution_is_previous_revision(self):
        branch = self.run_git('branch', '--show-current').strip()
        self.run_git('checkout', '-qb', 'side')
        self.path.write_text('side')
        self.commit('side')
        self.run_git('checkout', '-q', branch)
        self.path.write_text('main')
        self.commit('main')
        subprocess.run(['git', '-C', str(self.root), 'merge', 'side'], capture_output=True)
        self.path.write_text('resolution')
        self.commit('resolution')
        merge = self.run_git('rev-parse', 'HEAD').strip()
        self.path.write_text('later')
        self.commit('later')
        self.assertEqual(self.history().default, merge)

    def test_git_timeout_after_stdout_closes(self):
        fake = self.root / 'bin'
        fake.mkdir()
        executable = fake / 'git'
        executable.write_text('#!/bin/sh\nexec 1>&-\nsleep 5\n')
        executable.chmod(0o755)
        with patch.dict(os.environ, {'PATH': str(fake) + os.pathsep + os.environ['PATH']}):
            with self.assertRaisesRegex(GitError, 'timed out'):
                git(self.root, 'status', deadline=time.monotonic() + 0.2)

    def test_invalid_tree_path_and_revision(self):
        for revision, path in [('HEAD', self.path.name), (self.third, '../outside'), (self.third, 'missing')]:
            with self.assertRaises(GitError):
                blob(self.root, revision, path)

    def test_untracked_and_initial_clean(self):
        self.path = self.root / 'new.md'
        self.path.write_text('new')
        self.assertIsNone(self.history().default)
        self.commit('new')
        self.assertIsNone(self.history().default)
        self.assertIn('previous', self.history().reason)
