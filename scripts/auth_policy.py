"""Shared gateway policy compiler. No service gets an implicit auth bypass."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
INCLUDE='/data/nginx/custom/home-auth'
MARKER='# home-auth-managed'

def services():
    entries=json.loads((ROOT/'config/services.json').read_text())['services']
    result={}
    for entry in entries:
        url=urlsplit(entry['url']);host=url.hostname
        if url.scheme!='https' or not host or not (host=='home.egouda.xyz' or host.endswith('.home.egouda.xyz')) or url.username or url.query:
            raise ValueError('Invalid household browser URL: '+entry['id'])
        policy=entry.get('auth',{})
        if policy.get('mode')!='gateway' or policy.get('access') not in ('owner','household') or policy.get('adapter') not in ('gateway','native','trusted-header','oidc','upstream-basic'):
            raise ValueError('Missing supported auth policy: '+entry['id'])
        if host in result:raise ValueError('Duplicate service hostname: '+host)
        result[host]=entry
    return result

def closing(text, start):
    depth=0;quote=None;escape=False;comment=False
    for i in range(start,len(text)):
        c=text[i]
        if comment:
            if c=='\n':comment=False
            continue
        if escape:escape=False;continue
        if c=='\\':escape=True;continue
        if quote:
            if c==quote:quote=None
            continue
        if c in "\"'":quote=c;continue
        if c=='#':comment=True;continue
        if c=='{':depth+=1
        if c=='}':
            depth-=1
            if depth==0:return i
    raise ValueError('Unbalanced nginx block')

def render(text, policies=None):
    policies=services() if policies is None else policies
    changes=[];covered=set()
    for m in re.finditer(r'(?m)^\s*server\s*\{',text):
        start=text.index('{',m.start());end=closing(text,start)
        body=text[start+1:end]
        names=re.search(r'\bserver_name\s+([^;]+);',body)
        if not names:continue
        hosts=names[1].split()
        https=bool(re.search(r'\blisten\s+443\s+ssl',body))
        if not https:
            if hosts in (['jellyfin.lan'],['assistant.lan']) and '# home-auth-native-client' not in body:
                body='\n    # home-auth-native-client\n    auth_request off;\n'+body
                changes.append((start+1,end,body))
                continue
            # Keep media native client endpoints; their own credentials remain required.
            if len(hosts)==1 and hosts[0].endswith('.lan') and hosts[0] not in ('jellyfin.lan','assistant.lan'):
                host='home.egouda.xyz' if hosts[0]=='home.lan' else hosts[0][:-4].replace('.','-')+'.home.egouda.xyz'
                if host in policies and '# home-auth-redirect' not in body:
                    body='\n    # home-auth-redirect\n    return 308 https://'+host+'$request_uri;\n'+body
                    changes.append((start+1,end,body))
            continue
        if hosts==['auth.home.egouda.xyz']:continue
        if not all(host in policies for host in hosts):
            raise ValueError('HTTPS host is not registered for authentication: '+','.join(hosts))
        covered.update(hosts)
        if MARKER in body:continue
        body=re.sub(r'(?m)^\s*auth_basic(?:_user_file)?\s+[^;]+;\s*$', '',body)
        if re.search(r'\bauth_request\s|\bsatisfy\s+any',body):
            raise ValueError('Review existing authorization rules: '+','.join(hosts))
        body='\n    '+MARKER+'\n    include '+INCLUDE+'/location.conf;\n'+body
        # Proxy headers must be at the same level as the app's own proxy headers.
        body=re.sub(r'\b(proxy_pass\s+[^;]+;|include\s+conf\.d/include/proxy\.conf;)',lambda m:'include '+INCLUDE+'/identity.conf;\n    '+m[0],body)
        # NZBGet requires Basic auth upstream; inject only after gateway authorization.
        if hosts==['nzbget.home.egouda.xyz']:
            body=body.replace('include '+INCLUDE+'/identity.conf;', 'include '+INCLUDE+'/identity.conf;\n    include '+INCLUDE+'/nzbget.conf;')
        if hosts==['torrents.home.egouda.xyz']:
            # qBittorrent 5.2 accepts Basic auth from an identity-aware proxy.
            # The generated include is mode 600 and never reaches the browser.
            body=body.replace('include '+INCLUDE+'/identity.conf;', 'include '+INCLUDE+'/identity.conf;\n    include '+INCLUDE+'/qbittorrent.conf;')
        if hosts==['coach.home.egouda.xyz']:
            # Exact machine routes require the app's constant-time Bearer key
            # check. All browser routes retain the household gateway policy.
            for endpoint in ('context','snapshot','events'):
                body+='\n    location = /api/device/'+endpoint+' {\n        auth_request off;\n        include '+INCLUDE+'/identity.conf;\n        set $coach_device_backend http://health-coach:8099;\n        proxy_pass $coach_device_backend;\n        proxy_set_header Host $host;\n        proxy_set_header X-Forwarded-Proto https;\n    }\n'
        if hosts==['people.home.egouda.xyz']:
            # The only unauthenticated browser path is a one-use bearer invite.
            # The backend validates its 256-bit token and never accepts client
            # identity headers on this route.
            body+='\n    location /join/ {\n        auth_request off;\n        include /data/nginx/custom/home-server/people-key.conf;\n        proxy_set_header Host $host;\n        proxy_set_header Remote-User "";\n        proxy_set_header Remote-Groups "";\n        proxy_set_header X-Forwarded-Proto https;\n        proxy_pass http://172.18.0.1:8766;\n        proxy_read_timeout 190s;\n    }\n'
        changes.append((start+1,end,body))
    for start,end,body in reversed(changes):text=text[:start]+body+text[end:]
    return text,covered


def protect_if_enabled(data):
    """Used by every proxy generator before validation/reload, including legacy aliases."""
    if Path('/mnt/server/npm/data/nginx/custom/home-auth/location.conf').exists():
        return render(data.decode())[0].encode()
    return data
