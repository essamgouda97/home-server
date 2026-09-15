"""Small durable metadata store; media files are never moved by assignment changes."""
import json
import os
import uuid
from storage import directory, regular, relative_parts


class State:
    def __init__(self, root):
        self.fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    def close(self):
        os.close(self.fd)

    def read(self, name, default=None):
        parts = ['.footage-ingest', *relative_parts(name)]
        with directory(self.fd, parts[:-1]) as parent:
            try:
                fd = regular(os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent))
            except FileNotFoundError:
                return default
            with os.fdopen(fd, 'rb') as f:
                data = f.read(2 * 1024 * 1024 + 1)
                if len(data) > 2 * 1024 * 1024:
                    raise ValueError('Metadata file exceeds limit.')
                return json.loads(data)

    def write(self, name, value):
        parts = ['.footage-ingest', *relative_parts(name)]
        data = (json.dumps(value, ensure_ascii=True) + '\n').encode()
        if len(data) > 2 * 1024 * 1024:
            raise ValueError('Metadata exceeds limit.')
        with directory(self.fd, parts[:-1]) as parent:
            temporary = '.' + uuid.uuid4().hex + '.tmp'
            fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o640, dir_fd=parent)
            try:
                with os.fdopen(fd, 'wb') as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporary, parts[-1], src_dir_fd=parent, dst_dir_fd=parent)
                os.fsync(parent)
            finally:
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass

    def imports(self, limit=100):
        with directory(self.fd, ['.footage-ingest', 'imports']) as parent:
            with os.scandir(parent) as entries:
                names = [(e.stat(follow_symlinks=False).st_mtime_ns, e.name) for e in entries
                         if e.name.endswith('.json') and e.is_file(follow_symlinks=False)]
        names.sort(reverse=True)
        return [self.read('imports/' + name) for _, name in names[:limit]]
