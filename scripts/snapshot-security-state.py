#!/usr/bin/env python3
"""Create a private app-config snapshot with SQLite online backups (run on server)."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile

DATA=Path('/mnt/server')
SOURCES={
 'infrastructure/env':Path('/home/egouda/workspace/home-server/.env'),
 'infrastructure/server.conf':Path('/home/egouda/workspace/home-server/server.conf'),
 'secrets':Path('/home/egouda/.config/home-server/secrets'),
 'npm/data':DATA/'npm/data', 'npm/letsencrypt':DATA/'npm/letsencrypt',
 'homarr':DATA/'homarr/appdata/db',
 'jellyfin/config':DATA/'jellyfin/config/config',
 'jellyfin/data':DATA/'jellyfin/config/data/data',
 'sonarr':DATA/'sonarr/data', 'radarr':DATA/'radarr/config',
 'prowlarr':DATA/'prowlarr/data', 'qbittorrent':DATA/'qbittorrent/config',
 'nzbget':DATA/'nzbget', 'filebrowser':DATA/'filebrowser',
 'homeassistant':DATA/'homeassistant',
 'excalidraw':Path('/srv/mergerfs/ssd/excalidraw'),
 'life/data':Path('/srv/mergerfs/ssd/life-dashboard/data'),
 'life/docs':Path('/srv/mergerfs/ssd/life-dashboard/docs'),
 'jellyseerr':DATA/'jellyseerr/config',
 'authelia':Path('/srv/mergerfs/ssd/authelia'),
 'grafana':Path('/srv/mergerfs/ssd/monitoring/grafana'),
 'portainer':DATA/'portainer/data', 'uptime-kuma':DATA/'uptimekuma/data',
 'speedtest':DATA/'speedtest-tracker/config',
 'pihole':DATA/'pihole', 'dnsmasq':DATA/'dnsmasq',
}
EXCLUDE={'logs','log','cache','Cache','Backups','backups','MediaCover','metadata','transcodes','node_modules','runtime'}

def main():
 os.umask(0o077)
 root=Path('/home/egouda/.local/state/home-server-security-backups');root.mkdir(parents=True,exist_ok=True,mode=0o700)
 name=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
 target=root/(name+'.tar');sqlite_count=0;included=[]
 with tempfile.TemporaryDirectory(dir=root,prefix='staging-') as tmp:
  stage=Path(tmp)
  for prefix,source in SOURCES.items():
   if not source.exists():continue
   included.append(prefix)
   paths=[source] if source.is_file() else source.rglob('*')
   for p in paths:
    relative=Path() if source.is_file() else p.relative_to(source)
    if any(part in EXCLUDE for part in relative.parts) or p.is_symlink() or not p.is_file() or p.name.endswith(('-wal','-shm')):continue
    dest=stage/prefix/relative;dest.parent.mkdir(parents=True,exist_ok=True)
    with p.open('rb') as f:magic=f.read(16)
    if magic==b'SQLite format 3\x00':
     with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) as live,sqlite3.connect(dest) as saved:
      live.backup(saved)
      assert saved.execute('PRAGMA quick_check').fetchone()[0]=='ok',prefix
     sqlite_count+=1
    else:shutil.copy2(p,dest)
  (stage/'manifest.json').write_text(json.dumps({'created':name,'included':included,'sqlite_databases':sqlite_count,'scope':'application configuration; excludes media, original footage, logs and caches','revision':subprocess.check_output(['git','-C','/home/egouda/workspace/home-server','rev-parse','HEAD'],text=True).strip()},indent=2))
  with tarfile.open(target,'w') as archive:archive.add(stage,arcname='recovery')
 target.chmod(0o600);os.chown(target,1000,1000);os.chown(root,1000,1000)
 print(str(target))

if __name__=='__main__':main()
