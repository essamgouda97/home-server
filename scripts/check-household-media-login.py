#!/usr/bin/env python3
"""Verify actual Jellyfin and Requests login with the private household credential."""
from pathlib import Path
import http.cookiejar
import json
import urllib.error
import urllib.request

def main():
    secrets=Path.home()/'.config/home-server/secrets'
    active=secrets/'service-passwords.json'
    passwords=json.loads(active.read_text()) if active.exists() else {}
    password=passwords.get('jellyfin') or (secrets/'creative_password').read_text().strip()
    def request(opener,url,data=None,headers=None):
        req=urllib.request.Request(url,data=None if data is None else json.dumps(data).encode(),
            headers={'Content-Type':'application/json',**(headers or {})})
        try:
            with opener.open(req,timeout=20) as response:
                body=response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            raise SystemExit('FAIL '+url.split('?')[0]+' HTTP '+str(error.code)) from None
    direct=urllib.request.build_opener()
    auth=request(direct,'http://127.0.0.1:8096/Users/AuthenticateByName',
        {'Username':'egouda','Pw':password},
        {'Authorization':'MediaBrowser Client="Home server check", Device="Maintenance", DeviceId="household-login-check", Version="1.0"'})
    assert auth['User']['Name']=='egouda'
    request(direct,'http://127.0.0.1:8096/Sessions/Logout',{}, {'X-Emby-Token':auth['AccessToken']})
    print('PASS direct Jellyfin authentication; verification session logged out')
    for base,host in [('http://10.0.0.182','http://requests.lan'),('https://requests.home.egouda.xyz','https://requests.home.egouda.xyz')]:
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        headers={'Origin':host,'Host':host.split('://')[1]}
        request(opener,base+'/api/v1/auth/jellyfin',{'username':'egouda','password':password},headers)
        user=request(opener,base+'/api/v1/auth/me',headers=headers)
        assert user.get('jellyfinUsername')=='egouda' or user.get('username')=='egouda'
        request(opener,base+'/api/v1/auth/logout',{},headers)
        print('PASS '+host+' Jellyfin login and authenticated session; logged out')

if __name__=='__main__': main()
