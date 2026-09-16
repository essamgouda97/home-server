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
