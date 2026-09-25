#!/usr/bin/env python3
"""Create and verify a Workspace-only invitation; write its link privately."""
import argparse
import json
import os
from pathlib import Path
import re
import time
import urllib.request
from auth_session import AuthSession, prefer_ipv4

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('username')
    parser.add_argument('--name',required=True)
    args=parser.parse_args()
    assert re.fullmatch('[a-z][a-z0-9]{2,31}',args.username)
    prefer_ipv4()
    public='https://workspace.egouda.xyz'
    people='https://people.home.egouda.xyz'
    os.umask(0o077)
    directory=Path.home()/'.local/state/home-server-maintenance/people-invitations'
    directory.mkdir(parents=True,mode=0o700,exist_ok=True)
    path=directory/(args.username+'-invitation.txt')
    if path.exists():
        path.rename(directory/(args.username+'-invitation-'+str(time.time_ns())+'.txt'))
    with AuthSession() as session:
        request=urllib.request.Request(people+'/api/invitations',data=json.dumps({'username':args.username,'name':args.name,'services':['workspace']}).encode(),headers={'Content-Type':'application/json','Origin':people})
        with session.opener.open(request,timeout=30) as response:
            assert response.status==201
            invitation=json.load(response)
    assert invitation['url'].startswith(public+'/join/#')
    # Persist before verification so a network interruption cannot lose the link.
    path.write_text('Invitation for '+args.name+' ('+args.username+')\n\n'+invitation['url']+'\n\nExpires in 24 hours; usable once. Share privately.\nCreate a unique password using your password manager (16–72 characters).\nAfter signup, open '+public+'/#agents and copy the setup message to your agent.\n')
    path.chmod(0o600)
    token=invitation['url'].split('#',1)[1]
    request=urllib.request.Request(public+'/join/api/invitation',data=json.dumps({'token':token}).encode(),headers={'Content-Type':'application/json','Origin':public})
    with urllib.request.urlopen(request,timeout=30) as response:
        value=json.load(response)
        assert value['username']==args.username and value['name']==args.name and value['services']==['workspace']
    print('Created and verified one-use Workspace invitation. Private link file: '+str(path))

if __name__=='__main__':
    main()
