#!/usr/bin/env python3
"""Install private whiteboard and Pi-hole routes; validate before graceful reload."""
from datetime import datetime, timezone
from pathlib import Path
from auth_policy import protect_if_enabled
from service_credentials import service_password
import os
import shutil
import subprocess

os.umask(0o077)
root = Path('/mnt/server/npm/data/nginx/custom')
routes = root / 'home-server'
routes.mkdir(parents=True, exist_ok=True)
target = routes / 'design-dns.conf'
hook = root / 'http_top.conf'
backup = Path.home() / '.local/state/home-server-maintenance/proxies' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup.mkdir(parents=True)
previous = {p: p.read_bytes() if p.exists() else None for p in [target, hook]}
for p, data in previous.items():
    if data is not None: (backup / p.name).write_bytes(data)

text = '''map "$request_method:$http_origin" $draw_reject_origin {
    default 1;
    ~^(GET|HEAD|OPTIONS): 0;
    "POST:http://draw.lan" 0;
    "PUT:http://draw.lan" 0;
    "PATCH:http://draw.lan" 0;
    "DELETE:http://draw.lan" 0;
}
map $http_origin $draw_reject_websocket {
    default 1;
    "http://draw.lan" 0;
    "" 0;
}
server {
    listen 80;
    server_name draw.lan;
    auth_basic "Private whiteboard";
    auth_basic_user_file /data/nginx/custom/home-server/draw.htpasswd;
    if ($draw_reject_origin) { return 403; }
    if ($draw_reject_websocket) { return 403; }
    client_max_body_size 20m;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' ws://draw.lan; worker-src 'self' blob:; object-src 'none'; frame-src 'none'" always;
    location / {
        resolver 127.0.0.11 valid=30s;
        set $draw_backend http://excalidraw:3000;
        proxy_pass $draw_backend;
        proxy_set_header Host $host;
        proxy_set_header Authorization "";
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $http_connection;
        proxy_read_timeout 3600s;
        proxy_buffering off;
        proxy_hide_header Access-Control-Allow-Origin;
    }
}
server {
    listen 80;
    server_name dns.lan;
    location = / { return 302 /admin/; }
    location / {
        resolver 127.0.0.11 valid=30s;
        set $pihole_backend http://pihole:80;
        proxy_pass $pihole_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
'''

def write(path, data):
    import shlex
    destination = Path('/data/nginx/custom') / path.relative_to(root)
    tmp = destination.with_suffix('.pending')
    command = 'cat > ' + shlex.quote(str(tmp)) + ' && chmod 644 ' + shlex.quote(str(tmp)) + ' && mv ' + shlex.quote(str(tmp)) + ' ' + shlex.quote(str(destination))
    subprocess.run(['docker', 'exec', '-i', 'npm', 'sh', '-c', command], input=data, check=True)

try:
    hashed = subprocess.run(['openssl','passwd','-6','-stdin'],input=service_password('draw').encode()+b'\n',capture_output=True,check=True).stdout.strip()
    write(routes/'draw.htpasswd', b'egouda:'+hashed+b'\n')
    write(target, protect_if_enabled(text.encode()))
    include = b'include /data/nginx/custom/home-server/*.conf;'
    if include not in (previous[hook] or b''):
        write(hook, (previous[hook] or b'') + b'\n' + include + b'\n')
    subprocess.run(['docker', 'exec', 'npm', 'nginx', '-t'], check=True, capture_output=True)
except Exception:
    for p, data in previous.items():
        write(p, data or b'')
    raise SystemExit('Proxy validation failed; previous configuration restored.')
subprocess.run(['docker', 'exec', 'npm', 'nginx', '-s', 'reload'], check=True, capture_output=True)
print('draw.lan and dns.lan routes installed; Nginx configuration validated.')
