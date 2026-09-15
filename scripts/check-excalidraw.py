#!/usr/bin/env python3
"""Server-side private HTTP/MCP checks. --seed adds a first architecture board."""
import argparse
import base64
import json
from pathlib import Path
import select
import subprocess
import time
import urllib.request

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', action='store_true')
    parser.add_argument('--fit', action='store_true', help='With --seed, fit the architecture board in its open browser')
    args = parser.parse_args()
    password = (Path.home()/'.config/home-server/secrets/creative_password').read_text().strip()
    headers = {'Host':'draw.lan', 'Authorization':'Basic '+base64.b64encode(('egouda:'+password).encode()).decode()}
    def api(path, data=None, tenant=None):
        h = {**headers, 'Content-Type':'application/json', 'Origin':'http://draw.lan'}
        if tenant: h['X-Tenant-Id'] = tenant
        request = urllib.request.Request('http://127.0.0.1'+path, headers=h, data=None if data is None else json.dumps(data).encode())
        with urllib.request.urlopen(request, timeout=20) as response: return json.load(response)
    assert api('/health')['status']=='healthy'
    print('PASS authenticated whiteboard HTTP')
    process = subprocess.Popen(['docker','exec','-i','excalidraw','node','dist/index.js'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    def send(value):
        process.stdin.write(json.dumps(value)+'\n'); process.stdin.flush()
    def rpc(ident, method, params):
        send(dict(jsonrpc='2.0', id=ident, method=method, params=params))
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if select.select([process.stdout],[],[],1)[0]:
                line=process.stdout.readline()
                if not line: raise RuntimeError('MCP exited')
                reply=json.loads(line)
                if reply.get('id')==ident:
                    assert 'error' not in reply and not reply.get('result',{}).get('isError'), 'MCP request failed'
                    return reply['result']
        raise RuntimeError('MCP request timed out')
    try:
        rpc(1,'initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'home-server-check','version':'1'}})
        send({'jsonrpc':'2.0','method':'notifications/initialized'})
        tools=rpc(2,'tools/list',{})['tools']
        assert len(tools)>=30 and not any(t['name']=='export_to_excalidraw_url' for t in tools)
        print('PASS MCP handshake and local-only tool inventory')
        if args.seed:
            tenants=api('/api/tenants')['tenants']
            board=next((t for t in tenants if t['name']=='Home server architecture'),None)
            if not board: board=api('/api/boards',{'name':'Home server architecture'})['tenant']
            rpc(3,'tools/call',{'name':'switch_tenant','arguments':{'tenantId':board['id']}})
            elements=api('/api/elements',tenant=board['id'])['elements']
            if not elements:
                boxes=[('devices','Household devices',0,100),('dns','Local DNS\ndnsmasq :53\nPi-hole test :1053',320,0),('proxy','Nginx Proxy Manager\nClean .lan URLs',320,250),('apps','Media + Home Assistant\nFiles + Life + ODS',680,120),('draw','Private Excalidraw\nSSD database + Codex MCP',680,350)]
                elements=[dict(id=i,type='rectangle',text=text,x=x,y=y,width=250,height=120,backgroundColor='#e7f5ff',strokeColor='#1971c2',fontSize=18) for i,text,x,y in boxes]
                for start,end in [('devices','dns'),('devices','proxy'),('proxy','apps'),('proxy','draw')]:
                    elements.append(dict(type='arrow',x=0,y=0,startElementId=start,endElementId=end,endArrowhead='arrow'))
                rpc(4,'tools/call',{'name':'batch_create_elements','arguments':{'elements':elements}})
            actual=api('/api/elements',tenant=board['id'])['elements']
            assert len(actual)>=9
            print('PASS architecture board stored through MCP:',len(actual),'elements')
            if args.fit:
                result=rpc(5,'tools/call',{'name':'set_viewport','arguments':{'scrollToContent':True}})
                print('PASS live MCP viewport command')
        with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1/',headers=headers),timeout=10) as response:
            policy=response.headers.get('Content-Security-Policy','')
            assert "connect-src 'self' ws://draw.lan" in policy
        print('PASS browser connection policy restricts external requests')
    finally:
        process.stdin.close()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.terminate(); process.wait(timeout=5)

if __name__=='__main__': main()
