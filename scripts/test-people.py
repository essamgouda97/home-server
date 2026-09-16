#!/usr/bin/env python3
"""Security regression for owner console and one-use invitations."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services/people'))
import server as people

with tempfile.TemporaryDirectory() as directory:
    people.PRIVATE=Path(directory)
    (people.PRIVATE/'proxy-key').write_text('test-only-key')
    calls=[]
    people.run_enrollment=lambda *args:calls.append(args[:3])
    server=ThreadingHTTPServer(('127.0.0.1',0),people.Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    def request(path,body=None,owner=False,key=True):
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
        headers={'Host':people.OWNER_HOST,'Origin':'https://'+people.OWNER_HOST,'Content-Type':'application/json'}
        if key:headers['X-Home-People-Key']='test-only-key'
        if owner:headers.update({'Remote-User':'egouda','Remote-Groups':'owners'})
        raw=None if body is None else json.dumps(body)
        connection.request('GET' if raw is None else 'POST',path,raw,headers)
        response=connection.getresponse();data=response.read();connection.close()
        return response.status,json.loads(data) if response.getheader('Content-Type')=='application/json' else data
    try:
        assert request('/api/state',owner=True,key=False)[0]==403
        assert request('/api/state')[0]==403
        assert request('/api/state',owner=True)[0]==200
        assert request('/join/')[0]==200
        assert request('/api/invitations',{'username':'agouda','name':'Asser','services':['homarr']})[0]==403
        code,created=request('/api/invitations',{'username':'agouda','name':'Asser','services':['homarr','jellyfin']},owner=True)
        assert code==201
        token=created['url'].split('#',1)[1]
        assert request('/join/api/invitation',{'token':token})[0]==200
        assert request('/join/api/enroll',{'token':token,'password':'short','confirmation':'short'})[0]==400
        assert request('/join/api/enroll',{'token':token,'password':'correct horse battery staple','confirmation':'correct horse battery staple'})[0]==200
        assert calls==[('agouda','Asser',['homarr','jellyfin'])]
        assert request('/join/api/enroll',{'token':token,'password':'correct horse battery staple','confirmation':'correct horse battery staple'})[0]==404
        assert request('/join/api/invitation',{'token':token})[0]==404
        assert request('/api/state',owner=True)[1]['invitations']==[]
    finally:server.shutdown();server.server_close()
print('PASS owner isolation, private invite, validation and one-use redemption')
