#!/usr/bin/env python3
"""Verify real Grafana HTTPS login, provisioned dashboard and live metric samples."""
import http.cookiejar
import json
from pathlib import Path
import time
import urllib.request
import urllib.parse
from service_credentials import service_password
base='https://metrics.home.egouda.xyz'
o=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
with o.open(urllib.request.Request(base+'/login',data=json.dumps({'user':'egouda','password':service_password('metrics')}).encode(),headers={'Content-Type':'application/json'})) as r:assert r.status==200
with o.open(base+'/api/user') as r:assert json.load(r)['login']=='egouda'
with o.open(base+'/api/dashboards/uid/home-server') as r:assert len(json.load(r)['dashboard']['panels'])>=10
for expression in ['up','node_cpu_seconds_total','node_memory_MemTotal_bytes','home_container_running','home_service_up','home_filesystem_available_bytes']:
 with o.open(base+'/api/datasources/proxy/uid/home-prometheus/api/v1/query?'+urllib.parse.urlencode({'query':expression})) as r:result=json.load(r)
 assert result['status']=='success' and result['data']['result'],expression+' has no samples'
 if expression in ['up','home_service_up']:assert all(float(s['value'][1])==1 for s in result['data']['result']),expression+' reports unavailable targets'
 print('PASS live metrics:',expression,len(result['data']['result']),'series')
with o.open(base+'/logout') as r:r.read()
print('PASS actual Grafana login, provisioned dashboard, live datasource and logout.')
