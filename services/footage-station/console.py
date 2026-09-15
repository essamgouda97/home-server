#!/usr/bin/env python3
"""Server tracking UI. Access is authenticated by the private NPM proxy route."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import uuid

from state import State
from storage import identifier, stamp

STATIC = Path(__file__).parent / 'static'
LOCK = threading.Lock()


def label(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 120 or any(ord(c) < 32 for c in value):
        raise ValueError('Enter a name of 1–120 characters.')
    return value.strip()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_):
        pass

    def send(self, code, data, kind='application/json'):
        body = json.dumps(data).encode() if kind == 'application/json' else data
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/health':
            return self.send(200, {'ok': True})
        if self.path == '/api/state':
            state = State(self.server.root)
            try:
                station = state.read('station.json', {})
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(station['seen_at'])).total_seconds() if station.get('seen_at') else None
                rows = state.imports(100)
                for row in rows:
                    key = identifier(row['id'])
                    row['assignment'] = state.read('assignments/' + key + '.json',
                        {'project': row['project'], 'session': row['card']})
                    row['codex'] = state.read('jobs/' + key + '.json', {'status': 'not queued'})
                return self.send(200, {'station': station, 'station_online': age is not None and age < 90,
                    'imports': rows, 'policy': state.read('policy.json', {'project': 'Inbox'}),
                    'worker': state.read('worker.json', {}), 'server_time': stamp()})
            except (ValueError, OSError, KeyError):
                return self.send(503, {'error': 'Tracking metadata is unavailable. Try again shortly.'})
            finally:
                state.close()
        assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                  '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                  '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if self.path in assets:
            name, kind = assets[self.path]
            return self.send(200, (STATIC / name).read_bytes(), kind)
        self.send(404, {'error': 'Not found.'})

    def do_POST(self):
        # NPM also enforces origin and login. This second check protects direct
        # container access from browser cross-origin requests.
        if self.headers.get('Origin') != self.server.origin or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.send(403, {'error': 'Open this page at its configured address before making changes.'})
        state = None
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 8192:
                raise ValueError('Request exceeds limit.')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected an object.')
            state = State(self.server.root)
            with LOCK:
                if self.path == '/api/policy':
                    current = state.read('policy.json', {})
                    current['project'] = identifier(data.get('project'))
                    state.write('policy.json', current)
                elif self.path == '/api/retry':
                    current = state.read('policy.json', {})
                    current['retry_nonce'] = uuid.uuid4().hex
                    state.write('policy.json', current)
                elif self.path in ('/api/assign', '/api/codex'):
                    key = identifier(data.get('id'))
                    imported = state.read('imports/' + key + '.json')
                    if not imported:
                        raise ValueError('Import not found.')
                    if self.path == '/api/codex' and not imported.get('verified_at'):
                        raise ValueError('Codex reviews start after the import is verified.')
                    if self.path == '/api/assign':
                        state.write('assignments/' + key + '.json',
                            {'project': label(data.get('project')), 'session': label(data.get('session')), 'updated_at': stamp()})
                    else:
                        # Separate request avoids overwriting a running job's result.
                        state.write('requests/' + key + '.json', {'nonce': uuid.uuid4().hex, 'requested_at': stamp()})
                else:
                    return self.send(404, {'error': 'Not found.'})
            self.send(200, {'ok': True})
        except (ValueError, OSError, KeyError) as error:
            self.send(400, {'error': str(error) if isinstance(error, ValueError) else 'Could not save the change.'})
        finally:
            if state:
                state.close()


def make_server(root, host='0.0.0.0', port=8080, origin='http://ingest.lan'):
    server = ThreadingHTTPServer((host, port), Handler)
    server.root, server.origin = root, origin
    return server


if __name__ == '__main__':
    make_server(os.environ.get('CREATIVE_ROOT', '/creative'),
                origin=os.environ.get('CONSOLE_ORIGIN', 'http://ingest.lan')).serve_forever()
