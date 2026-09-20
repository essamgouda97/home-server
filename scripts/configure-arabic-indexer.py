#!/usr/bin/env python3
"""Configure ArabP2P search and seed limits; no media inspection or grabs."""
import datetime
import json
import os
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET


def main():
    os.umask(0o077)
    backup = Path.home()/'.local/state/home-server-maintenance/arabic-indexer'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup.mkdir(parents=True)
    for app, port, config, version in [('prowlarr',9696,'prowlarr/data','v1'),('radarr',7878,'radarr/config','v3')]:
        key = ET.parse('/mnt/server/'+config+'/config.xml').getroot().findtext('ApiKey')
        base = f'http://127.0.0.1:{port}/api/{version}'
        def api(path, data=None):
            req = urllib.request.Request(base+path,headers={'X-Api-Key':key,'Content-Type':'application/json'},data=json.dumps(data).encode() if data is not None else None,method='PUT' if data is not None else 'GET')
            with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
        name = 'ArabP2P' if app=='prowlarr' else 'ArabP2P (Prowlarr)'
        indexer = next(x for x in api('/indexer') if x['name']==name)
        (backup/(app+'.json')).write_text(json.dumps(indexer))
        desired = {'torrentBaseSettings.seedRatio':2.0} if app=='prowlarr' else {'seedCriteria.seedRatio':2.0,'removeYear':True}
        for field in indexer['fields']:
            if field['name'] in desired:field['value']=desired[field['name']]
        api('/indexer/'+str(indexer['id']),indexer)
        actual = {f['name']:f.get('value') for f in api('/indexer/'+str(indexer['id']))['fields']}
        assert all(actual[k]==v for k,v in desired.items())
        print('PASS',app,'ArabP2P configuration')
    print('Private configuration backup:',backup)


if __name__=='__main__':main()
