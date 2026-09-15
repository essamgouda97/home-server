#!/usr/bin/env python3
"""Repair Homarr probes while preserving public links and existing board layout."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3
import uuid
from urllib.parse import quote

PROBES = {
    'jellyfin': 'http://jellyfin:8096/health',
    'vue': 'http://jellyfin-vue:80',
    'requests': 'http://jellyseerr:5055',
    'sonarr': 'http://sonarr:8989/ping',
    'radarr': 'http://radarr:7878/ping',
    'torrents': 'http://vpn-gateway:15080',
    'prowlarr': 'http://prowlarr:9696/ping',
    'status': 'http://uptime-kuma:3001',
    'portainer': 'http://portainer:9000/api/status',
    'nzbget': 'http://nzbget:6789',
    'speedtest': 'http://speedtest-tracker:80',
    'ods': 'http://ods-dashboard:3001',
    'chat': 'http://ods-webui:8080',
}

ADDITIONS = [
    ('Jellyfin', 'jellyfin', 'http://jellyfin:8096/health', 'Watch movies and television', 'JF'),
    ('Creative Drive', 'files', 'http://filebrowser:8080/health', 'Browse and upload household files', 'Files'),
    ('Footage Library', 'ingest', 'http://footage-console:8080/health', 'Import and organize camera footage', 'Film'),
    ('Home Assistant', 'assistant', 'http://10.0.0.182:8123', 'Control the home and local voice assistant', 'HA'),
    ('Life Dashboard', 'life', 'http://life-dashboard:3000', 'Personal planning and finances', 'Life'),
    ('Private Whiteboard', 'draw', 'http://excalidraw:3000/health', 'Saved Excalidraw boards and live Codex drawing', 'Draw'),
    ('Pi-hole DNS', 'dns', 'http://pihole:80/admin/', 'Local DNS and ad blocking; staged test service', 'DNS'),
]

def main():
    os.umask(0o077)
    database = Path('/mnt/server/homarr/appdata/db/db.sqlite')
    backup_dir = Path.home() / '.local/state/home-server-maintenance/dashboard'
    backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with sqlite3.connect(database) as db:
        db.execute('PRAGMA foreign_keys=ON')
        with sqlite3.connect(backup_dir / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.sqlite')) as backup:
            db.backup(backup)
        db.execute('BEGIN IMMEDIATE')
        for host, probe in PROBES.items():
            db.execute('UPDATE app SET ping_url=? WHERE rtrim(href,"/") IN (?,?)',
                       (probe, 'http://' + host + '.lan', 'https://' + host + '.home.egouda.xyz'))
        board = db.execute('SELECT id FROM board WHERE name=?', ('home-server',)).fetchone()[0]
        section = db.execute('SELECT id FROM section WHERE board_id=? AND kind=?', (board, 'empty')).fetchone()[0]
        layouts = db.execute('SELECT id,column_count FROM layout WHERE board_id=?', (board,)).fetchall()
        positions = {lid: [0, db.execute('SELECT COALESCE(MAX(y_offset+height),0) FROM item_layout WHERE layout_id=? AND section_id=?', (lid,section)).fetchone()[0]] for lid,_ in layouts}
        for name, host, probe, description, short in ADDITIONS:
            href = 'http://' + host + '.lan'
            secure_href = 'https://' + host + '.home.egouda.xyz'
            app = db.execute('SELECT id FROM app WHERE rtrim(href,"/") IN (?,?)', (href,secure_href)).fetchone()
            if Path('/mnt/server/npm/data/nginx/custom/home-server/household-https.conf').exists():
                href = secure_href
            app_id = app[0] if app else uuid.uuid4().hex[:24]
            if not app:
                icon = 'data:image/svg+xml,' + quote('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80"><rect width="80" height="80" rx="16" fill="#36354a"/><text x="40" y="47" text-anchor="middle" font-family="sans-serif" font-size="22" fill="white">'+short+'</text></svg>')
                db.execute('INSERT INTO app (id,name,description,icon_url,href,ping_url) VALUES (?,?,?,?,?,?)', (app_id,name,description,icon,href,probe))
            db.execute('UPDATE app SET ping_url=? WHERE id=?', (probe, app_id))
            if any(json.loads(row[0]).get('json',{}).get('appId') == app_id for row in db.execute('SELECT options FROM item WHERE board_id=? AND kind="app"', (board,))):
                continue
            item_id = uuid.uuid4().hex[:24]
            db.execute('INSERT INTO item (id,board_id,kind,options) VALUES (?,?,?,?)', (item_id,board,'app',json.dumps({'json':{'appId':app_id}})))
            for lid, columns in layouts:
                x,y=positions[lid]
                db.execute('INSERT INTO item_layout (item_id,section_id,layout_id,x_offset,y_offset,width,height) VALUES (?,?,?,?,?,?,?)', (item_id,section,lid,x,y,1,1))
                positions[lid] = [x+1,y] if x+1 < columns else [0,y+1]
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    print('Updated internal probes; browser links and board layout preserved.')

if __name__ == '__main__':
    main()
