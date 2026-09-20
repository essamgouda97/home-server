#!/usr/bin/env python3
"""Move one opaque directory and preserve paths; never enumerate private media.

Run on the server after syncing the matching Compose change. Root is needed only
to install the read-only container init hook. Backups contain configuration only.
"""
import datetime
import os
from pathlib import Path
import subprocess

REPO = Path(__file__).resolve().parents[1]
DATA = Path('/mnt/server')
SOURCE = DATA / 'downloads'
TARGET = DATA / 'media/downloads'
CONSUMERS = ['filebrowser', 'qbittorrent', 'radarr', 'sonarr', 'nzbget']


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def main():
    if SOURCE.is_symlink():
        assert SOURCE.resolve() == TARGET and TARGET.is_dir()
        print('Already migrated; run check-media-hardlinks.py')
        return
    assert SOURCE.is_dir() and not os.path.lexists(TARGET)
    backup = Path.home()/'.local/state/home-server-maintenance/media-hardlinks'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup.mkdir(parents=True, mode=0o700)
    # Capture the pre-migration storage declarations from the parent commit.
    old = subprocess.check_output(['git','-C',str(REPO),'show','HEAD^:docker-compose.yml'])
    assert b'/media/tvshows:/tv' in old and b'/media/movies:/movies' in old
    (backup/'compose.before.yml').write_bytes(old)
    hook = DATA/'media-path-init'
    hook.mkdir(mode=0o755, exist_ok=True)
    source = REPO/'config/media-path-init/10-paths.sh'
    password = (Path.home()/'.config/home-server/secrets/creative_password').read_text().strip()+'\n'
    result = subprocess.run(['sudo','-S','-p','','install','-o','root','-g','root','-m','0755',str(source),str(hook/'10-paths.sh')],input=password,text=True,capture_output=True)
    if result.returncode:
        raise SystemExit('Could not install root-owned init hook; no services changed')
    running = set(subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines())
    restart = [x for x in CONSUMERS if x in running]
    assert 'radarr' in restart and 'sonarr' in restart
    compose = ['docker','compose','--project-directory',str(REPO),'--env-file',str(REPO/'server.conf'),'--env-file',str(REPO/'.env')]
    moved = False
    try:
        run(['docker','stop','--time','30',*restart],stdout=subprocess.DEVNULL)
        os.rename(SOURCE,TARGET)  # no traversal, copying, or file reads
        moved = True
        SOURCE.symlink_to('media/downloads',target_is_directory=True)
        run(compose+['-f',str(REPO/'docker-compose.yml'),'up','-d','--no-deps','--force-recreate','radarr','sonarr'])
        others = [x for x in restart if x not in ['radarr','sonarr']]
        if others: run(['docker','start',*others],stdout=subprocess.DEVNULL)
    except Exception:
        run(['docker','stop','--time','30',*restart],stdout=subprocess.DEVNULL)
        if moved:
            if SOURCE.is_symlink(): SOURCE.unlink()
            os.rename(TARGET,SOURCE)
        run(compose+['-f',str(backup/'compose.before.yml'),'up','-d','--no-deps','--force-recreate','radarr','sonarr'])
        others = [x for x in restart if x not in ['radarr','sonarr']]
        if others: run(['docker','start',*others],stdout=subprocess.DEVNULL)
        raise
    print('PASS opaque directory rename; legacy paths preserved; consumers restarted')
    print('Configuration rollback:',backup)


if __name__ == '__main__': main()
