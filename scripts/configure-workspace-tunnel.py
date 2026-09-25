#!/usr/bin/env python3
"""Mac: create a narrow public tunnel using existing authorized Cloudflare access.

Never outputs API/tunnel credentials. DNS conflicts fail closed. Re-run after
origin configuration is verified; only two named public hosts are published.
"""
import base64,json,os,re,secrets,shlex,subprocess,urllib.request,urllib.parse,urllib.error
from pathlib import Path
from datetime import datetime,timezone
HOSTS=['workspace.egouda.xyz','signin.egouda.xyz']
NAME='home-shared-workspace'

def main():
    os.umask(0o077)
    match=re.search(r'^\s*(?:export\s+)?CLOUDFLARE_API_TOKEN\s*=\s*(.+)$',(Path.home()/'.zshrc').read_text(),re.M)
    if not match:raise SystemExit('Existing Cloudflare credential missing')
    token=shlex.split(match[1],comments=True)[0]
    if '$' in token or '`' in token:raise SystemExit('Cloudflare credential is not a literal assignment')
    def api(method,path,data=None):
        req=urllib.request.Request('https://api.cloudflare.com/client/v4'+path,method=method,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=30) as r:value=json.load(r)
        except urllib.error.HTTPError as e:raise RuntimeError('Cloudflare API refused '+method+' (HTTP '+str(e.code)+')') from None
        if not value.get('success'):raise RuntimeError('Cloudflare operation failed')
        return value['result']
    zone=api('GET','/zones?name=egouda.xyz')[0];account=zone['account']['id'];base='/accounts/'+account+'/cfd_tunnel'
    backups=Path.home()/'.local/state/home-server-maintenance/workspace-cloudflare'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    backups.mkdir(parents=True,mode=0o700)
    tunnels=api('GET',base+'?is_deleted=false&name='+NAME)
    tunnel=next((t for t in tunnels if t['name']==NAME),None)
    if not tunnel:tunnel=api('POST',base,{'name':NAME,'config_src':'cloudflare','tunnel_secret':base64.b64encode(secrets.token_bytes(32)).decode()})
    # This API explicitly supports non-browser clients. Disable only the
    # browser-header heuristic on these two hosts; origin auth and WAF remain.
    rulesbase='/zones/'+zone['id']+'/rulesets'
    sets=api('GET',rulesbase)
    settings=next((r for r in sets if r.get('phase')=='http_config_settings' and r.get('kind')=='zone'),None)
    rule={'ref':'shared_workspace_machine_clients','description':'Workspace supports authenticated HTTP agents','expression':'(http.host in {"workspace.egouda.xyz" "signin.egouda.xyz"})','action':'set_config','action_parameters':{'bic':False},'enabled':True}
    if settings:
        old=api('GET',rulesbase+'/'+settings['id']);(backups/'config-rules-before.json').write_text(json.dumps(old))
        existing=next((r for r in old.get('rules',[]) if r.get('ref')==rule['ref']),None)
        if existing:api('PATCH',rulesbase+'/'+settings['id']+'/rules/'+existing['id'],rule)
        else:api('POST',rulesbase+'/'+settings['id']+'/rules',rule)
    else:
        api('POST',rulesbase,{'name':'Site configuration','kind':'zone','phase':'http_config_settings','rules':[rule]})
    tid=tunnel['id'];target=tid+'.cfargotunnel.com'
    records={h:api('GET','/zones/'+zone['id']+'/dns_records?'+urllib.parse.urlencode({'name':h})) for h in HOSTS}
    for host,items in records.items():
        if items and not (len(items)==1 and items[0]['type']=='CNAME' and items[0]['content']==target):raise RuntimeError('Existing DNS record conflicts: '+host)
    (backups/'dns-before.json').write_text(json.dumps(records))
    before=api('GET',base+'/'+tid+'/configurations');(backups/'tunnel-before.json').write_text(json.dumps(before))
    ingress=[{'hostname':h,'service':'https://npm:443','originRequest':{'originServerName':'auth.home.egouda.xyz','httpHostHeader':h,'connectTimeout':10}} for h in HOSTS]
    ingress.append({'service':'http_status:404'})
    api('PUT',base+'/'+tid+'/configurations',{'config':{'ingress':ingress}})
    tunnel_token=api('GET',base+'/'+tid+'/token')
    command="umask 077; cat > ~/.config/home-server/secrets/workspace/tunnel-token"
    r=subprocess.run(['ssh','home-server',command],input=tunnel_token.encode(),capture_output=True)
    if r.returncode:raise RuntimeError('Could not stage tunnel token')
    # Start connector before routing public DNS. The ingress backend enforces
    # central browser auth or scoped machine auth, with no general proxy bypass.
    r=subprocess.run(['ssh','home-server','cd ~/workspace/home-server && docker compose -f compose.workspace-tunnel.yml up -d && (docker network connect shared-workspace_public npm || true)'],capture_output=True)
    if r.returncode:raise RuntimeError('Tunnel startup failed; DNS not published')
    connected=subprocess.run(['ssh','home-server',"docker network inspect shared-workspace_public --format '{{range .Containers}}{{.Name}} {{end}}'"],capture_output=True,text=True)
    if connected.returncode or 'npm' not in connected.stdout.split() or 'workspace-tunnel' not in connected.stdout.split():raise RuntimeError('Tunnel origin network incomplete; DNS not published')
    for host,items in records.items():
        if not items:api('POST','/zones/'+zone['id']+'/dns_records',{'type':'CNAME','name':host,'content':target,'proxied':True,'ttl':1,'comment':'Shared Workspace public ingress; explicit authenticated routes'})
    print('Published authenticated public Workspace and central sign-in endpoints.')
    print('Tunnel:',tid)
if __name__=='__main__':main()
