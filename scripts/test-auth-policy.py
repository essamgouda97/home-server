#!/usr/bin/env python3
"""Security regression checks for policy rendering, without production changes."""
from auth_policy import render
p={'life.home.egouda.xyz':{}}
source='''server {
 listen 443 ssl;
 server_name life.home.egouda.xyz;
 auth_basic "private";
 auth_basic_user_file /private/auth;
 location / { proxy_pass http://backend; }
 location /ws { proxy_pass http://backend; }
}'''
r,hosts=render(source,p)
assert hosts==set(p)
assert 'auth_basic' not in r and '/location.conf;' in r
assert r.count('/identity.conf;')==2
assert render(r,p)[0]==r
for text in [source.replace('life.home.egouda.xyz','unknown.home.egouda.xyz'),source.replace('location / {','satisfy any;\n location / {')]:
 try:render(text,p)
 except ValueError:pass
 else:raise AssertionError('Unsafe route was accepted')
legacy='server {\n listen 80;\n server_name life.lan;\n location / { proxy_pass http://backend; }\n}'
r,_=render(legacy,p)
assert 'return 308 https://life.home.egouda.xyz$request_uri;' in r
assert render(r,p)[0]==r
native='server {\n listen 80;\n server_name jellyfin.lan;\n location / { proxy_pass http://jellyfin; }\n}'
r,_=render(native,p)
assert '# home-auth-native-client' in r and 'auth_request off;' in r
print('PASS default deny, unknown-route rejection, legacy redirects, native-client isolation and repeatable rendering')

torrents=source.replace('life.home.egouda.xyz','torrents.home.egouda.xyz')
r,_=render(torrents,{'torrents.home.egouda.xyz':{}})
assert r.count('/qbittorrent.conf;')==2
assert render(r,{'torrents.home.egouda.xyz':{}})[0]==r
managed=r.replace('include '+"/data/nginx/custom/home-auth/qbittorrent.conf;\n    ",'')
upgraded,_=render(managed,{'torrents.home.egouda.xyz':{}})
assert upgraded.count('/qbittorrent.conf;')==2
print('PASS qBittorrent private upstream-auth bridge is present and repeatable')

coach=source.replace('life.home.egouda.xyz','coach.home.egouda.xyz')
r,_=render(coach,{'coach.home.egouda.xyz':{}})
assert r.count('auth_request off;')==3
for endpoint in ('context','snapshot','events'):
 assert 'location = /api/device/'+endpoint+' {' in r
assert 'location /api/device/' not in r
assert render(r,{'coach.home.egouda.xyz':{}})[0]==r
print('PASS Coach machine exceptions are exact, bounded and repeatable')

people=source.replace('life.home.egouda.xyz','people.home.egouda.xyz')
r,_=render(people,{'people.home.egouda.xyz':{}})
assert r.count('auth_request off;')==1
assert 'location /join/ {' in r
assert 'proxy_set_header Remote-User "";' in r
assert 'include '+"/data/nginx/custom/home-auth/identity.conf;" in r
assert render(r,{'people.home.egouda.xyz':{}})[0]==r
print('PASS People owner gateway and exact invitation subtree')
