#!/usr/bin/env python3
"""Prove single-copy imports using only disposable files created by this check."""
import subprocess
import uuid


def main():
    for app, library in [('radarr','/movies'),('sonarr','/tv')]:
        name = '.hardlink-probe-'+uuid.uuid4().hex
        source, target = '/downloads/'+name, library+'/'+name
        def call(*args):
            return subprocess.run(['docker','exec','-u','1000:1000',app,*args],capture_output=True,text=True)
        try:
            assert call('touch',source).returncode == 0, app+' cannot create synthetic download'
            assert call('ln',source,target).returncode == 0, app+' cannot hardlink download to library'
            result = call('stat','-c','%d:%i:%h',source,target)
            assert result.returncode == 0
            rows = result.stdout.strip().splitlines()
            assert len(rows) == 2 and rows[0] == rows[1] and rows[0].endswith(':2')
            assert call('rm',source).returncode == 0
            assert call('test','-f',target).returncode == 0, 'Library link must survive source unlink'
            print('PASS',app,'same device/inode, link count two, independent directory entries')
        finally:
            assert call('rm','-f',source,target).returncode == 0, 'Synthetic probe cleanup failed'


if __name__ == '__main__': main()
