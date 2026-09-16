#!/usr/bin/env python3
"""Check native Grafana identity using only the central credential."""
import json
from auth_session import AuthSession
with AuthSession() as s:
    s.opener.open('https://metrics.home.egouda.xyz/login/generic_oauth',timeout=30).read()
    with s.opener.open('https://metrics.home.egouda.xyz/api/user',timeout=20) as response:identity=json.load(response)
    assert identity['id']==1 and identity['login']=='egouda' and identity['isGrafanaAdmin']
    with s.opener.open('https://metrics.home.egouda.xyz/api/dashboards/uid/home-server',timeout=20) as response:
        assert len(json.load(response)['dashboard']['panels'])>=17
    print('PASS central credential only -> existing Grafana administrator and live dashboard')
