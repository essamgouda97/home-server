#!/usr/bin/env python3
"""Real HTTPS login using only the credential injected by `vault.py exec metrics`."""
import http.cookiejar
import json
import os
import urllib.request
base='https://metrics.home.egouda.xyz'
o=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
req=urllib.request.Request(base+'/login',data=json.dumps({'user':os.environ['HOME_SERVICE_USERNAME'],'password':os.environ['HOME_SERVICE_PASSWORD']}).encode(),headers={'Content-Type':'application/json'})
with o.open(req,timeout=20) as r:assert r.status==200
with o.open(base+'/api/user') as r:assert json.load(r)['login']=='egouda'
with o.open(base+'/api/dashboards/uid/home-server') as r:assert json.load(r)['dashboard']['uid']=='home-server'
with o.open(base+'/logout') as r:r.read()
print('PASS 1Password-injected Grafana login and dashboard access over trusted HTTPS; session logged out.')
