#!/usr/bin/env python3
"""Verify real Grafana HTTPS login, provisioned dashboard and live metric samples."""
from auth_session import AuthSession
import atexit
import http.cookiejar
import json
from pathlib import Path
import time
import urllib.request
import urllib.parse
from service_credentials import service_password
base='https://metrics.home.egouda.xyz'
gateway=AuthSession();atexit.register(gateway.close)
o=gateway.opener
with o.open(urllib.request.Request(base+'/login',data=json.dumps({'user':'egouda','password':service_password('metrics')}).encode(),headers={'Content-Type':'application/json'})) as r:assert r.status==200
with o.open(base+'/api/user') as r:assert json.load(r)['login']=='egouda'
with o.open(base+'/api/dashboards/uid/home-server') as r:dashboard=json.load(r)['dashboard']
titles={panel.get('title') for panel in dashboard['panels']}
assert {'Seed jobs','Active uploads','Below ratio 2.0','Seed policy healthy','Torrent upload rate','Seed availability'}<=titles
for expression in ['up','node_cpu_seconds_total','node_memory_MemTotal_bytes','home_container_running','home_service_up','home_filesystem_available_bytes','home_qbittorrent_metrics_up','home_qbittorrent_seed_policy_ok']:
 with o.open(base+'/api/datasources/proxy/uid/home-prometheus/api/v1/query?'+urllib.parse.urlencode({'query':expression})) as r:result=json.load(r)
 assert result['status']=='success' and result['data']['result'],expression+' has no samples'
 if expression in ['up','home_service_up','home_qbittorrent_metrics_up','home_qbittorrent_seed_policy_ok']:assert all(float(s['value'][1])==1 for s in result['data']['result']),expression+' reports an unhealthy target or policy'
 print('PASS live metrics:',expression,len(result['data']['result']),'series')
with o.open(base+'/api/datasources/proxy/uid/home-prometheus/api/v1/rules') as r:rules=json.load(r)
alert_names={rule['name'] for group in rules['data']['groups'] for rule in group['rules'] if rule.get('type')=='alerting'}
assert {'TorrentMetricsUnavailable','TorrentSeedPolicyDrift','TorrentDemandStalled'}<=alert_names
print('PASS torrent dashboard panels and Prometheus alert rules')
with o.open(base+'/logout') as r:r.read()
print('PASS actual Grafana login, provisioned dashboard, live datasource and logout.')
