"""Verify document routing, directory browsing, and explicit framed visits."""

import json
import os
from html import escape, unescape
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import ProxyHandler, Request, build_opener

import test_serve_html as existing


class DocumentNavigationTests(unittest.TestCase):
    server = existing.ServeHTML.server

    def test_html_navigation_shell_preserves_original_responses_and_head(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            name = '한글 <tag> # "?.HTML'
            source = b'<!doctype html><title>Original</title><script>window.works = true</script>'
            (root / name).write_bytes(source)
            (root / 'style.css').write_bytes(b'body { color: navy; }')
            (root / 'index.htm').write_bytes(source)
            client = build_opener(ProxyHandler({}))
            with self.server(root, '--bind', '127.0.0.1') as (_, urls, _):
                url = urls[0] + quote(name, safe='') + '?keep=%20&other=%2B'
                for headers in ({}, {'Sec-Fetch-Dest': 'iframe', 'Accept': 'text/html'},
                                {'Sec-Fetch-Dest': 'empty', 'Accept': '*/*'}):
                    with client.open(Request(url, headers=headers)) as response:
                        self.assertEqual(response.read(), source)
                        self.assertEqual(response.headers['Vary'], 'Sec-Fetch-Dest, Accept')
                for headers in ({'Sec-Fetch-Dest': 'document', 'Accept': 'text/html'},
                                {'Accept': 'text/html'}, {'Accept': 'text/html', 'Referer': 'http://['}):
                    with client.open(Request(url, headers=headers)) as response:
                        shell = response.read()
                        self.assertIn(b'data-docserve-html-viewer', shell)
                        self.assertIn(b'data-docserve-document', shell)
                        self.assertIn(b'keep=%20&amp;other=%2B&amp;__docserve_standalone=1', shell)
                        self.assertNotIn(b'<tag>', shell)
                    with client.open(Request(url, headers=headers, method='HEAD')) as response:
                        self.assertEqual(int(response.headers['Content-Length']), len(shell))
                        self.assertEqual(response.read(), b'')
                    with client.open(Request(url + '&__docserve_standalone=1', headers=headers)) as response:
                        self.assertEqual(response.read(), source)
                with client.open(Request(urls[0] + 'index.htm', headers={'Accept': 'text/html'})) as response:
                    self.assertIn(b'data-docserve-html-viewer', response.read())
                with client.open(urls[0] + 'style.css') as response:
                    self.assertEqual(response.read(), b'body { color: navy; }')
                with self.assertRaises(HTTPError) as caught:
                    client.open(Request(urls[0] + 'missing.html', headers={'Accept': 'text/html'}))
                self.assertEqual(caught.exception.code, 404)
                caught.exception.close()

    def test_directory_api_lists_immediate_entries_without_recording_visits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'root'
            (root / 'docs/nested').mkdir(parents=True)
            name = '한글 <tag> #?.html'
            (root / 'docs' / name).write_text('original')
            (root / 'docs/.hidden').write_text('hidden')
            (root / 'docs/broken').symlink_to('missing')
            outside = Path(temp) / 'outside'
            outside.mkdir()
            (outside / 'direct.txt').write_text('direct links follow symlinks')
            (root / 'docs/linked').symlink_to(outside, target_is_directory=True)
            client = build_opener(ProxyHandler({}))
            env = {**os.environ, 'XDG_CACHE_HOME': str(Path(temp) / 'cache')}
            with self.server(root, '--bind', '127.0.0.1', env=env) as (_, urls, _):
                base = urls[0] + '__serve_html__/api/'

                def directory(url):
                    with client.open(base + 'directory?' + urlencode({'url': url})) as response:
                        self.assertEqual(response.headers['Cache-Control'], 'no-store')
                        return json.load(response)

                self.assertIsNone(directory('/')['parent'])
                data = directory('/docs/')
                self.assertEqual((data['url'], data['path'], data['parent']), ('/docs/', 'docs', '/'))
                self.assertEqual([entry['name'] for entry in data['entries']], ['linked', 'nested', '.hidden', 'broken', name])
                special = data['entries'][-1]
                self.assertEqual(special['url'], '/docs/' + quote(name, safe=''))
                self.assertEqual(special['kind'], 'file')
                self.assertEqual(special['server_path'], str(root / 'docs' / name))
                self.assertTrue(data['entries'][0]['symlink'])
                self.assertEqual(directory('/docs/linked/')['entries'][0]['name'], 'direct.txt')
                self.assertEqual(directory('/docs/nested/')['entries'], [])
                for invalid in ('../outside/', '/docs/../', '/%2e%2e/', '/%00/',
                                'http://elsewhere/docs/', '//elsewhere/docs/', '/__serve_html__/'):
                    with self.subTest(invalid=invalid), self.assertRaises(HTTPError) as caught:
                        directory(invalid)
                    self.assertEqual(caught.exception.code, 400)
                    caught.exception.close()
                with self.assertRaises(HTTPError) as caught:
                    directory('/missing/')
                self.assertEqual(caught.exception.code, 404)
                caught.exception.close()
                with client.open(base + 'recent') as response:
                    self.assertEqual(json.load(response)['results'], [])

    def test_copy_paths_preserve_server_names_and_validate_document_urls(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'root & "한글'
            (root / 'docs').mkdir(parents=True)
            name = '한글 <tag> # "?%2F\r\n.md'
            target = root / 'docs' / name
            target.write_text('# Original')
            (root / 'alias').symlink_to(root / 'docs', target_is_directory=True)
            client = build_opener(ProxyHandler({}))
            env = {**os.environ, 'XDG_CACHE_HOME': str(Path(temp) / 'cache')}
            with self.server(root, '--bind', '127.0.0.1', env=env) as (_, urls, _):
                base = urls[0] + '__serve_html__/api/'

                def server_path(url):
                    with client.open(base + 'path?' + urlencode({'url': url})) as response:
                        self.assertEqual(response.headers['Cache-Control'], 'no-store')
                        return json.load(response)['server_path']

                self.assertEqual(server_path('/'), str(root))
                self.assertEqual(server_path('/docs/'), str(root / 'docs'))
                self.assertEqual(server_path('/docs/' + quote(name, safe='') + '?raw=1#heading'), str(target))
                self.assertEqual(server_path('/alias/' + quote(name, safe='')), str(root / 'alias' / name))
                with client.open(urls[0] + 'docs/?sort=title') as response:
                    listing = response.read().decode()
                encoded = escape(str(target), quote=True).replace('\r', '&#13;')
                self.assertIn(f'data-copy-path="{encoded}"', listing)
                self.assertEqual(unescape(encoded), str(target))
                self.assertNotIn('<tag>', listing)
                for invalid in ('../outside', '/docs/../', '/%2e%2e/', '/%00/',
                                'http://elsewhere/docs/', '//elsewhere/docs/', '/__serve_html__/viewer.js'):
                    with self.subTest(invalid=invalid), self.assertRaises(HTTPError) as caught:
                        server_path(invalid)
                    self.assertEqual(caught.exception.code, 400)
                    caught.exception.close()
                with self.assertRaises(HTTPError) as caught:
                    server_path('/missing')
                self.assertEqual(caught.exception.code, 404)
                caught.exception.close()
                with client.open(base + 'recent') as response:
                    self.assertEqual(json.load(response)['results'], [])

    def test_framed_visits_require_an_explicit_valid_document(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'root'
            (root / 'docs').mkdir(parents=True)
            (root / 'docs/page.html').write_text('<h1>Page</h1>')
            env = {**os.environ, 'XDG_CACHE_HOME': str(Path(temp) / 'cache')}
            client = build_opener(ProxyHandler({}))
            with self.server(root, '--bind', '127.0.0.1', env=env) as (_, urls, _):
                base = urls[0]
                with client.open(Request(base + 'docs/page.html', headers={'Sec-Fetch-Dest': 'iframe', 'Accept': 'text/html'})) as response:
                    response.read()
                for url, referrer in (('docs/page.html?__docserve_standalone=1', base),
                                      ('docs/page.html', base + 'docs/page.html?__docserve_standalone=1')):
                    with client.open(Request(base + url, headers={'Accept': 'text/html', 'Referer': referrer})) as response:
                        response.read()

                def recent():
                    with client.open(base + '__serve_html__/api/recent') as response:
                        return [entry['path'] for entry in json.load(response)['results']]

                def post(body, headers=None):
                    request = Request(base + '__serve_html__/api/visit', data=body,
                                      headers=headers or {'Content-Type': 'application/json'})
                    return client.open(request)

                self.assertEqual(recent(), [])
                for body, headers, code in (
                    (b'{', None, 400), (b'[]', None, 400),
                    (b'{"url":"/../outside"}', None, 400),
                    (b'{"url":"/missing"}', None, 404),
                    (b'{"url":"/__serve_html__/viewer.js"}', None, 400),
                    (b'{"url":"/docs/page.html"}', {'Content-Type': 'text/plain'}, 400),
                    (b'{"url":"/docs/page.html"}', {'Content-Type': 'application/json', 'Sec-Fetch-Site': 'cross-site'}, 400),
                    (b'x' * 8193, None, 400),
                ):
                    with self.subTest(body=body[:80]), self.assertRaises(HTTPError) as caught:
                        post(body, headers)
                    self.assertEqual(caught.exception.code, code)
                    caught.exception.close()
                self.assertEqual(recent(), [])
                with post(b'{"url":"/docs/page.html?query=1#heading"}') as response:
                    self.assertEqual(json.load(response), {'recorded': True})
                self.assertEqual(recent(), ['docs/page.html'])
                with post(b'{"url":"/docs/"}') as response:
                    response.read()
                self.assertEqual(recent(), ['docs', 'docs/page.html'])


if __name__ == '__main__':
    unittest.main()
