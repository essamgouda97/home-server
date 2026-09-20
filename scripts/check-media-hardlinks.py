#!/usr/bin/env python3
"""Prove single-copy imports using only disposable files created by this check."""
import subprocess
import uuid
from pathlib import Path


def main():
    for app, library in [('radarr','/movies'),('sonarr','/tv')]:
        name = '.hardlink-probe-'+uuid.uuid4().hex
        source, target = '/downloads/'+name, library+'/'+name
        def call(*args):
            return subprocess.run(['docker','exec','-u','1000:1000',app,*args],capture_output=True,text=True)
        try:
            assert call('touch',source).returncode == 0, app+' cannot create synthetic download'
            assert call('ln',source,target).returncode == 0, app+' cannot hardlink download to library'
            # mergerfs can cache the old link count. Check only our synthetic
            # files on physical branches to prove no extra allocation exists.
            pairs = []
            for branch in ['hdd','ssd','usb-ssd']:
                root = Path('/srv/mergerfs')/branch/'server/media'
                a = root/'downloads'/name
                b = root/('movies' if app == 'radarr' else 'tvshows')/name
                if a.exists() or b.exists():
                    sa, sb = a.stat(), b.stat()
                    assert (sa.st_dev,sa.st_ino)==(sb.st_dev,sb.st_ino)
                    assert sa.st_nlink == sb.st_nlink == 2
                    pairs.append(branch)
            assert len(pairs)==1, 'Synthetic files must occupy exactly one physical branch'
            assert call('rm',source).returncode == 0
            assert call('test','-f',target).returncode == 0, 'Library link must survive source unlink'
            print('PASS',app,'same device/inode, link count two, independent directory entries')
        finally:
            assert call('rm','-f',source,target).returncode == 0, 'Synthetic probe cleanup failed'


if __name__ == '__main__': main()
