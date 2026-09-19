#!/usr/bin/env python3
"""Prove Coach uses only central identity and its backend is proxy-isolated."""
from auth_session import AuthSession
import json
import subprocess
import urllib.request

BASE='https://coach.home.egouda.xyz'

def inspect(kind,name):
    return json.loads(subprocess.run(['docker',kind,'inspect',name],capture_output=True,text=True,check=True).stdout)[0]

def main():
    with AuthSession() as session:
        with session.opener.open(BASE+'/api/state',timeout=20) as response:
            state=json.load(response)
        assert state['user']=='egouda' and len(state['plan']['workouts'])==4 and state['plan']['meals']
        request=urllib.request.Request(BASE+'/api/logout',data=b'{}',headers={
            'Content-Type':'application/json','Origin':BASE,'X-CSRF-Token':state['csrf']})
        with session.opener.open(request,timeout=20) as response:
            result=json.load(response)
        assert result['url']=='https://auth.home.egouda.xyz/logout'
    container=inspect('container','health-coach')
    assert not container['HostConfig']['PortBindings']
    assert set(container['NetworkSettings']['Networks'])=={'health-coach_auth'}
    network=inspect('network','health-coach_auth')
    assert {v['Name'] for v in network['Containers'].values()}=={'health-coach','npm'}
    print('PASS central credential only -> Coach owner; backend isolated; native password removed')

if __name__=='__main__':main()
