#!/usr/bin/env python3
"""Verified camera-folder transfer over a pinned-host-key SSH connection.

The Pi mount helper/UI must supply a read-only camera folder, never its boot disk.
This module only reads its source. It never unmounts, erases or reformats a device.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

from storage import CHUNK, HEADER_LIMIT, directory, digest_fd, identifier, regular, relative_parts


class Connection:
    def __init__(self, command):
        # No shell; the production command uses a server-side forced command.
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL)

    def request(self, operation, body=None):
        try:
            header = (json.dumps(operation) + '\n').encode()
            if len(header) > HEADER_LIMIT:
                raise ValueError('File metadata exceeds transfer limit.')
            self.process.stdin.write(header)
            if body is not None:
                self.process.stdin.write(body)
            self.process.stdin.flush()
            line = self.process.stdout.readline(HEADER_LIMIT + 1)
        except BrokenPipeError:
            raise ConnectionError('Server connection closed. Retry this project/card to resume.') from None
        if not line or len(line) > HEADER_LIMIT or not line.endswith(b'\n'):
            raise ConnectionError('Server connection interrupted. Retry this project/card to resume.')
        result = json.loads(line)
        if not result.get('ok'):
            raise ValueError(result.get('error', 'Server rejected transfer.'))
        return result

    def close(self):
        try:
            self.process.stdin.close()
        except BrokenPipeError:
            pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.process.stdout.close()


def snapshot(root_fd):
    rows = []

    def walk(parts):
        with directory(root_fd, parts, create=False) as fd:
            with os.scandir(fd) as entries:
                names = sorted(e.name for e in entries)
            for name in names:
                relative_parts('/'.join([*parts, name]))
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    raise ValueError('Camera folder contains a symbolic link; no import started.')
                if stat.S_ISDIR(info.st_mode):
                    walk([*parts, name])
                elif stat.S_ISREG(info.st_mode):
                    rows.append({'parts': [*parts, name], 'size': info.st_size,
                                 'identity': (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)})
                else:
                    raise ValueError('Camera folder contains a non-regular file; no import started.')
    walk([])
    if not rows:
        raise ValueError('This camera folder contains no files.')
    return rows


def verify_source(fd, expected):
    info = os.fstat(fd)
    if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != expected:
        raise ValueError('Camera file changed during import; no completion manifest was requested.')


def import_folder(source, project, card, command, progress=lambda event: None, source_uuid=None):
    if source_uuid is None:
        identifier(project)
        identifier(card)
    root_fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    connection = None
    try:
        rows = snapshot(root_fd)
        total = sum(row['size'] for row in rows)
        completed = 0
        transferred = 0
        connection = Connection(command)
        if connection.request({'op': 'ping'}).get('protocol') != 1:
            raise ValueError('Server transfer protocol is incompatible.')
        last_report = [0, None]
        if source_uuid is not None:
            # Routing hint only; SHA-256 still verifies every byte on each import.
            selection = hashlib.sha256(json.dumps([
                ['/'.join(row['parts']), row['size'], row['identity'][3]] for row in rows
            ], separators=(',', ':')).encode()).hexdigest()
            route = connection.request({'op': 'plan', 'source_uuid': source_uuid, 'selection': selection})
            project, card = route['project'], route['card']

        def report(event):
            progress(event)
            now = time.monotonic()
            if source_uuid is not None and (now-last_report[0] >= 2 or event['phase'] != last_report[1]):
                connection.request({'op': 'status', 'event': event})
                last_report[:] = [now, event['phase']]
        for index, row in enumerate(rows):
            path = '/'.join(row['parts'])

            def emit(phase, offset=0):
                report({'phase': phase, 'file': path, 'file_index': index + 1,
                          'file_count': len(rows), 'file_bytes': row['size'],
                          'file_offset': offset, 'verified_bytes': completed,
                          'total_bytes': total, 'transferred_bytes': transferred})

            with directory(root_fd, row['parts'][:-1], create=False) as parent:
                fd = regular(os.open(row['parts'][-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                     dir_fd=parent))
            try:
                verify_source(fd, row['identity'])
                emit('hashing')
                sha256 = digest_fd(fd)
                verify_source(fd, row['identity'])
                state = connection.request({'op': 'begin', 'project': project, 'card': card,
                    'path': path, 'size': row['size'], 'sha256': sha256})
                if state['state'] != 'verified':
                    offset = state['offset']
                    if type(offset) is not int or not 0 <= offset <= row['size']:
                        raise ValueError('Server returned an invalid resume position.')
                    emit('checking-resume', offset)
                    if digest_fd(fd, offset) != state['prefix_sha256']:
                        connection.request({'op': 'reset'})
                        offset = 0
                    while offset < row['size']:
                        emit('copying', offset)
                        data = os.pread(fd, min(CHUNK, row['size'] - offset), offset)
                        if not data:
                            raise OSError('Card disconnected or file truncated. Source retained; retry to resume.')
                        result = connection.request({'op': 'chunk', 'offset': offset, 'length': len(data)}, data)
                        offset += len(data)
                        transferred += len(data)
                        if result.get('offset') != offset:
                            raise ValueError('Server acknowledged an unexpected upload position.')
                    verify_source(fd, row['identity'])
                    emit('verifying', offset)
                    connection.request({'op': 'finish'})
                verify_source(fd, row['identity'])
                completed += row['size']
                emit('file-verified', row['size'])
            finally:
                os.close(fd)
        # Refuse completion if the source file set changed since enumeration.
        if snapshot(root_fd) != rows:
            raise ValueError('Camera folder changed during import. Retry before claiming completion.')
        report({'phase': 'verifying-import', 'verified_bytes': completed,
                  'total_bytes': total, 'file_count': len(rows), 'transferred_bytes': transferred})
        result = connection.request({'op': 'complete', 'file_count': len(rows)})
        report(dict(result, phase='complete', verified_bytes=completed,
                      total_bytes=total, transferred_bytes=transferred))
        return result
    finally:
        if connection:
            connection.close()
        os.close(root_fd)


def ssh_command(host, identity, known_hosts):
    if host.startswith('-'):
        raise ValueError('Invalid SSH host.')
    return ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(known_hosts),
            '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15',
            '-o', 'ServerAliveCountMax=3', '-i', str(identity), host, 'footage-receiver']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('project')
    parser.add_argument('card')
    parser.add_argument('--host', required=True)
    parser.add_argument('--identity', type=Path, required=True)
    parser.add_argument('--known-hosts', type=Path, required=True)
    args = parser.parse_args()
    try:
        import_folder(args.source, args.project, args.card,
                      ssh_command(args.host, args.identity, args.known_hosts),
                      lambda event: print(json.dumps(event), flush=True))
    except (ValueError, OSError, ConnectionError) as error:
        print(json.dumps({'phase': 'failed', 'error': str(error), 'source_retained': True}), flush=True)
        raise SystemExit(1)
