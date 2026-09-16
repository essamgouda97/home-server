#!/usr/bin/env python3
"""Exercise the real central-only OIDC flow, then revoke the test media session."""
import json,re,urllib.request,uuid
from auth_session import AuthSession
BASE='https://jellyfin.home.egouda.xyz'
def main():
    with AuthSession() as session:
        with session.opener.open(BASE+'/sso/OID/start/authelia',timeout=30) as r:body=r.read().decode()
        match=re.search(r'(?:const|let|var) data\s*=\s*("[^"\n]*")\s*;',body)
        assert match,'Missing SSO completion state'
        data={'data':json.loads(match.group(1)),'deviceId':'maintenance-'+uuid.uuid4().hex,'appName':'Home SSO check','appVersion':'1','deviceName':'Maintenance'}
        request=urllib.request.Request(BASE+'/sso/OID/Auth/authelia',data=json.dumps(data).encode(),headers={'Content-Type':'application/json','Origin':BASE})
        with session.opener.open(request,timeout=30) as r:result=json.load(r)
        token=result['AccessToken']
        try:
            assert result['User']['Name']=='egouda' and result['User']['Policy']['IsAdministrator']
            print('PASS central login -> OIDC -> existing Jellyfin owner session; no native media password used')
        finally:
            request=urllib.request.Request(BASE+'/Sessions/Logout',data=b'{}',headers={'Content-Type':'application/json','X-Emby-Token':token})
            with session.opener.open(request,timeout=20) as r:r.read()
if __name__=='__main__':main()
