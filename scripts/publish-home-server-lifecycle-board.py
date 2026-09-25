#!/usr/bin/env python3
"""Create an editable Draw board explaining storage, access and releases.

The board is additive: never replace an existing board or human edits. Run on
home-server, where the local Excalidraw MCP container and AuthSession are ready.
"""
import json
import select
import subprocess
import time
import urllib.request
from auth_session import AuthSession

TITLE='Home server — storage, access & releases'
ORIGIN='https://draw.home.egouda.xyz'
PREFIX='home-lifecycle-'
INK='#1e293b'
BLUE='#e0f2fe'
GREEN='#dcfce7'
VIOLET='#ede9fe'
AMBER='#fef3c7'
SLATE='#f1f5f9'

def box(key,caption,x,y,w=470,h=165,fill=BLUE,size=19):
    return {'id':PREFIX+key,'type':'rectangle','text':caption,'x':x,'y':y,
            'width':w,'height':h,'fontSize':size,'fontFamily':2,'roughness':0,
            'strokeWidth':1.5,'strokeColor':INK,'backgroundColor':fill}

def heading(caption,x,y,size=32,color=INK):
    return {'type':'text','text':caption,'x':x,'y':y,'fontSize':size,
            'fontFamily':2,'roughness':0,'strokeColor':color}

def arrow(start,end,color='#64748b'):
    return {'type':'arrow','x':0,'y':0,'startElementId':PREFIX+start,
            'endElementId':PREFIX+end,'endArrowhead':'arrow','roughness':0,
            'strokeWidth':2,'strokeColor':color}

def design():
    x=[0,510,1020,1530,2040]
    e=[heading('HOME SERVER  /  WHERE IT LIVES & HOW IT RUNS',0,0,42),
       heading('Observed 18 Sep 2026  •  Data survives container replacement because it lives in host directories and volumes.',0,67,20),
       heading('1   FILESYSTEM & APPLICATION DATA',0,145)]

    e.extend([
      box('os','OS DISK  /dev/sda3\nUbuntu, Docker image layers\n/home/egouda/workspace\nCode checkouts live here',x[0],210,470,190,SLATE),
      box('hdd','HDD BRANCH  /dev/sdb1\n/srv/mergerfs/hdd\nCapacity branch of the pool\nNot a separate app URL',x[1],210,470,190,BLUE),
      box('ssd','SSD BRANCH  /dev/sdc1\n/srv/mergerfs/ssd\nFast branch of the pool\nAlso holds dedicated state',x[2],210,470,190,BLUE),
      box('pool','MERGED VIEW  /mnt\nhdd:ssd via mergerfs\n/mnt/server is the common\napp-data and media root',x[3],210,470,190,GREEN),
      box('mounts','DOCKER BIND MOUNTS\nHost folders appear inside apps\nContainers can be recreated\nwithout moving their data',x[4],210,470,190,GREEN),
      arrow('hdd','pool'),arrow('ssd','pool'),arrow('pool','mounts'),

      box('code','VERSIONED SETUP\n~/workspace/home-server\nCompose, scripts, Nginx templates,\nservice catalog and policies\nGit tracks setup, not app databases',x[0],455,470,225,VIOLET,18),
      box('private','PRIVATE CREDENTIALS\n~/.config/home-server/secrets\n1Password holds owner logins\nRuntime keys stay outside Git\nOnly selected containers read them',x[1],455,470,225,AMBER,18),
      box('pooled-data','POOLED APP DATA  /mnt/server\nMedia, downloads, Jellyfin\nHomarr, *arr, qBittorrent, NPM,\nHome Assistant and other configs\nActual files may sit on either disk',x[2],455,470,225,GREEN,18),
      box('ssd-data','SSD-ONLY STATE\n/srv/mergerfs/ssd/creative\n.../excalidraw (boards + assets)\n.../authelia + .../monitoring\nLife Dashboard data also on SSD',x[3],455,470,225,GREEN,18),
      box('other-trees','SEPARATE SOURCE / RUNTIME\n~/workspace/personal-finances\n~/.local/share/home-server/excalidraw\n~/workspace/ods-upstream + ~/ods\nSome apps are separate Compose stacks',x[4],455,470,225,VIOLET,18),

      box('media-group','MEDIA & DOWNLOADS\nJellyfin / Moonfin • Requests\nSonarr • Radarr • Prowlarr\nqBittorrent • NZBGet\nFiles: /mnt/server/media + downloads',0,735,590,225,BLUE,18),
      box('creative-group','CREATIVE & FAMILY\nLocal Drive • Draw • Footage\nLife Dashboard • Health Coach\nFiles: Creative / Draw SSD paths;\nLife source and data are separate',635,735,590,225,BLUE,18),
      box('home-group','HOME, ADMIN & METRICS\nHomarr • Home Assistant • People\nPortainer • DNS • Print • Status\nGrafana / Prometheus on SSD\nApp state via mounts, not image layers',1270,735,590,225,BLUE,18),
      box('ods-group','AI / ODS TOOLS\nODS dashboard + chat, models,\nsearch, n8n, Langfuse and workers\nSeparate ~/ods runtime and volumes\nRegistered browser tools get HTTPS',1905,735,590,225,BLUE,18),
      heading('Backups: private server snapshots + encrypted Mac configuration backups. Media and original footage lack an independent off-server backup.',0,985,18,'#92400e'),

      heading('2   LOCAL & REMOTE REQUEST PATHS',0,1060),
      box('home-client','AT HOME\nPhone / laptop on household Wi-Fi\nOpen home.egouda.xyz or an\napp.home.egouda.xyz link',x[0],1125,470,180,BLUE),
      box('dns','DNS ANSWER\nCloudflare DNS-only A records\nhome + *.home.egouda.xyz\n→ private 10.0.0.182',x[1],1125,470,180,BLUE),
      box('edge','PRIVATE HTTPS EDGE\nNginx Proxy Manager on :443\nWildcard TLS certificate renewed\nwith Cloudflare DNS-01',x[2],1125,470,180,GREEN),
      box('auth','BROWSER GATEWAY\nAuthelia checks session + grants\nper registered service\nNative app login may still follow',x[3],1125,470,180,GREEN),
      box('app','INTERNAL BACKENDS\nNginx routes by hostname to\nDocker proxy / isolated networks\nHomarr links; metrics probe health',x[4],1125,470,180,GREEN),
      arrow('home-client','dns'),arrow('dns','edge'),arrow('edge','auth'),arrow('auth','app'),

      box('away-client','AWAY: OWNER BROWSER\nCellular / other Wi-Fi\nConnect the owner Tailscale first',x[0],1370,470,155,VIOLET),
      box('tailscale','PRIVATE TAILSCALE ROUTE\nOwner-approved server /32 + DNS\nSame household HTTPS links\nShared family grant is media-only',x[1],1370,470,155,VIOLET),
      box('not-public','CLOUDFLARE IS DNS ONLY\nPrivate A record is published;\nit is not internet-routable\nNo Tunnel, Funnel or public proxy',x[2],1370,470,155,AMBER),
      box('native','NATIVE CLIENT EXCEPTION\nMoonfin: private Tailscale Serve\n→ Jellyfin :8096 + native login\nLAN TV can use 10.0.0.182:8096',x[3],1370,470,155,AMBER),
      box('protocols','OTHER PRIVATE PROTOCOLS\nSMB / Finder, SSH, DNS and\nHome Assistant native clients\nuse their own auth + LAN/VPN',x[4],1370,470,155,AMBER),
      arrow('away-client','tailscale'),arrow('tailscale','edge'),

      heading('3   HOW A CHANGE BECOMES A RUNNING RELEASE',0,1635),
      box('edit','EDIT & REVIEW\nMac home-server checkout\nChange Compose, source or policy\nKeep secrets and backups out of Git',0,1700,385,205,VIOLET,18),
      box('git','VERSION CONTROL\nCommit + push to GitHub main\nPreserve unrelated working changes\nKeep Mac/server checkouts aligned',420,1700,385,205,VIOLET,18),
      box('server-code','SERVER CHECKOUT\n~/workspace/home-server\nFetch/fast-forward reviewed code\nOther app source trees stay pinned',840,1700,385,205,VIOLET,18),
      box('deploy','APPLY THE CHANGE\nCompose up/build/pull for app\nScoped scripts install proxy/auth\nSystemd units/timers where needed',1260,1700,385,205,GREEN,18),
      box('runtime','RUNNING RELEASE\nPinned image digest or local build\nDocker process reads mounted data\nWatchtower monitors; no auto-update',1680,1700,385,205,GREEN,18),
      box('verify','VERIFY & RECOVER\nReal HTTPS login / app workflow\nmake check-network + check-server\nSnapshots before migrations',2100,1700,385,205,GREEN,18),
      arrow('edit','git','#7c3aed'),arrow('git','server-code','#7c3aed'),
      arrow('server-code','deploy','#7c3aed'),arrow('deploy','runtime','#7c3aed'),
      arrow('runtime','verify','#7c3aed'),
      box('new-app','NEW BROWSER APP CONTRACT\nPersistent host data → catalog entry in config/services.json → owner-only gateway route by default\n→ native identity adapter if needed → actual HTTPS login test → Homarr tile + metrics probe',0,1980,2485,135,SLATE,20),
      heading('Source map: server.conf • docker-compose.yml / compose.*.yml • config/services.json • docs/server-operations.md • docs/security-hardening.md',0,2160,18),
      heading('The diagram groups browser apps by role. Worker/database containers are shown in the runtime and metrics, not as broken Homarr links.',0,2195,18),
    ])
    return e

def main():
    elements=design()
    with AuthSession() as session:
        def api(path,data=None,board=None):
            headers={'Content-Type':'application/json','Origin':ORIGIN}
            if board:headers['X-Tenant-Id']=board
            request=urllib.request.Request(ORIGIN+path,data=None if data is None else json.dumps(data).encode(),headers=headers)
            with session.opener.open(request,timeout=30) as response:return json.load(response)
        tenants=api('/api/tenants')['tenants']
        existing=next((t for t in tenants if t['name']==TITLE),None)
        if existing:
            saved=api('/api/elements',board=existing['id'])['elements']
            if saved and not globals().get('APPEND_TO_EXISTING',False):
                print('Preserved existing board:',TITLE,'('+str(len(saved))+' elements)')
                print(ORIGIN+'/?board='+existing['id'])
                return
        board=existing or api('/api/boards',{'name':TITLE})['tenant']
        if existing and globals().get('APPEND_TO_EXISTING',False):
            saved_ids={e.get('id') for e in saved}
            elements=[e for e in elements if e.get('id') not in saved_ids]
            if not elements:
                print('PASS verified existing editable board:',ORIGIN+'/?board='+board['id'])
                return
        process=subprocess.Popen(['docker','exec','-i','excalidraw','node','dist/index.js'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
        sequence=0
        def rpc(method,params):
            nonlocal sequence
            sequence+=1
            process.stdin.write(json.dumps({'jsonrpc':'2.0','id':sequence,'method':method,'params':params})+'\n')
            process.stdin.flush()
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                if select.select([process.stdout],[],[],1)[0]:
                    reply=json.loads(process.stdout.readline())
                    if reply.get('id')==sequence:
                        if 'error' in reply or reply.get('result',{}).get('isError'):
                            raise RuntimeError('Draw MCP rejected the operation')
                        return reply['result']
            raise RuntimeError('Draw MCP timed out')
        try:
            rpc('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'home-server-lifecycle-board','version':'1'}})
            process.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n')
            process.stdin.flush()
            rpc('tools/call',{'name':'switch_tenant','arguments':{'tenantId':board['id']}})
            for offset in range(0,len(elements),20):
                rpc('tools/call',{'name':'batch_create_elements','arguments':{'elements':elements[offset:offset+20]}})
            saved=api('/api/elements',board=board['id'])['elements']
            if len(saved)<len(elements):raise RuntimeError('Board was not fully persisted')
            print('PASS saved editable board:',TITLE,'('+str(len(saved))+' elements)')
            print(ORIGIN+'/?board='+board['id'])
        finally:
            process.stdin.close()
            process.wait(timeout=10)

if __name__=='__main__':main()
