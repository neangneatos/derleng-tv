"""Offline security/regression checks. No listeners, live config writes or Telegram calls."""
import io
import json
import os
import socket
import ssl
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest import mock

import bot
import server
import start_tv as supervisor


class Response:
    status = 200
    def __init__(self, data):
        self.data = json.dumps(data).encode()
    def read(self, n=-1):
        return self.data if n < 0 else self.data[:n]
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


class BackendRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log = mock.patch.object(supervisor, 'LOG_FILE', os.path.join(self.temp.name, 'log'))
        self.log.start()
        self.addCleanup(self.log.stop)

    def test_proxy_removed_without_any_egress(self):
        # Exercise dispatch directly: no listening socket or external network.
        for method in (False, True):
            for target in ('', '?url=http://127.0.0.1/', '?url=https://example.com/video.m3u8'):
                handler = object.__new__(server.DerlengTVRequestHandler)
                handler.path = '/proxy' + target
                handler._send_json = mock.Mock()
                with mock.patch('urllib.request.urlopen') as outbound:
                    handler._handle_request(head_only=method)
                    outbound.assert_not_called()
                self.assertEqual(handler._send_json.call_args.args[0], 410)
                self.assertEqual(handler._send_json.call_args.kwargs['head_only'], method)

    def test_release_asset_allowlist(self):
        from test_suite import execute_handler_via_socketpair
        names = ['channels.0123456789abcdef.json', 'health.json', 'vendor/hls-1.7.4.min.js']
        for name in names:
            filename = os.path.join(self.temp.name, name)
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            with open(filename, 'w') as f:
                f.write('{}')
        with mock.patch.object(server, 'BASE_DIR', self.temp.name):
            for name in names:
                self.assertEqual(execute_handler_via_socketpair('/' + name)['status'], 200)
            for name in ('channels.not-a-hash.json', 'vendor/unknown.js', 'private.json'):
                self.assertEqual(execute_handler_via_socketpair('/' + name)['status'], 404)

    def test_health_requires_catalog_and_index(self):
        with open(os.path.join(self.temp.name, 'index.html'), 'w') as f:
            f.write('a' * 2048)
        handler = object.__new__(server.DerlengTVRequestHandler)
        handler.path = '/healthz'
        handler._send_json = mock.Mock()
        with mock.patch.object(server, 'BASE_DIR', self.temp.name):
            handler._handle_request()
            self.assertEqual(handler._send_json.call_args.args[0], 503)
            with open(os.path.join(self.temp.name, 'channels_public.json'), 'w') as f:
                json.dump([{'id': '0123456789abcdef', 'n': 'Demo', 'u': 'https://example.org/a.m3u8'}], f)
            handler._handle_request()
            self.assertEqual(handler._send_json.call_args.args[0], 200)

    def test_health_errors_never_succeed(self):
        errors = [PermissionError('Operation not permitted'),
                  urllib.error.URLError(socket.gaierror(8, 'nodename nor servname provided')),
                  urllib.error.URLError(ssl.SSLError('TLS failed')),
                  TimeoutError('timed out')]
        for error in errors:
            with self.subTest(error=type(error).__name__), mock.patch('urllib.request.urlopen', side_effect=error):
                self.assertFalse(supervisor.check_local_health()[0])
                self.assertFalse(supervisor.check_public_tunnel_health('https://example.org')[0])
                self.assertFalse(supervisor.update_telegram_menu('fake-token', 'https://example.org'))

    def test_menu_requires_explicit_true(self):
        for ok in (False, None, 'true', 1):
            with mock.patch('urllib.request.urlopen', return_value=Response({'ok': ok})):
                self.assertFalse(supervisor.update_telegram_menu('fake-token', 'https://example.org'))
        with mock.patch('urllib.request.urlopen', return_value=Response({'ok': True})):
            self.assertTrue(supervisor.update_telegram_menu('fake-token', 'https://example.org'))

    def test_bot_reads_only_published_ids(self):
        filename = os.path.join(self.temp.name, 'catalog.json')
        with open(filename, 'w') as f:
            json.dump([{'id': '0123456789abcdef', 'n': 'Demo', 'u': 'https://example.org/a.m3u8', 'g': 'Cambodia', 't': 'News', 'c': 'KH'},
                       {'name': 'RAW', 'url': 'https://example.org/private?token=secret'},
                       {'id': 'fedcba9876543210', 'n': 'HTTP', 'u': 'http://example.org/a.m3u8'}], f)
        with mock.patch.object(bot, 'CHANNELS_FILE', filename):
            channels = bot.load_channels()
        self.assertEqual(len(channels), 2)
        self.assertTrue(any(c["url"].startswith("http://") for c in channels))
        with mock.patch.object(bot, 'CHANNELS', channels), mock.patch.object(bot, 'get_env_config', return_value=('', 'https://tv.derlenghub.com')):
            _, markup = bot.build_category_view('Cambodia')
            link = markup['inline_keyboard'][0][0]['web_app']['url']
            self.assertEqual(link, 'https://tv.derlenghub.com/?cid=0123456789abcdef')
            self.assertNotIn('example.org', json.dumps(markup))
        with mock.patch.object(bot, 'CHANNELS', channels), mock.patch.object(bot, 'get_env_config', return_value=('', '')):
            _, markup = bot.build_category_view('ALL')
            self.assertNotIn('https://example.org', json.dumps(markup))
        with mock.patch.object(bot, 'CHANNELS_FILE', filename + '.missing'):
            self.assertEqual(bot.load_channels(), [])

    def test_bot_rate_limits_bounded_and_ambiguous_send_not_retried(self):
        with mock.patch.object(bot, 'get_env_config', return_value=('fake', '')), mock.patch.object(bot.time, 'sleep') as sleep:
            limited = {'ok': False, 'error_code': 429, 'parameters': {'retry_after': 2}}
            with mock.patch('urllib.request.urlopen', return_value=Response(limited)) as req:
                self.assertFalse(bot.api_request('sendMessage', {})['ok'])
                self.assertEqual(req.call_count, 3)
                self.assertEqual(sleep.call_count, 2)
            with mock.patch('urllib.request.urlopen', side_effect=TimeoutError('ambiguous')) as req:
                self.assertFalse(bot.api_request('sendMessage', {})['ok'])
                self.assertEqual(req.call_count, 1)
            with mock.patch('urllib.request.urlopen', return_value=Response({'ok': False, 'error_code': 429, 'parameters': {'retry_after': 60}})) as req:
                self.assertFalse(bot.api_request('sendMessage', {})['ok'])
                self.assertEqual(req.call_count, 1)


if __name__ == '__main__':
    unittest.main()
