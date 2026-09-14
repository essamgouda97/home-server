#!/usr/bin/env python3
"""Integration regression check on the real mounted Creative share; synthetic data only."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

spec = importlib.util.spec_from_file_location('ingest', Path(__file__).with_name('ingest-footage.py'))
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)
share = Path('/Volumes/Creative')
if not os.path.ismount(share):
    raise SystemExit('Mount Creative before testing.')
project = 'verification-' + uuid.uuid4().hex
root = share / 'Projects' / project
try:
    with tempfile.TemporaryDirectory() as td:
        source = Path(td)
        original = source / 'DJI_0001.MP4'
        payload = os.urandom(1024 * 1024)
        original.write_bytes(payload)
        ingest.ingest(source, share, project, 'card01')
        ingest.ingest(source, share, project, 'card01')
        target = root / 'Originals/card01/DJI_0001.MP4'
        assert target.read_bytes() == payload
        original.write_bytes(b'conflicting footage')
        try:
            ingest.ingest(source, share, project, 'card01')
        except ValueError:
            pass
        else:
            raise AssertionError('Conflicting original was accepted')
        assert target.read_bytes() == payload
        partial = target.with_name('.race-probe')
        partial.write_bytes(b'concurrent writer')
        try:
            ingest.publish_exclusive(partial, target)
        except FileExistsError:
            pass
        else:
            raise AssertionError('Exclusive publication overwrote existing footage')
        assert target.read_bytes() == payload
        partial.unlink()
        original.unlink()
        original.symlink_to('/etc/hosts')
        try:
            ingest.ingest(source, share, project, 'card01')
        except ValueError:
            pass
        else:
            raise AssertionError('Source symlink was accepted')
        print('PASS: SMB ingest, rerun, conflict preservation, exclusive publication and symlink rejection.')
finally:
    if root.exists():
        # macOS metadata files can be hidden from SMB listings. Clean only this
        # randomly named probe directory on the server, including that metadata.
        import json, shlex
        settings = dict(line.split('=', 1) for line in (Path(__file__).resolve().parents[1] / 'server.conf').read_text().splitlines()
                        if line and not line.startswith('#') and '=' in line)
        remote = str(Path(settings['CREATIVE_ROOT']) / 'Projects' / project)
        code = 'import shutil; shutil.rmtree(' + repr(remote) + ')'
        subprocess.run(['ssh','home-server','python3 -c ' + shlex.quote(code)], check=True)
