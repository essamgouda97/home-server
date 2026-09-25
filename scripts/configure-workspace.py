#!/usr/bin/env python3
"""Configure the private document identity and authenticated Workspace route."""
import json,os,subprocess,time,sys
from pathlib import Path
from auth_policy import protect_if_enabled
ROOT=Path(__file__).resolve().parents[1]
PRIVATE=Path.home()/'.config/home-server/secrets/workspace'

def run(args,**kwargs):
    p=subprocess.run(args,capture_output=True,cwd=ROOT,**kwargs)
    if p.returncode:raise RuntimeError('Workspace configuration command failed; output withheld')
    return p.stdout

def put(target,data,mode='644'):
    run(['docker','exec','-i','npm','sh','-c','cat > "$1.pending" && chmod "$2" "$1.pending" && mv "$1.pending" "$1"','sh',target,mode],input=data)

def main():
    os.umask(0o077)
    # This identity is internal to the single shared content repository. Its
    # credential never leaves the server. No human account/password is created.
    program='''
from django.contrib.auth.models import User, Permission
from rest_framework.authtoken.models import Token
u,created=User.objects.get_or_create(username='workspace-service')
if created:u.set_unusable_password()
u.is_staff=False;u.is_superuser=False;u.save()
u.user_permissions.set(Permission.objects.filter(codename__in=['add_document','change_document','view_document','view_paperlesstask']))
t,_=Token.objects.get_or_create(user=u)
print('WORKSPACE_TOKEN='+t.key)
'''
    if '--proxy-only' not in sys.argv:
        output=run(['docker','exec','-i','workspace-paperless','python','manage.py','shell'],input=program.encode()).decode()
        values=[line.split('=',1)[1].strip() for line in output.splitlines() if line.startswith('WORKSPACE_TOKEN=')]
        assert len(values)==1 and len(values[0])==40,'Could not provision document identity'
        (PRIVATE/'app/paperless-token').write_text(values[0]);(PRIVATE/'app/paperless-token').chmod(0o600)
    run(['docker','network','connect','shared-workspace_edge','npm']) if b'npm' not in run(['docker','network','inspect','shared-workspace_edge','--format','{{range .Containers}}{{.Name}} {{end}}']) else None
    backup=Path.home()/'.local/state/home-server-maintenance/workspace'/time.strftime('%Y%m%dT%H%M%S')
    backup.mkdir(parents=True,mode=0o700)
    key=(PRIVATE/'app/proxy-key').read_text().strip()
    paths={
      '/data/nginx/custom/home-server/workspace-key.conf':('proxy_set_header X-Workspace-Proxy-Key "'+key+'";\n').encode(),
      '/data/nginx/custom/home-server/workspace.conf':protect_if_enabled((ROOT/'config/nginx/workspace.conf').read_bytes()),
      '/data/nginx/custom/home-server/workspace-signin.conf':(ROOT/'config/auth/nginx-public-portal.conf').read_bytes(),
    }
    old={}
    for path in paths:
        r=subprocess.run(['docker','exec','npm','cat',path],capture_output=True)
        old[path]=r.stdout if r.returncode==0 else None
        if old[path] is not None:(backup/Path(path).name).write_bytes(old[path])
    try:
        for path,data in paths.items():put(path,data,'600' if 'key.conf' in path else '644')
        run(['docker','exec','npm','nginx','-t'])
        run(['docker','exec','npm','nginx','-s','reload'])
    except Exception:
        for path,data in old.items():
            if data is not None:put(path,data,'600' if 'key.conf' in path else '644')
            else:run(['docker','exec','npm','rm','-f',path])
        run(['docker','exec','npm','nginx','-s','reload'])
        raise
    print('Workspace gateway route configured.' if '--proxy-only' in sys.argv else 'Workspace private document identity and gateway route configured.')
if __name__=='__main__':main()
