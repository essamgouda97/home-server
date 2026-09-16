#!/usr/bin/env python3
"""Pinned OIDC adapter; preserve existing user IDs, passwords and playback policy."""
import hashlib,io,json,os,sqlite3,subprocess,time,urllib.request,zipfile
from pathlib import Path
from identity_policy import identities,allowed
ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8096'
PRIVATE=Path.home()/'.config/home-server/secrets'

def main():
    os.umask(0o077)
    settings=json.loads(Path('/mnt/server/jellyseerr/config/settings.json').read_text())
    headers={'X-Emby-Token':settings['jellyfin']['apiKey'],'Content-Type':'application/json'}
    def api(path,data=None):
        req=urllib.request.Request(BASE+path,data=None if data is None else json.dumps(data).encode(),headers=headers)
        with urllib.request.urlopen(req,timeout=30) as r:
            body=r.read();return json.loads(body) if body else None
    assert api('/System/Info/Public')['Version']=='10.11.11','Pinned compatible Jellyfin patch required'
    original={u['Name']:u for u in api('/Users')}
    assert original['mgouda']['Id']=='21109ac1f8d24849b2165f7cca76fe7a'
    backup=Path.home()/'.local/state/home-server-maintenance/sso/jellyfin';backup.mkdir(parents=True,exist_ok=True)
    before=backup/'users-before.json'
    if not before.exists():before.write_text(json.dumps(original))
    plugin=Path('/mnt/server/jellyfin/config/data/plugins/Community SSO for Jellyfin_4.3.0.0')
    if not plugin.exists():
        assert not any(s.get('NowPlayingItem') for s in api('/Sessions')),'Active playback: defer plugin restart'
        url='https://github.com/Flowfin/jellyfin-plugin-sso/releases/download/4.3.0-stable/community-sso-for-jellyfin_4.3.0.0.zip'
        blob=urllib.request.urlopen(url).read()
        assert hashlib.sha256(blob).hexdigest()=='f7275b9beeaa9519eb2a53afec7fa89ed8c1013deeec4754ba3b543d24f96f9d'
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            assert all('/' not in n and '\\' not in n for n in archive.namelist())
            plugin.mkdir(parents=True)
            archive.extractall(plugin)
        subprocess.run(['docker','restart','jellyfin'],check=True,stdout=subprocess.DEVNULL)
        for _ in range(60):
            try:api('/System/Info/Public');break
            except Exception:time.sleep(1)
    for attempt in range(90):
        try:
            plugins=api('/Plugins')
            break
        except Exception:
            if attempt==89:raise SystemExit('Jellyfin did not become ready; inspect plugin installation')
            time.sleep(1)
    assert any(p['Id'].replace('-','')=='505ce9d1d91642fa86ca673ef241d7df' and p['Status']=='Active' for p in plugins),'SSO plugin not active'
    credentials=json.loads((PRIVATE/'authelia/oidc.json').read_text())['clients']['jellyfin']
    provider={'OidEndpoint':'https://auth.home.egouda.xyz','OidClientId':credentials['id'],'OidSecret':credentials['secret'],
        'Enabled':True,'EnableAuthorization':False,'AllowExistingAccountLink':False,'ProvisionNewUsersDisabled':True,
        'Roles':['owners','service:jellyfin'],'RoleClaim':'groups','OidScopes':['groups','email'],
        'DefaultUsernameClaim':'preferred_username','RequirePkce':True,'RequireVerifiedEmailForLogin':True,
        'AllowPrivateNetworkAddresses':True,'DisablePushedAuthorization':True,
        'BaseUrlOverride':'https://jellyfin.home.egouda.xyz','SchemeOverride':'https',
        'DisableAvatarFromPictureClaim':True,'DefaultProvider':'Jellyfin.Server.Implementations.Users.DefaultAuthenticationProvider'}
    api('/sso/OID/Add/authelia',provider)
    result=subprocess.run(['docker','exec','home-authelia','authelia','storage','user','identifiers','generate','--config','/config/configuration.yml','--users',','.join(identities()),'--services','openid'],capture_output=True,text=True)
    assert result.returncode==0,'Could not prepare stable identity identifiers'
    with sqlite3.connect('file:/srv/mergerfs/ssd/authelia/db.sqlite3?mode=ro',uri=True) as db:
        # Read only stable public subject identifiers, never user credentials.
        subjects=dict(db.execute("SELECT username,identifier FROM user_opaque_identifier WHERE service='openid' AND sector_id=''"))
    for name in identities():
        if allowed(name,'jellyfin'):
            assert name in original,'Provision native media profile before enabling SSO'
            api('/sso/Links/Preprovision/oid/authelia/'+original[name]['Id'],subjects[name])
    after={u['Name']:u for u in api('/Users')}
    for name in ['egouda','mgouda']:
        assert after[name]['Id']==original[name]['Id'] and after[name]['Policy']==original[name]['Policy'],'Unexpected account/policy change'
    print('PASS pinned Jellyfin SSO configured; existing accounts linked explicitly; native policy preserved')
if __name__=='__main__':main()
