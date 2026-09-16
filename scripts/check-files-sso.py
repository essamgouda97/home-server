#!/usr/bin/env python3
"""Prove storage opens from the gateway identity; spoofed identity cannot elevate."""
import json,urllib.request,urllib.error,base64,socket,subprocess
from auth_session import AuthSession
BASE='https://files.home.egouda.xyz'
with AuthSession() as s:
    req=urllib.request.Request(BASE+'/api/login',data=b'{}',headers={'Content-Type':'application/json','Origin':BASE,'Remote-User':'mgouda'})
    with s.opener.open(req,timeout=20) as r:token=r.read().decode().strip('"')
    claims=json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='))
    assert claims['user']['username']=='egouda','Client-supplied user header was trusted'
    assert claims['user']['perm']['admin'] is True
    with s.opener.open(urllib.request.Request(BASE+'/api/resources/',headers={'X-Auth':token}),timeout=20) as r:assert r.status==200
    print('PASS central credential only -> existing file-storage owner; forged user header overwritten')
for host in ['127.0.0.1','10.0.0.182']:
    try:
        socket.create_connection((host,8082),timeout=2).close();raise AssertionError('Storage backend port exposed')
    except OSError:pass
state=json.loads(subprocess.run(['docker','network','inspect','home-server_files_auth'],capture_output=True,text=True,check=True).stdout)[0]
assert state['Internal'] and {v['Name'] for v in state['Containers'].values()}=={'npm','filebrowser'}
print('PASS storage backend accessible only through isolated proxy network')
