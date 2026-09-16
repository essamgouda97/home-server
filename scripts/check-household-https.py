#!/usr/bin/env python3
"""Read-only HTTPS, link, origin and WebSocket checks on the home server."""
from pathlib import Path
from service_credentials import service_password
import base64
import json
import re
import socket
import ssl
import urllib.error
import urllib.request

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args): return None

def main():
    context = ssl.create_default_context()
    opener = urllib.request.build_opener(NoRedirect,urllib.request.HTTPSHandler(context=context))
    secret = service_password('draw')
    auth = 'Basic '+base64.b64encode(('egouda:'+secret).encode()).decode()
    def get(host,path='/',authenticated=False,method='GET',origin=None):
        name=host.split('.')[0]
        specific_auth='Basic '+base64.b64encode(('egouda:'+service_password(name)).encode()).decode()
        headers = {'Authorization':specific_auth} if authenticated else {}
        if origin: headers['Origin']=origin
        request = urllib.request.Request('https://'+host+path,headers=headers,method=method)
        try: return opener.open(request,timeout=20)
        except urllib.error.HTTPError as error: return error
    config = Path('/mnt/server/npm/data/nginx/custom/home-server/household-https.conf').read_text()
    hosts = sorted(set(re.findall(r'server_name\s+([a-z0-9.-]+);',config)))
    assert len(hosts)>=20
    for host in hosts:
        with get(host) as response:
            assert response.code in [200,301,302,303,307,308,401], (host,response.code)
        print('PASS trusted HTTPS',host)
    for host,path in [('ods.home.egouda.xyz','/api/external-links'),('ingest.home.egouda.xyz','/')]:
        with get(host,path,True) as response:
            assert response.code==200
            text=response.read().decode()
            assert not re.search(r'https?://[a-z0-9.-]+\.lan\b',text)
        print('PASS household links',host)
    host='draw.home.egouda.xyz'
    with get(host,'/api/tenants',True) as response:
        assert response.code==200
        assert len(json.load(response)['tenants'])>=1
    with get(host,'/api/boards',True,'POST','https://untrusted.invalid') as response:
        assert response.code==403
    with socket.create_connection((host,443),timeout=10) as connection:
        with context.wrap_socket(connection,server_hostname=host) as secure:
            request = ('GET / HTTP/1.1\r\nHost: '+host+'\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\nOrigin: https://'+host+'\r\nAuthorization: '+auth+'\r\n\r\n')
            secure.sendall(request.encode())
            assert secure.recv(4096).split(b'\r\n',1)[0]==b'HTTP/1.1 101 Switching Protocols'
    print('PASS saved boards, cross-origin rejection and secure whiteboard WebSocket')

if __name__=='__main__': main()
