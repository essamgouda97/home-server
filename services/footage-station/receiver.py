#!/usr/bin/env python3
"""Restricted SSH receiver: resumable uploads, verified exclusive publication.

stdin/stdout carry newline-delimited JSON. A `chunk` header is followed by exactly
`length` raw bytes. This program executes no caller-provided commands. Install it
as an SSH forced command; choose its root in server-owned configuration only.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

from storage import CHUNK, HEADER_LIMIT, MAX_FILE, stamp, identifier, relative_parts, integer, digest_fd, regular, directory
from state import State


class Receiver:
    def __init__(self, root):
        self.root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.lock_fd = None
        self.context = None
        self.active = None
        self.verified = {}
        self.started_at = stamp()
        self.closed = False
        self.state = State(root)
        self.route = None
        try:
            with directory(self.root_fd, ['.footage-ingest']) as spool:
                self.lock_fd = regular(os.open('receiver.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                                               0o600, dir_fd=spool))
                try:
                    fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ValueError('Another import is active; retry when it finishes.')
        except BaseException:
            self.close()
            raise

    def close(self):
        if not self.closed:
            self.closed = True
            if self.lock_fd is not None:
                os.close(self.lock_fd)
            os.close(self.root_fd)
            self.state.close()

    def plan(self, request):
        if self.context:
            raise ValueError('Select the card before transferring files.')
        source = identifier(request.get('source_uuid'))
        selection = request.get('selection')
        if not isinstance(selection, str) or not re.fullmatch('[0-9a-f]{64}', selection):
            raise ValueError('Invalid card selection fingerprint.')
        key = hashlib.sha256((source + ':' + selection).encode()).hexdigest()
        route = self.state.read('routes/' + key + '.json')
        if route is None:
            policy = self.state.read('policy.json', {})
            route = {'id': key, 'source_uuid': source,
                     'project': identifier(policy.get('project', 'Inbox')),
                     'card': source + '-' + selection[:16], 'created_at': stamp()}
            self.state.write('routes/' + key + '.json', route)
        self.route = route
        self.context = (route['project'], route['card'])
        if not self.state.read('imports/' + key + '.json'):
            self.state.write('imports/' + key + '.json', dict(route, status='importing',
                file_count=0, total_bytes=0, manifest=None))
        self.state.write('station.json', dict(route, phase='scanning', seen_at=stamp()))
        return route

    def status(self, request):
        event = request.get('event', {})
        if not isinstance(event, dict):
            raise ValueError('Invalid progress event.')
        clean = {}
        for key in ('phase', 'file', 'error', 'source_uuid'):
            if key in event:
                value = event[key]
                if not isinstance(value, str) or len(value) > 4096:
                    raise ValueError('Invalid progress text.')
                clean[key] = value
        for key in ('file_index', 'file_count', 'file_bytes', 'file_offset',
                    'verified_bytes', 'total_bytes', 'transferred_bytes'):
            if key in event:
                clean[key] = integer(event[key], MAX_FILE * 1000)
        clean['safe_to_remove'] = event.get('safe_to_remove') is True
        previous = self.state.read('station.json', {})
        if clean.get('phase') in ('waiting', 'mounting'):
            previous = {}
        self.state.write('station.json', dict(previous, **clean, seen_at=stamp()))
        key = (self.route or previous).get('id')
        if key and clean.get('phase') not in ('waiting', 'safe', 'mounting'):
            row = self.state.read('imports/' + identifier(key) + '.json', {})
            if row and not row.get('verified_at'):
                row.update(status=clean.get('phase', row.get('status')), updated_at=stamp())
                for field in ('file_count', 'total_bytes', 'verified_bytes', 'error'):
                    if field in clean:
                        row[field] = clean[field]
                self.state.write('imports/' + key + '.json', row)
        return self.state.read('policy.json', {'project': 'Inbox'})

    def target(self, path):
        return ['Projects', self.context[0], 'Originals', self.context[1], *relative_parts(path)]

    def existing_matches(self, parent, name, size, sha256):
        try:
            fd = regular(os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent))
        except FileNotFoundError:
            return False
        try:
            if os.fstat(fd).st_size != size or digest_fd(fd) != sha256:
                raise ValueError('An original with this name contains different data. Choose a new card name.')
            return True
        finally:
            os.close(fd)

    def begin(self, request):
        if self.active:
            raise ValueError('Finish the current file before starting another.')
        context = (identifier(request.get('project')), identifier(request.get('card')))
        if self.context and self.context != context:
            raise ValueError('A connection can import only one project/card pair.')
        self.context = context
        path = request.get('path')
        relative_parts(path)
        size = integer(request.get('size'), MAX_FILE)
        sha256 = request.get('sha256')
        if not isinstance(sha256, str) or not re.fullmatch('[0-9a-f]{64}', sha256):
            raise ValueError('Invalid SHA-256.')
        row = {'path': path, 'bytes': size, 'sha256': sha256}
        parts = self.target(path)
        with directory(self.root_fd, parts[:-1]) as parent:
            if self.existing_matches(parent, parts[-1], size, sha256):
                self.verified[path] = dict(row, verified_at=stamp())
                return {'state': 'verified', 'offset': size}
        key = hashlib.sha256(json.dumps([*context, path, size, sha256]).encode()).hexdigest()
        with directory(self.root_fd, ['.footage-ingest', 'partials']) as spool:
            fd = regular(os.open(key, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=spool))
            try:
                offset = os.fstat(fd).st_size
                if offset > size:
                    raise ValueError('Partial upload exceeds original size; reset it explicitly.')
                prefix = digest_fd(fd)
            finally:
                os.close(fd)
        self.active = dict(row, key=key, offset=offset)
        return {'state': 'partial', 'offset': offset, 'prefix_sha256': prefix}

    def chunk(self, request, stream):
        if self.active is None:
            raise ValueError('No active upload.')
        offset = integer(request.get('offset'), MAX_FILE)
        length = integer(request.get('length'), CHUNK)
        if not length or offset != self.active['offset'] or offset + length > self.active['bytes']:
            raise ValueError('Chunk does not match the upload position or file size.')
        with directory(self.root_fd, ['.footage-ingest', 'partials']) as spool:
            fd = regular(os.open(self.active['key'], os.O_WRONLY | os.O_NOFOLLOW, dir_fd=spool))
            try:
                if os.fstat(fd).st_size != offset:
                    raise ValueError('Partial upload changed; reconnect to verify its prefix.')
                os.lseek(fd, offset, os.SEEK_SET)
                remaining = length
                while remaining:
                    data = stream.read(min(remaining, 256 * 1024))
                    if not data:
                        raise EOFError('Transfer interrupted; partial bytes retained for retry.')
                    view = memoryview(data)
                    while view:
                        written = os.write(fd, view)
                        if written <= 0:
                            raise OSError('Upload write did not advance.')
                        view = view[written:]
                    remaining -= len(data)
                os.fsync(fd)
            finally:
                os.close(fd)
        self.active['offset'] += length
        return {'offset': self.active['offset']}

    def reset(self):
        if self.active is None:
            raise ValueError('No active upload.')
        with directory(self.root_fd, ['.footage-ingest', 'partials']) as spool:
            fd = regular(os.open(self.active['key'], os.O_WRONLY | os.O_NOFOLLOW, dir_fd=spool))
            try:
                os.ftruncate(fd, 0)
                os.fsync(fd)
            finally:
                os.close(fd)
        self.active['offset'] = 0
        return {'offset': 0}

    def finish(self):
        if self.active is None:
            raise ValueError('No active upload.')
        active = self.active
        parts = self.target(active['path'])
        with directory(self.root_fd, ['.footage-ingest', 'partials']) as spool:
            fd = regular(os.open(active['key'], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=spool))
            try:
                if os.fstat(fd).st_size != active['bytes'] or digest_fd(fd) != active['sha256']:
                    raise ValueError('Upload checksum differs from the card. Original was not published.')
                os.fsync(fd)
            finally:
                os.close(fd)
            with directory(self.root_fd, parts[:-1]) as parent:
                try:
                    os.link(active['key'], parts[-1], src_dir_fd=spool, dst_dir_fd=parent,
                            follow_symlinks=False)
                except FileExistsError:
                    self.existing_matches(parent, parts[-1], active['bytes'], active['sha256'])
                os.fsync(parent)
            os.unlink(active['key'], dir_fd=spool)
            os.fsync(spool)
        self.verified[active['path']] = {k: active[k] for k in ('path', 'bytes', 'sha256')}
        self.verified[active['path']]['verified_at'] = stamp()
        self.active = None
        return {'state': 'verified'}

    def complete(self, request):
        count = integer(request.get('file_count'), 1_000_000)
        if self.active or not self.context or not count or count != len(self.verified):
            raise ValueError('Import has not verified every expected file.')
        # Recheck published originals: user edits/deletion between finish and
        # manifest publication cannot be silently counted as a completed import.
        for row in self.verified.values():
            parts = self.target(row['path'])
            with directory(self.root_fd, parts[:-1], create=False) as parent:
                if not self.existing_matches(parent, parts[-1], row['bytes'], row['sha256']):
                    raise ValueError('An original was removed before import completion.')
        project, card = self.context
        name = card + '-' + uuid.uuid4().hex + '.json'
        report = {'schema': 1, 'project': project, 'card': card,
                  'started_at': self.started_at, 'verified_at': stamp(),
                  'files': list(self.verified.values())}
        data = (json.dumps(report, indent=2) + '\n').encode()
        with directory(self.root_fd, ['Projects', project, 'Manifests']) as parent:
            partial = '.' + name + '.partial'
            fd = regular(os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                                 0o640, dir_fd=parent))
            try:
                with os.fdopen(fd, 'wb') as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                os.link(partial, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
                os.fsync(parent)
            finally:
                os.unlink(partial, dir_fd=parent)
                os.fsync(parent)
        manifest = '/'.join(['Projects', project, 'Manifests', name])
        if self.route:
            key = self.route['id']
            previous = self.state.read('imports/' + key + '.json', {})
            # Queue before publication of the verified index; a fast worker must
            # never finish a job that this connection then resets to queued.
            if not previous.get('verified_at'):
                self.state.write('jobs/' + key + '.json',
                    {'id': key, 'status': 'queued', 'queued_at': stamp(), 'basis': 'file metadata'})
            self.state.write('imports/' + key + '.json', dict(self.route,
                status='verified', verified_at=report['verified_at'], file_count=count,
                total_bytes=sum(row['bytes'] for row in self.verified.values()),
                manifest=manifest))
        return {'state': 'complete', 'file_count': count, 'manifest': manifest}

    def handle(self, request, stream):
        operation = request.get('op')
        if operation == 'plan':
            return self.plan(request)
        if operation == 'status':
            return self.status(request)
        if operation == 'begin':
            return self.begin(request)
        if operation == 'chunk':
            return self.chunk(request, stream)
        if operation == 'reset':
            return self.reset()
        if operation == 'finish':
            return self.finish()
        if operation == 'complete':
            return self.complete(request)
        if operation == 'ping':
            usage = os.fstatvfs(self.root_fd)
            return {'protocol': 1, 'free_bytes': usage.f_bavail * usage.f_frsize}
        raise ValueError('Unsupported operation.')


def serve(root, incoming, outgoing):
    receiver = None
    try:
        receiver = Receiver(root)
        while True:
            line = incoming.readline(HEADER_LIMIT + 1)
            if not line:
                return 0
            if len(line) > HEADER_LIMIT or not line.endswith(b'\n'):
                raise ValueError('Invalid request header.')
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError('Expected an operation object.')
            result = receiver.handle(request, incoming)
            outgoing.write((json.dumps(dict(result, ok=True)) + '\n').encode())
            outgoing.flush()
    except (ValueError, OSError, EOFError) as error:
        message = str(error) if not isinstance(error, OSError) else (error.strerror or 'Storage operation failed.')
        try:
            outgoing.write((json.dumps({'ok': False, 'error': message}) + '\n').encode())
            outgoing.flush()
        except BrokenPipeError:
            pass
        return 1
    finally:
        if receiver:
            receiver.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(serve(args.root, sys.stdin.buffer, sys.stdout.buffer))
