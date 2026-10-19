"""Exercise absolute filesystem links through the live HTTP server."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

import test_serve_html as existing


class AbsoluteLinkTests(unittest.TestCase):
    server = existing.ServeHTML.server

    def test_project_absolute_links_redirect_and_existing_web_paths_take_precedence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'root'
            (root / 'docs').mkdir(parents=True)
            name = '한글 #?%2F "<tag>\n.md'
            document = root / 'docs' / name
            document.write_text('# Absolute link')
            alias = Path(temp) / 'alias'
            alias.symlink_to(root, target_is_directory=True)
            client = build_opener(ProxyHandler({}))
            with self.server(alias, '--bind', '127.0.0.1') as (_, urls, _):
                for absolute in (document, alias / 'docs' / name):
                    url = urls[0].rstrip('/') + quote(str(absolute), safe='/') + '?raw=1&keep=%20&other=%2B'
                    with client.open(url) as response:
                        self.assertEqual(response.url, urls[0] + 'docs/' + quote(name, safe='')
                                         + '?raw=1&keep=%20&other=%2B')
                        self.assertEqual(response.read(), b'# Absolute link')
                    with client.open(Request(url, method='HEAD')) as response:
                        self.assertEqual(response.read(), b'')
                        self.assertEqual(response.headers['Content-Length'], str(len(b'# Absolute link')))
                # A real website path retains priority over the filesystem interpretation.
                collision = root / str(document).lstrip('/')
                collision.parent.mkdir(parents=True)
                collision.write_text('# Web path')
                with client.open(urls[0].rstrip('/') + quote(str(document), safe='/') + '?raw=1') as response:
                    self.assertEqual(response.read(), b'# Web path')

    def test_extra_roots_serve_documents_assets_and_directory_navigation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'root'
            root.mkdir()
            extra = Path(temp) / 'extra 한글 #?'
            (extra / 'docs').mkdir(parents=True)
            (extra / 'docs/page.md').write_text('# Extra document\n\n![Figure](figure.svg)')
            html = b'<h1>Extra HTML</h1><script>window.original = true</script>'
            (extra / 'docs/page.html').write_bytes(html)
            (extra / 'docs/figure.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
            second = Path(temp) / 'second'
            second.mkdir()
            (second / 'note.txt').write_text('Second allowed directory')
            client = build_opener(ProxyHandler({}))
            with self.server(root, '--bind', '127.0.0.1', '--allow-root', str(extra),
                             '--allow-root', str(second)) as (_, urls, _):
                base = urls[0].rstrip('/')
                with client.open(base + quote(str(extra / 'docs/page.md'), safe='/')) as response:
                    mounted = urlsplit(response.url).path
                    self.assertTrue(mounted.startswith('/__docserve_fs__/'))
                    self.assertIn(b'id="content"', response.read())
                directory = mounted.rsplit('/', 1)[0] + '/'
                mount_root = directory.removesuffix('docs/')
                with client.open(base + directory + 'figure.svg') as response:
                    self.assertEqual(response.headers.get_content_type(), 'image/svg+xml')
                for suffix in ('', '?__docserve_standalone=1'):
                    with client.open(base + directory + 'page.html' + suffix) as response:
                        self.assertEqual(response.read(), html)
                with client.open(Request(base + directory + 'page.html', headers={'Accept': 'text/html'})) as response:
                    self.assertIn(b'data-docserve-html-viewer', response.read())
                with client.open(base + quote(str(second / 'note.txt'), safe='/')) as response:
                    self.assertEqual(response.read(), b'Second allowed directory')
                    self.assertNotEqual(urlsplit(response.url).path.split('/')[2], mounted.split('/')[2])
                for path, expected_parent in ((mount_root, None), (directory, mount_root)):
                    with client.open(base + '/__serve_html__/api/directory?' + urlencode({'url': path})) as response:
                        listing = json.load(response)
                    self.assertEqual(listing['parent'], expected_parent)
                    self.assertTrue(all(entry['url'].startswith(path) for entry in listing['entries']))
                with client.open(base + mount_root) as response:
                    self.assertNotIn('href="../', response.read().decode())

    def test_absolute_access_rejects_unconfigured_paths_traversal_and_symlink_escapes(self):
        with tempfile.TemporaryDirectory() as temp:
            root, extra, outside = (Path(temp) / name for name in ('root', 'extra', 'extra-other'))
            for directory in (root, extra, outside):
                directory.mkdir()
            (extra / 'safe.txt').write_text('Allowed')
            (outside / 'secret.txt').write_text('Secret bytes must not be served')
            (extra / 'escape').symlink_to(outside, target_is_directory=True)
            (extra / 'inside.txt').symlink_to(extra / 'safe.txt')
            (root / 'escape').symlink_to(outside, target_is_directory=True)
            client = build_opener(ProxyHandler({}))
            with self.server(root, '--bind', '127.0.0.1', '--allow-root', str(extra)) as (_, urls, _):
                base = urls[0].rstrip('/')
                with client.open(base + quote(str(extra / 'inside.txt'), safe='/')) as response:
                    mount = urlsplit(response.url).path.rsplit('/', 1)[0] + '/'
                    self.assertEqual(response.read(), b'Allowed')
                for path, status in (
                    (str(outside / 'secret.txt'), 404),
                    (str(extra / 'escape/secret.txt'), 403),
                    (str(root / 'escape/secret.txt'), 403),
                    (mount + 'escape/secret.txt', 403),
                    (mount.replace('__docserve_fs__', '%5f_docserve_fs__') + 'escape/secret.txt', 403),
                    (mount + '%2e%2e/extra-other/secret.txt', 400),
                    (mount + '%00.txt', 400),
                    ('/__docserve_fs__/unknown/secret.txt', 404),
                    ('/__docserve_fs__/', 404),
                ):
                    with self.subTest(path=path), self.assertRaises(HTTPError) as caught:
                        client.open(base + quote(path, safe='/%'))
                    self.assertEqual(caught.exception.code, status)
                    body = caught.exception.read().decode()
                    self.assertNotIn('Secret bytes must not be served', body)
                    if path == str(outside / 'secret.txt'):
                        self.assertIn('--allow-root', body)
                        self.assertIn(str(outside), body)
                    caught.exception.close()
                # Replacing a previously safe symlink cannot reuse its mounted URL to escape.
                (extra / 'inside.txt').unlink()
                (extra / 'inside.txt').symlink_to(outside / 'secret.txt')
                with self.assertRaises(HTTPError) as caught:
                    client.open(base + mount + 'inside.txt')
                self.assertEqual(caught.exception.code, 403)
                caught.exception.close()
                for endpoint, parameters in (
                    ('path', {'url': mount + 'escape/secret.txt'}),
                    ('directory', {'url': mount + 'escape/'}),
                    ('preview', {'url': mount + 'escape/secret.txt'}),
                    ('search', {'scope_url': mount + 'escape/', 'mode': 'files'}),
                ):
                    with self.subTest(endpoint=endpoint), self.assertRaises(HTTPError) as caught:
                        client.open(base + '/__serve_html__/api/' + endpoint + '?' + urlencode(parameters))
                    self.assertEqual(caught.exception.code, 403)
                    caught.exception.close()
                # Ordinary direct links keep the documented pre-existing symlink behavior.
                with client.open(base + '/escape/secret.txt') as response:
                    self.assertEqual(response.read(), b'Secret bytes must not be served')

    def test_mounted_finder_previews_and_history_keep_their_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root, extra = Path(temp) / 'root', Path(temp) / 'extra'
            root.mkdir()
            (root / 'main.md').write_text('# Main')
            (extra / 'nested').mkdir(parents=True)
            (extra / 'other.md').write_text('# Other')
            (extra / 'nested/note.md').write_text('# Mounted note')
            client = build_opener(ProxyHandler({}))
            with self.server(root, '--bind', '127.0.0.1', '--allow-root', str(extra)) as (_, urls, _):
                base = urls[0].rstrip('/')
                with client.open(Request(base + str(extra / 'nested/note.md'),
                                         headers={'Sec-Fetch-Dest': 'document'})) as response:
                    mounted = urlsplit(response.url).path
                    response.read()
                mount = mounted.split('nested/')[0]

                def api(endpoint, **parameters):
                    with client.open(base + '/__serve_html__/api/' + endpoint + '?' + urlencode(parameters)) as response:
                        return json.load(response)

                search = api('search', scope_url=mount + 'nested/', root='1', mode='files')
                self.assertEqual({item['path'] for item in search['results']}, {'nested/note.md', 'other.md'})
                self.assertTrue(all(item['url'].startswith(mount) for item in search['results']))
                current = api('search', scope_url=mount + 'nested/', mode='files')
                self.assertEqual([item['path'] for item in current['results']], ['nested/note.md'])
                self.assertEqual(api('preview', url=mounted)['lines'][0]['text'], '# Mounted note')
                self.assertEqual(api('path', url=mounted)['server_path'], str(extra / 'nested/note.md'))
                self.assertEqual(api('recent')['results'], [])
                self.assertEqual(api('recent', scope_url=mount)['results'][0]['url'], mounted)
                request = Request(base + '/__serve_html__/api/visit', data=json.dumps({'url': mount + 'other.md'}).encode(),
                                  headers={'Content-Type': 'application/json'})
                with client.open(request) as response:
                    self.assertTrue(json.load(response)['recorded'])
                self.assertEqual(api('recent', scope_url=mount)['results'][0]['url'], mount + 'other.md')
                self.assertEqual(api('recent')['results'], [])

    def test_duplicate_and_nested_roots_have_stable_urls_and_validate_cli_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root, extra = Path(temp) / 'root', Path(temp) / 'extra'
            root.mkdir()
            (extra / 'nested').mkdir(parents=True)
            (extra / 'nested/note.txt').write_text('Nested root')
            alias = Path(temp) / 'alias'
            alias.symlink_to(extra, target_is_directory=True)
            client = build_opener(ProxyHandler({}))
            destinations = []
            for allowed in ((extra / 'nested', extra, alias, root), (extra, extra / 'nested')):
                arguments = [item for directory in allowed for item in ('--allow-root', str(directory))]
                with self.server(root, '--bind', '127.0.0.1', *arguments) as (_, urls, _):
                    with client.open(urls[0].rstrip('/') + str(extra / 'nested/note.txt')) as response:
                        destinations.append(urlsplit(response.url).path)
            self.assertEqual(destinations[0], destinations[1])
            self.assertTrue(destinations[0].endswith('/note.txt'))
            for invalid in (extra / 'missing', extra / 'nested/note.txt'):
                result = subprocess.run([sys.executable, str(existing.SCRIPT), '--bind', '127.0.0.1',
                                         '-d', str(root), '--allow-root', str(invalid)], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
                self.assertIn('--allow-root requires an existing directory', result.stderr)


if __name__ == '__main__':
    unittest.main()
