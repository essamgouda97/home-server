"""Filesystem primitives shared by the receiver, transfer client and console."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
import re
import stat

CHUNK = 4 * 1024 * 1024
HEADER_LIMIT = 65536
MAX_FILE = 2 * 1024**4


def stamp():
    return datetime.now(timezone.utc).isoformat()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,100}', value) or '..' in value:
        raise ValueError('Use letters, numbers, dots, hyphens or underscores for project/card names.')
    return value


def relative_parts(value):
    if not isinstance(value, str) or len(value) > 4096 or '\\' in value or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid camera file path.')
    parts = value.split('/')
    if len(parts) > 32 or any(p in ('', '.', '..') or len(p.encode()) > 255 for p in parts):
        raise ValueError('Camera file path must be relative and cannot traverse directories.')
    return parts


def integer(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError('Invalid byte count.')
    return value


def digest_fd(fd, length=None, progress=None):
    h = hashlib.sha256()
    position = 0
    while length is None or position < length:
        data = os.pread(fd, CHUNK if length is None else min(CHUNK, length-position), position)
        if not data:
            if length is not None and position != length:
                raise ValueError('File ended before the expected byte count.')
            break
        h.update(data)
        position += len(data)
        if progress:
            progress(position)
    return h.hexdigest()


def regular(fd):
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ValueError('Expected a regular file.')
    return fd


@contextmanager
def directory(root_fd, parts, create=True):
    fd = os.dup(root_fd)
    try:
        for part in parts:
            if create:
                try:
                    os.mkdir(part, 0o750, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)
