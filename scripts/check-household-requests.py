#!/usr/bin/env python3
"""Read-only acceptance checks for automatic household media requests."""
import json
from pathlib import Path
import urllib.request

def main():
    settings=json.loads(Path('/mnt/server/jellyseerr/config/settings.json').read_text())
    assert settings['main']['defaultPermissions']==160
    assert settings['main']['applicationUrl']=='https://requests.home.egouda.xyz'
    assert settings['notifications']['agents']['webpush']['enabled']
    assert settings['jellyfin']['externalHostname']=='https://jellyfin.home.egouda.xyz'
    allowed={'WEBDL-1080p','WEBRip-1080p','Bluray-1080p'}
    for name in ['sonarr','radarr']:
        config=settings[name][0]
        assert config['isDefault'] and not config['is4k'] and config['syncEnabled'] and not config['preventSearch']
        req=urllib.request.Request('http://127.0.0.1:'+str(config['port'])+'/api/v3/qualityprofile/'+str(config['activeProfileId']),headers={'X-Api-Key':config['apiKey']})
        with urllib.request.urlopen(req,timeout=15) as response:profile=json.load(response)
        assert profile['name']=='Home 1080p (WEB / Blu-ray)' and not profile['upgradeAllowed']
        def leaves(items):
            for item in items:
                if not item['allowed']:continue
                if item.get('items'):yield from leaves(item['items'])
                else:yield item['quality']['name']
        assert set(leaves(profile['items']))==allowed
        req=urllib.request.Request('http://127.0.0.1:'+str(config['port'])+'/api/v3/qualitydefinition',headers={'X-Api-Key':config['apiKey']})
        with urllib.request.urlopen(req,timeout=15) as response:definitions=json.load(response)
        for definition in definitions:
            if definition['quality']['name'] in allowed:
                assert definition['maxSize']==80 and definition['preferredSize']==40
        print('PASS '+name+' 1080p-only defaults, size limits, search and progress sync')
    req=urllib.request.Request('http://127.0.0.1:5055/api/v1/user?take=100',headers={'X-Api-Key':settings['main']['apiKey']})
    with urllib.request.urlopen(req,timeout=15) as response:users=json.load(response)['results']
    mariam=next(u for u in users if u.get('jellyfinUsername')=='mgouda')
    assert mariam['permissions']==160
    print('PASS Mariam auto-approval, no administrator/4K permission, and opt-in web push')

if __name__=='__main__':main()
