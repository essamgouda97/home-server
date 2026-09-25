#!/usr/bin/env python3
"""Enroll a NEW household identity using a hidden terminal password prompt.

Run on the server over ssh -t. Never pass passwords as command-line arguments.
Existing accounts are refused: use a reviewed migration, not a password reset.
"""
import argparse,getpass,importlib.util,json,os,re,secrets,subprocess,sys,urllib.request
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
PRIVATE=Path.home()/'.config/home-server/secrets'

def run(args):
    result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
    if result.returncode:raise RuntimeError('Provisioning command failed; do not print captured credential-bearing output')
    return result.stdout

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('username');p.add_argument('--name',required=True)
    p.add_argument('--services',default='homarr,jellyfin,vue,requests')
    p.add_argument('--password-stdin',action='store_true',help='Read one password line from a protected pipe (owner-only People service)')
    a=p.parse_args();assert re.fullmatch('[a-z][a-z0-9]{2,31}',a.username),'Use a lowercase username'
    grants=a.services.split(',');assert set(grants)<= {'homarr','jellyfin','vue','requests','files','workspace'},'No unreviewed/admin service grants'
    assert not ({'vue','requests'}&set(grants)) or 'jellyfin' in grants,'Media clients require a Jellyfin profile'
    config=ROOT/'config/identities.json';catalog=json.loads(config.read_text())
    users_path=PRIVATE/'authelia/users.yml';users=yaml.safe_load(users_path.read_text())
    assert a.username not in catalog['users'] and a.username not in users['users'],'Existing identity: refusing overwrite'
    assert a.password_stdin or sys.stdin.isatty(),'Interactive terminal required; use ssh -t'
    password=sys.stdin.readline().rstrip('\n') if a.password_stdin else getpass.getpass('New household password (hidden): ')
    assert len(password)>=16,'Use at least 16 characters'
    if not a.password_stdin:
        assert secrets.compare_digest(password,getpass.getpass('Repeat password (hidden): ')),'Passwords differ'
    settings=json.loads(Path('/mnt/server/jellyseerr/config/settings.json').read_text()) if 'jellyfin' in grants else None
    def api(base,path,key,data=None):
        request=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={key[0]:key[1],'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=30) as response:
            raw=response.read();return json.loads(raw) if raw else None
    jf=lambda path,data=None:api('http://127.0.0.1:8096',path,('X-Emby-Token',settings['jellyfin']['apiKey']),data)
    if 'jellyfin' in grants:
        assert not any(u['Name']==a.username for u in jf('/Users')),'Existing Jellyfin profile: refusing overwrite'
        created=jf('/Users/New',{'Name':a.username,'Password':password})
        assert not created['Policy']['IsAdministrator']
        if 'requests' in grants:
            api('http://127.0.0.1:5055','/api/v1/user/import-from-jellyfin',('X-Api-Key',settings['main']['apiKey']),{'jellyfinUserIds':[created['Id']]})
    if 'files' in grants:
        folder=Path('/srv/mergerfs/ssd/creative/People')/a.username
        folder.mkdir(parents=True,exist_ok=False,mode=0o700)
        compose=['docker','compose','--env-file','server.conf','--env-file','.env']
        run(['docker','stop','filebrowser'])
        try:
            run(compose+['run','--rm','--no-deps','filebrowser','--config','/config/settings.json','users','add',a.username,secrets.token_urlsafe(48),'--scope','Creative/People/'+a.username,'--perm.admin=false','--perm.execute=false','--perm.share=false'])
        finally:run(['docker','start','filebrowser'])
    spec=importlib.util.spec_from_file_location('prepare_auth',ROOT/'scripts/prepare-auth.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    users['users'][a.username]={'displayname':a.name,'email':a.username+'@home.egouda.xyz','password':module.pbkdf2(password),'groups':['household']+['service:'+s for s in grants]}
    del password
    os.umask(0o077);users_path.write_text(yaml.safe_dump(users));users_path.chmod(0o600)
    catalog['users'][a.username]={'display_name':a.name,'owner':False,'services':grants}
    config.write_text(json.dumps(catalog,indent=2)+'\n')
    run(['python3','scripts/prepare-auth.py'])
    if 'homarr' in grants:run(['python3','scripts/provision-homarr-identities.py'])
    if 'jellyfin' in grants:
        # The media OIDC plugin requires an explicit stable-subject link for every
        # existing native profile; matching a name or email must never be enough.
        run(['python3','scripts/configure-jellyfin-sso.py'])
    print('Enrolled',a.username,'with explicit grants. Store the login in the household member’s password manager. Sync/commit the non-secret identities catalog on both checkouts.')
    print('Central and native Jellyfin passwords start equal; later password changes are not yet synchronized.')
if __name__=='__main__':
    try:main()
    except Exception as e:raise SystemExit('Enrollment stopped: '+str(e))
