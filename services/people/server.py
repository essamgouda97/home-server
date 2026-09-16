#!/usr/bin/env python3
"""Small owner console and one-use household enrollment endpoint.

Runs as the server user on the Docker proxy bridge. Nginx authenticates the
owner route; a separate bearer invitation authorizes only new-user enrollment.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from identity_policy import identities

PRIVATE=Path.home()/'.config/home-server/secrets/people'
STATIC=Path(__file__).with_name('static')
OWNER_HOST='people.home.egouda.xyz'
ALLOWED={'homarr','jellyfin','vue','requests','files'}

def atomic_json(path,data):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.pending-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as output:
            json.dump(data,output,indent=2)
            output.write('\n')
            output.flush();os.fsync(output.fileno())
        os.chmod(name,0o600);os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def invite_store():
    path=PRIVATE/'invitations.json'
    return json.loads(path.read_text()) if path.exists() else {'version':1,'invitations':{}}

def valid_grants(grants):
    if not isinstance(grants,list) or not grants or len(grants)!=len(set(grants)) or not set(grants)<=ALLOWED:
        raise ValueError('Choose supported household services only')
    if ({'vue','requests'}&set(grants)) and 'jellyfin' not in grants:
        raise ValueError('Media clients and requests require Jellyfin')
    return grants

def run_enrollment(username,name,grants,password):
    result=subprocess.run([sys.executable,str(ROOT/'scripts/enroll-household-user.py'),username,'--name',name,'--services',','.join(grants),'--password-stdin'],cwd=ROOT,input=password+'\n',text=True,capture_output=True,timeout=180)
    if result.returncode:raise RuntimeError('Enrollment stopped. Check private service state before retrying; no second account was created automatically.')

class Handler(BaseHTTPRequestHandler):
    server_version='People/1'
    def log_message(self,format,*args):
        # Never log URL fragments, request bodies, passwords or invitation tokens.
        pass
    def respond(self,code,data,content_type='application/json'):
        raw=json.dumps(data).encode() if content_type=='application/json' else data
        self.send_response(code)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers();self.wfile.write(raw)
    def host(self):return self.headers.get('Host','').split(':')[0]
    def authorized(self):
        expected=(PRIVATE/'proxy-key').read_text().strip()
        supplied=self.headers.get('X-Home-People-Key','')
        if not secrets.compare_digest(expected,supplied):return False
        if self.host()!=OWNER_HOST:return False
        if self.path.startswith('/join/'):
            return True  # exact invitation is checked by the join API
        return self.headers.get('Remote-User')=='egouda' and 'owners' in self.headers.get('Remote-Groups','').split(',')
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/health':return self.respond(200,{'ok':True})
        if not self.authorized():return self.respond(403,{'error':'Access denied'})
        if path=='/api/state':
            users=identities();store=invite_store()
            pending=[{'username':v['username'],'name':v['name'],'services':v['services'],'expires':v['expires'],'status':v['status']} for v in store['invitations'].values() if v['status']=='pending' and v['expires']>time.time()]
            return self.respond(200,{'users':users,'invitations':pending,'services':sorted(ALLOWED)})
        if path=='/':path='/index.html'
        static_map={'/index.html':'index.html','/style.css':'style.css','/app.js':'app.js',
                    '/join/':'join.html','/join/style.css':'style.css','/join/join.js':'join.js'}
        if path not in static_map:
            return self.respond(404,{'error':'Not found'})
        content=(STATIC/static_map[path]).read_bytes()
        mime='text/css; charset=utf-8' if path.endswith('.css') else 'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/html; charset=utf-8'
        self.respond(200,content,mime)
    def do_POST(self):
        if not self.authorized():return self.respond(403,{'error':'Access denied'})
        if self.headers.get('Origin')!='https://'+OWNER_HOST or self.headers.get('Content-Type','').split(';')[0]!='application/json':
            return self.respond(403,{'error':'Invalid request origin'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=8192:raise ValueError('Request too large')
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict):raise ValueError('Invalid request')
            if self.path=='/api/invitations':return self.create_invite(body)
            if self.path=='/join/api/invitation':return self.lookup_invite(body)
            if self.path=='/join/api/enroll':return self.enroll(body)
            return self.respond(404,{'error':'Not found'})
        except (ValueError,KeyError) as exc:return self.respond(400,{'error':str(exc)})
        except Exception:return self.respond(500,{'error':'Could not complete this action. Check the private server log and account state.'})
    def create_invite(self,body):
        username=body.get('username','');name=body.get('name','').strip();grants=valid_grants(body.get('services'))
        if not re.fullmatch('[a-z][a-z0-9]{2,31}',username):raise ValueError('Use a lowercase username of 3–32 letters/numbers')
        if not 1<=len(name)<=80 or any(ord(c)<32 for c in name):raise ValueError('Enter a display name')
        if username in identities():raise ValueError('That user already exists')
        token=secrets.token_urlsafe(32);digest=hashlib.sha256(token.encode()).hexdigest()
        with open(PRIVATE/'lock','a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);store=invite_store()
            if any(v['username']==username and v['status'] in ('pending','processing') and v['expires']>time.time() for v in store['invitations'].values()):
                raise ValueError('An invitation is already pending for this username')
            store['invitations'][digest]={'username':username,'name':name,'services':grants,'created':int(time.time()),'expires':int(time.time()+86400),'status':'pending'}
            atomic_json(PRIVATE/'invitations.json',store)
        return self.respond(201,{'url':'https://'+OWNER_HOST+'/join/#'+token,'expires_hours':24})
    def lookup_invite(self,body):
        token=body.get('token','')
        if not isinstance(token,str) or len(token)>128:return self.respond(404,{'error':'Invitation unavailable'})
        invite=invite_store()['invitations'].get(hashlib.sha256(token.encode()).hexdigest())
        if not invite or invite['status']!='pending' or invite['expires']<=time.time():return self.respond(404,{'error':'Invitation expired or already used'})
        return self.respond(200,{'name':invite['name'],'username':invite['username'],'services':invite['services']})
    def enroll(self,body):
        token=body.get('token','');password=body.get('password','');confirmation=body.get('confirmation','')
        if not isinstance(token,str) or len(token)>128:return self.respond(404,{'error':'Invitation unavailable'})
        if not isinstance(password,str) or len(password)<16 or len(password)>256 or '\n' in password or '\r' in password:
            raise ValueError('Use a password of 16–256 characters')
        if not secrets.compare_digest(password,confirmation):raise ValueError('Passwords do not match')
        digest=hashlib.sha256(token.encode()).hexdigest()
        with open(PRIVATE/'lock','a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);store=invite_store();invite=store['invitations'].get(digest)
            if not invite or invite['status']!='pending' or invite['expires']<=time.time():return self.respond(404,{'error':'Invitation expired or already used'})
            invite['status']='processing';atomic_json(PRIVATE/'invitations.json',store)
        try:
            with open(PRIVATE/'enrollment-lock','a+') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                run_enrollment(invite['username'],invite['name'],invite['services'],password)
        except Exception:
            with open(PRIVATE/'lock','a+') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX);store=invite_store();store['invitations'][digest]['status']='needs-review';atomic_json(PRIVATE/'invitations.json',store)
            return self.respond(500,{'error':'Enrollment needs owner review. Your password was not saved by People; ask the owner to inspect the account before retrying.'})
        with open(PRIVATE/'lock','a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);store=invite_store();store['invitations'][digest]['status']='used';atomic_json(PRIVATE/'invitations.json',store)
        return self.respond(200,{'username':invite['username'],'services':invite['services']})

if __name__=='__main__':
    PRIVATE.mkdir(parents=True,mode=0o700,exist_ok=True)
    port=int(os.environ.get('PEOPLE_PORT','8766'))
    ThreadingHTTPServer(('172.18.0.1',port),Handler).serve_forever()
