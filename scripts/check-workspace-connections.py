#!/usr/bin/env python3
"""Verify agent-first setup, confirmation boundaries and one-time delivery."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import secrets
import sqlite3
import time
import urllib.request
from auth_session import AuthSession,NoRedirect,prefer_ipv4

spec=importlib.util.spec_from_file_location('workspace_check',Path(__file__).with_name('check-workspace.py'))
check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)
prefer_ipv4();anonymous=urllib.request.build_opener(NoRedirect)
created_keys=[]

def start(name,scope='write'):
    value=check.data(anonymous,'/api/v1/connections',{'name':'Verification '+name,'scope':scope,'days':7},status=201)
    assert value['interval']==5 and value['expires_in']==600
    assert value['device_code'] not in value['verification_uri_complete']
    assert value['verification_uri_complete'].startswith(check.BASE+'/?connect=')
    return value

def poll(value):
    with check.response(urllib.request.build_opener(NoRedirect),'/api/v1/connections/token',{'device_code':value['device_code']}) as response:
        return response.status,json.load(response)

with AuthSession(portal='https://signin.egouda.xyz',target_url=check.BASE) as session:
    try:
        value=start('pairing')
        assert poll(value)==(202,{'error':'authorization_pending'})
        assert poll(value)==(429,{'error':'slow_down'})
        with check.response(anonymous,'/ui-api/connections/'+value['user_code']) as response:assert response.status==302
        with check.response(anonymous,'/ui-api/connections/'+value['user_code'],{'approve':True,'days':7}) as response:assert response.status==302
        request=urllib.request.Request(value['verification_uri_complete'])
        try:response=anonymous.open(request)
        except Exception as error:response=error
        assert response.status==302 and 'connect%3D' in response.headers['Location']
        response.close()
        check.data(session.opener,'/ui-api/connections/'+value['user_code'],{'approve':True,'scope':'read','days':7})
        check.data(session.opener,'/ui-api/connections/'+value['user_code'],{'approve':True,'scope':'read','days':7},status=409)
        time.sleep(5)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:poll(value),range(2)))
        assert sorted(status for status,_ in results)==[200,400],'Credential was delivered more than once'
        token=next(body for status,body in results if status==200);created_keys.append(token['key_id'])
        assert token['scope']=='read'
        identity=check.data(anonymous,'/api/v1/me',key=token['access_token'])
        assert identity['username']=='egouda' and identity['machine'] and identity['scope']=='read'
        check.data(anonymous,'/api/v1/records',{'title':'must fail','kind':'note'},key=token['access_token'],status=403)
        assert poll(value)==(400,{'error':'invalid_grant'})
        print('PASS agent-initiated setup, central confirmation, downgraded scope and atomic one-time credential delivery')
        value=start('cancel')
        check.data(session.opener,'/ui-api/connections/'+value['user_code'],{'approve':False,'scope':'write','days':7})
        assert poll(value)==(403,{'error':'access_denied'})
        print('PASS canceled connection grants no credential')
        value=start('expiration')
        with sqlite3.connect('/srv/mergerfs/ssd/shared-workspace/app/workspace.sqlite3') as c:
            c.execute('UPDATE connections SET expires=? WHERE device_digest=?',(int(time.time())-1,hashlib.sha256(value['device_code'].encode()).hexdigest()))
        assert poll(value)==(400,{'error':'expired_token'})
        check.data(session.opener,'/ui-api/connections/'+value['user_code'],status=404)
        unknown={'device_code':'wsc_'+secrets.token_urlsafe(32)}
        assert poll(unknown)==(400,{'error':'invalid_grant'})
        print('PASS expired and unknown setup secrets cannot receive credentials')
    finally:
        for key_id in created_keys:check.data(session.opener,'/ui-api/keys/'+key_id,method='DELETE')
print('PASS verification connection revoked; no credential printed')
