#!/usr/bin/env python3
"""Set predictable 1080p requests, family auto-approval and opt-in web push."""
from datetime import datetime, timezone
from pathlib import Path
import copy
import json
import os
import shutil
import sqlite3
import urllib.request

PROFILE='Home 1080p (WEB / Blu-ray)'
ALLOWED={'WEBDL-1080p','WEBRip-1080p','Bluray-1080p'}

def main():
    os.umask(0o077)
    settings_path=Path('/mnt/server/jellyseerr/config/settings.json')
    settings=json.loads(settings_path.read_text())
    backup=Path.home()/'.local/state/home-server-maintenance/household-requests'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup.mkdir(parents=True)
    shutil.copy2(settings_path,backup/'jellyseerr-settings.json')
    with sqlite3.connect('file:/mnt/server/jellyseerr/config/db/db.sqlite3?mode=ro',uri=True) as db:
        with sqlite3.connect(backup/'jellyseerr.sqlite') as saved:db.backup(saved)
    def api(app,path,data=None,method=None):
        if app=='requests':base='http://127.0.0.1:5055/api/v1';key=settings['main']['apiKey']
        else:base='http://127.0.0.1:'+str(settings[app][0]['port'])+'/api/v3';key=settings[app][0]['apiKey']
        req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),method=method,
            headers={'X-Api-Key':key,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=30) as response:
            body=response.read();return json.loads(body) if body else None
    for app in ['radarr','sonarr']:
        profiles=api(app,'/qualityprofile')
        (backup/(app+'-profiles.json')).write_text(json.dumps(profiles))
        previous=next((p for p in profiles if p['name']==PROFILE),None)
        profile=copy.deepcopy(previous or next(p for p in profiles if p['name']=='HD-1080p'))
        profile.pop('id',None);profile.update({'name':PROFILE,'upgradeAllowed':False,'cutoff':7})
        def allowed(item):
            if item.get('items'):
                children=[allowed(child) for child in item['items']]
                item['allowed']=any(children)
            else:item['allowed']=item.get('quality',{}).get('name') in ALLOWED
            return item['allowed']
        for item in profile['items']:allowed(item)
        result=api(app,'/qualityprofile'+('/'+str(previous['id']) if previous else ''),
                   {**profile,**({'id':previous['id']} if previous else {})},'PUT' if previous else 'POST')
        ident=previous['id'] if previous else result['id']
        definitions=api(app,'/qualitydefinition')
        (backup/(app+'-qualitydefinitions.json')).write_text(json.dumps(definitions))
        for definition in definitions:
            if definition['quality']['name'] not in ALLOWED:continue
            # MiB per minute: ~4.7 GiB preferred and ~9.4 GiB max for 2 hours.
            definition.update({'minSize':10,'maxSize':80,'preferredSize':40})
            api(app,'/qualitydefinition/'+str(definition['id']),definition,'PUT')
        config=copy.deepcopy(settings[app][0])
        config.update({'is4k':False,'isDefault':True,'activeProfileId':ident,'activeProfileName':PROFILE,
                       'syncEnabled':True,'preventSearch':False})
        if app=='sonarr':config.update({'activeAnimeProfileId':ident,'activeAnimeProfileName':PROFILE})
        server_id=config.pop('id')
        api('requests','/settings/'+app+'/'+str(server_id),config,'PUT')
        print(app+': future requests use '+PROFILE+'; search and status sync enabled')
    api('requests','/settings/main',{'applicationUrl':'https://requests.home.egouda.xyz','defaultPermissions':160})
    api('requests','/settings/jellyfin',{'externalHostname':'https://jellyfin.home.egouda.xyz',
        'jellyfinForgotPasswordUrl':'https://jellyfin.home.egouda.xyz/web/#/forgotpassword.html'})
    users=api('requests','/user?take=100')['results']
    mariam=next(u for u in users if u.get('jellyfinUsername')=='mgouda')
    (backup/'mariam-user.json').write_text(json.dumps(mariam))
    api('requests','/user/'+str(mariam['id']),{'username':'Mariam','permissions':160},'PUT')
    webpush=api('requests','/settings/notifications/webpush')
    webpush['enabled']=True
    api('requests','/settings/notifications/webpush',webpush)
    print('Mariam and new standard users: request + automatic approval, no admin/4K permissions')
    print('Web push enabled; each user must opt in from their device. Backup: '+str(backup))

if __name__=='__main__':main()
