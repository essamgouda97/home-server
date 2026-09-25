#!/usr/bin/env python3
"""Verify the provisioned Workspace dashboard with an actual Grafana login."""
import json
import urllib.parse
import urllib.request
from auth_session import AuthSession
from service_credentials import service_password

BASE='https://metrics.home.egouda.xyz'
with AuthSession() as session:
    opener=session.opener
    request=urllib.request.Request(BASE+'/login',data=json.dumps({'user':'egouda','password':service_password('metrics')}).encode(),headers={'Content-Type':'application/json'})
    with opener.open(request) as response:assert response.status==200
    try:
        with opener.open(BASE+'/api/dashboards/uid/shared-workspace') as response:dashboard=json.load(response)['dashboard']
        assert len(dashboard['panels'])==24
        for panel in dashboard['panels']:
            for target in panel['targets']:
                url=BASE+'/api/datasources/proxy/uid/home-prometheus/api/v1/query?'+urllib.parse.urlencode({'query':target['expr']})
                with opener.open(url) as response:result=json.load(response)
                assert result['status']=='success' and result['data']['result'],panel['title']+' has no data'
                if panel['title'] in ('Workspace availability','Application telemetry','Container health'):
                    assert all(float(row['value'][1])==1 for row in result['data']['result']),panel['title']+' is not healthy'
            print('PASS live dashboard panel:',panel['title'])
        with opener.open(BASE+'/api/datasources/proxy/uid/home-prometheus/api/v1/rules') as response:rules=json.load(response)
        names={rule['name'] for group in rules['data']['groups'] for rule in group['rules']}
        assert {'WorkspaceUnavailable','WorkspaceMetricsUnavailable','WorkspaceBackupOld','WorkspaceScriptFailures'}<=names
    finally:
        with opener.open(BASE+'/logout') as response:response.read()
print('PASS Grafana login, Workspace dashboard, live samples, alerts and logout')
