#!/usr/bin/env python3
"""Expose only the existing Resolve bridge through a private SSH Unix socket."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import signal
import shlex
import threading
import time

APP = Path.home()/'workspace/personal-finances'
ALLOWED = {'status','push-markers','create-planning-timeline','storage-reveal'}
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        try:
            if self.headers.get('Origin') or self.headers.get('Content-Type')!='application/json': raise ValueError()
            size=int(self.headers.get('Content-Length','0'))
            if self.path!='/bridge' or not 0<size<=2*1024*1024: raise ValueError()
            body=json.loads(self.rfile.read(size));args=body['args']
            if not isinstance(args,list) or not args or args[0] not in ALLOWED or len(args)>40: raise ValueError()
            if not all(isinstance(x,str) and '\0' not in x and len(x)<4096 for x in args): raise ValueError()
            if args[0]=='storage-reveal':
                root=args[args.index('--root')+1]
                if root!='/Volumes/Creative' and not root.startswith('/Volumes/Creative/'): raise ValueError()
            result=subprocess.run(['/usr/bin/python3',str(APP/'scripts/resolve_content_bridge.py'),*args],
                cwd=APP,input=body.get('input',''),text=True,capture_output=True,timeout=45)
            data=result.stdout.encode();json.loads(data)
            if len(data)>8*1024*1024: raise ValueError()
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(data)
        except Exception:
            self.send_response(503);self.end_headers();self.wfile.write(b'{"error":"Mac bridge unavailable"}')

def main():
    os.umask(0o077)
    repo=Path(__file__).resolve().parents[1]
    settings=dict(line.split('=',1) for line in (repo/'server.conf').read_text().splitlines() if line and not line.startswith('#') and '=' in line)
    remote=settings['LIFE_DASHBOARD_DATA']+'/bridge/resolve.sock'
    server=ThreadingHTTPServer(('127.0.0.1',18791),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    def terminate(_signum,_frame): raise SystemExit(0)
    signal.signal(signal.SIGTERM,terminate)
    while True:
        cleanup='import os,stat,sys; p=sys.argv[1]; s=os.lstat(p) if os.path.lexists(p) else None; os.unlink(p) if s and stat.S_ISSOCK(s.st_mode) and s.st_uid==os.getuid() else None'
        subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5','home-server',
            'python3 -c '+shlex.quote(cleanup)+' '+shlex.quote(remote)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        child=subprocess.Popen(['ssh','-N','-o','BatchMode=yes','-o','ConnectTimeout=5',
            '-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3',
            '-o','ExitOnForwardFailure=yes','-o','StreamLocalBindUnlink=yes',
            '-R',remote+':127.0.0.1:18791','home-server'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try: child.wait()
        finally:
            child.terminate()
            child.wait(timeout=10)
        time.sleep(10)

if __name__=='__main__': main()
