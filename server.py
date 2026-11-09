#!/usr/bin/env python3
"""
DERLENG TV — Hardened Multi-Threaded HTTP Server (v3.0)
Features:
  - ThreadedHTTPServer with per-connection socket timeouts (10s)
  - Strict public-asset allowlist (blocks .env, .py, .sh, logs, and directory traversal)
  - Real Gzip compression with in-memory mtime cache, Content-Encoding, Content-Length, and Vary headers
  - ETag / 304 Not Modified support and asset-specific Cache-Control policies
  - Machine-readable /healthz endpoint for supervisor verification
  - Graceful SIGINT / SIGTERM shutdown
"""

import os
import re
import sys
import time
import json
import gzip
import hashlib
import signal
import socket
import argparse
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.environ.get('DERLENG_WEB_ROOT', os.path.join(PROJECT_DIR, 'dist', 'hostinger')))

# Explicitly approved public files and their MIME types / cache policies
PUBLIC_ASSETS = {
    '/': {
        'file': 'index.html',
        'mime': 'text/html; charset=utf-8',
        'compressible': True,
        'cache': 'no-cache, must-revalidate',
    },
    '/index.html': {
        'file': 'index.html',
        'mime': 'text/html; charset=utf-8',
        'compressible': True,
        'cache': 'no-cache, must-revalidate',
    },
    '/logo.png': {
        'file': 'logo.png',
        'mime': 'image/png',
        'compressible': False,
        'cache': 'public, max-age=86400, immutable',
    },
    '/logo.svg': {
        'file': 'logo.svg',
        'mime': 'image/svg+xml; charset=utf-8',
        'compressible': True,
        'cache': 'public, max-age=86400, immutable',
    },
    '/favicon.png': {
        'file': 'favicon.png',
        'mime': 'image/png',
        'compressible': False,
        'cache': 'public, max-age=86400, immutable',
    },
    '/favicon.ico': {
        'file': 'favicon.png',
        'mime': 'image/png',
        'compressible': False,
        'cache': 'public, max-age=86400, immutable',
    },
    '/channels_public.json': {
        'file': 'channels_public.json',
        'mime': 'application/json; charset=utf-8',
        'compressible': True,
        'cache': 'public, max-age=300',
    },
    '/start_banner.png': {
        'file': 'start_banner.png',
        'mime': 'image/png',
        'compressible': False,
        'cache': 'public, max-age=86400, immutable',
    },
    '/start banner.png': {
        'file': 'start_banner.png',
        'mime': 'image/png',
        'compressible': False,
        'cache': 'public, max-age=86400, immutable',
    },
    '/welcome_banner.png': {
        'file': 'welcome_banner.png',
        'mime': 'image/png',
        'compressible': False,
        'cache': 'public, max-age=86400, immutable',
    },
    '/welcome banner.png': {
        'file': 'welcome_banner.png',
        'mime': 'image/png',
        'compressible': False,
        'cache': 'public, max-age=86400, immutable',
    },
}

# Sensitive file patterns that must explicitly return 403 Forbidden
FORBIDDEN_PATTERNS = (
    '.env', '.py', '.sh', '.log', '.git', '.DS_Store',
    'channels.json', 'm3u', 'archive', 'backup'
)

# In-memory asset cache: { filepath: {'mtime': float, 'size': int, 'raw': bytes, 'gzip': bytes, 'etag': str} }
_ASSET_CACHE = {}


def load_asset_cached(filepath, compressible=True):
    """Loads file from disk and caches raw + gzip-compressed bytes keyed by mtime and size."""
    st = os.stat(filepath)
    mtime = st.st_mtime
    size = st.st_size
    cached = _ASSET_CACHE.get(filepath)
    if cached and cached['mtime'] == mtime and cached['size'] == size:
        return cached

    with open(filepath, 'rb') as f:
        raw_bytes = f.read()

    etag_hash = hashlib.sha1(f"{filepath}:{mtime}:{size}".encode('utf-8')).hexdigest()[:16]
    etag = f'"{etag_hash}"'
    gzip_bytes = gzip.compress(raw_bytes, compresslevel=6) if compressible else None

    entry = {
        'mtime': mtime,
        'size': len(raw_bytes),
        'raw': raw_bytes,
        'gzip': gzip_bytes,
        'etag': etag,
    }
    _ASSET_CACHE[filepath] = entry
    return entry


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        super().server_bind()


class DerlengTVRequestHandler(BaseHTTPRequestHandler):
    server_version = "DerlengTVHttp/3.0"
    protocol_version = "HTTP/1.1"
    timeout = 10

    def setup(self):
        super().setup()
        try:
            self.request.settimeout(self.timeout)
        except Exception:
            pass

    def log_message(self, fmt, *args):
        # Suppress noisy per-request console spam unless DERLENG_HTTP_VERBOSE=1
        if os.environ.get('DERLENG_HTTP_VERBOSE') == '1':
            sys.stderr.write("%s - - [%s] %s\n" % (
                self.address_string(),
                self.log_date_time_string(),
                fmt % args
            ))

    def _send_security_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer-when-downgrade')
        self.send_header('Access-Control-Allow-Origin', '*')

    def _send_json(self, status_code, payload_dict, head_only=False):
        raw = json.dumps(payload_dict, ensure_ascii=False).encode('utf-8')
        accept_enc = self.headers.get('Accept-Encoding', '')
        use_gzip = 'gzip' in accept_enc.lower() and len(raw) > 128
        body = gzip.compress(raw, compresslevel=6) if use_gzip else raw

        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Vary', 'Accept-Encoding')
        if use_gzip:
            self.send_header('Content-Encoding', 'gzip')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self._send_security_headers()
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _handle_request(self, head_only=False):
        try:
            parsed = urllib.parse.urlsplit(self.path)
            raw_path = parsed.path or '/'
            clean_path = urllib.parse.unquote(raw_path)
        except Exception:
            self._send_json(400, {'error': 'Bad Request', 'status': 400}, head_only=head_only)
            return

        # 1. Path traversal & forbidden file protection
        norm_check = clean_path.lower()
        if (
            '..' in clean_path
            or '\\' in clean_path
            or '\x00' in clean_path
            or clean_path.startswith('/.')
            or any(pat.lower() in norm_check for pat in FORBIDDEN_PATTERNS)
        ):
            self._send_json(403, {
                'error': 'Forbidden: Access to internal configuration or source files is denied.',
                'status': 403
            }, head_only=head_only)
            return

        # 2. Dedicated Health Check Endpoint (/healthz)
        if clean_path == '/healthz':
            index_path = os.path.join(BASE_DIR, 'index.html')
            index_ok = os.path.isfile(index_path) and os.path.getsize(index_path) > 1024
            catalog_ok = False
            try:
                with open(os.path.join(BASE_DIR, 'channels_public.json'), encoding='utf-8') as f:
                    catalog = json.load(f)
                catalog_ok = isinstance(catalog, list) and bool(catalog) and all(
                    isinstance(c, dict) and c.get('id') and c.get('n') and
                    isinstance(c.get('u'), str) and c['u'].startswith('https://')
                    for c in catalog)
            except (OSError, ValueError):
                pass
            ready = index_ok and catalog_ok
            status_code = 200 if ready else 503
            self._send_json(status_code, {
                'status': 'ok' if ready else 'degraded',
                'service': 'derleng-tv-webapp',
                'version': '3.0',
                'signature': 'DERLENG_TV_HEALTH_OK_V3',
                'index_ready': index_ok,
                'catalog_ready': catalog_ok,
                'timestamp': int(time.time())
            }, head_only=head_only)
            return

        # The static hosting release never relays user-supplied stream targets.
        if clean_path == '/proxy':
            self._send_json(410, {'error': 'Stream relay disabled; use a published HTTPS channel.',
                                  'status': 410}, head_only=head_only)
            return

        # 4. Explicitly Allowlisted Public Assets Only
        asset_meta = PUBLIC_ASSETS.get(clean_path)
        if re.fullmatch(r'/channels\.[a-f0-9]{16}\.json', clean_path):
            asset_meta = {'file': clean_path[1:], 'mime': 'application/json; charset=utf-8',
                          'compressible': True, 'cache': 'public, max-age=31536000, immutable'}
        elif clean_path == '/health.json':
            asset_meta = {'file': 'health.json', 'mime': 'application/json; charset=utf-8',
                          'compressible': True, 'cache': 'no-cache, must-revalidate'}
        elif clean_path == '/vendor/hls-1.7.4.min.js':
            asset_meta = {'file': 'vendor/hls-1.7.4.min.js', 'mime': 'application/javascript; charset=utf-8',
                          'compressible': True, 'cache': 'public, max-age=31536000, immutable'}
        if not asset_meta:
            self._send_json(404, {
                'error': 'Not Found',
                'path': clean_path,
                'status': 404
            }, head_only=head_only)
            return

        target_file = os.path.abspath(os.path.join(BASE_DIR, asset_meta['file']))
        if not target_file.startswith(BASE_DIR + os.sep) or not os.path.isfile(target_file):
            self._send_json(404, {
                'error': 'Asset File Missing',
                'status': 404
            }, head_only=head_only)
            return

        try:
            entry = load_asset_cached(target_file, compressible=asset_meta['compressible'])
        except Exception as e:
            self._send_json(500, {'error': f'Internal I/O Error: {type(e).__name__}', 'status': 500}, head_only=head_only)
            return

        # Check If-None-Match for 304 Not Modified
        client_etag = self.headers.get('If-None-Match')
        if client_etag and client_etag.strip() == entry['etag']:
            self.send_response(304)
            self.send_header('ETag', entry['etag'])
            self.send_header('Cache-Control', asset_meta['cache'])
            self.send_header('Vary', 'Accept-Encoding')
            self.send_header('Connection', 'close')
            self._send_security_headers()
            self.end_headers()
            return

        accept_enc = self.headers.get('Accept-Encoding', '')
        use_gzip = asset_meta['compressible'] and ('gzip' in accept_enc.lower()) and (entry['gzip'] is not None)
        payload = entry['gzip'] if use_gzip else entry['raw']

        self.send_response(200)
        self.send_header('Content-Type', asset_meta['mime'])
        self.send_header('Cache-Control', asset_meta['cache'])
        self.send_header('ETag', entry['etag'])
        if asset_meta['compressible']:
            self.send_header('Vary', 'Accept-Encoding')
        if use_gzip:
            self.send_header('Content-Encoding', 'gzip')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Connection', 'close')
        self._send_security_headers()
        self.end_headers()

        if not head_only:
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_GET(self):
        self._handle_request(head_only=False)

    def do_HEAD(self):
        self._handle_request(head_only=True)


def run_server(host='127.0.0.1', port=8080):
    server = ThreadedHTTPServer((host, port), DerlengTVRequestHandler)

    def handle_signal(signum, frame):
        threading_shutdown = lambda: server.shutdown()
        import threading
        threading.Thread(target=threading_shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print(f"[*] DERLENG TV Hardened HTTP Server v3.0 listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("[*] DERLENG TV HTTP Server stopped cleanly.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="DERLENG TV Hardened HTTP Server v3.0")
    parser.add_argument('--host', default=os.environ.get('DERLENG_HOST', '127.0.0.1'), help='Bind address (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=int(os.environ.get('DERLENG_PORT', '8080')), help='Bind port (default: 8080)')
    parser.add_argument('--directory', help='Static release root (default: dist/hostinger or DERLENG_WEB_ROOT)')
    args = parser.parse_args()
    if args.directory:
        BASE_DIR = os.path.abspath(args.directory)
    run_server(host=args.host, port=args.port)
