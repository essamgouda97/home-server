"""Shared authenticated HTTP client for maintenance checks; never logs cookies."""
import http.cookiejar
import json
import urllib.request
from service_credentials import service_password

PORTAL='https://auth.home.egouda.xyz'
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None

class AuthSession:
    def __init__(self,password=None,username='egouda'):
        self.cookies=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.no_redirect=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies),NoRedirect)
        data={'username':username,'password':password or service_password('auth'),'keepMeLoggedIn':False,'targetURL':'https://home.egouda.xyz'}
        req=urllib.request.Request(PORTAL+'/api/firstfactor',data=json.dumps(data).encode(),headers={'Content-Type':'application/json','Origin':PORTAL})
        with self.opener.open(req,timeout=20) as response:
            assert response.status==200 and json.load(response)['status']=='OK','Central sign-in failed'
    def cookie_header(self,url):
        req=urllib.request.Request(url);self.cookies.add_cookie_header(req)
        return req.get_header('Cookie','')
    def close(self):
        request=urllib.request.Request(PORTAL+'/api/logout',data=b'{}',headers={'Content-Type':'application/json','Origin':PORTAL})
        with self.opener.open(request,timeout=15) as r:r.read()
        self.cookies.clear()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
