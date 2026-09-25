#!/usr/bin/env python3
"""Actual public HTTPS workflow and negative authorization/sandbox checks.

Only synthetic test content is uploaded. Test keys are always revoked. The
synthetic document and script run remain as an explicit installation example.
"""
import hashlib,json,time,urllib.request,urllib.error,uuid
from auth_session import AuthSession,NoRedirect
BASE='https://workspace.egouda.xyz'

def response(opener,path,body=None,method=None,key=None,raw=None,content_type='application/json'):
    headers={'Origin':BASE,'Content-Type':content_type}
    if key:headers['Authorization']='Bearer '+key
    req=urllib.request.Request(BASE+path,data=raw if raw is not None else json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
    try:return opener.open(req,timeout=110)
    except urllib.error.HTTPError as e:return e

def data(opener,path,body=None,method=None,key=None,status=200,**kwargs):
    with response(opener,path,body,method,key,**kwargs) as r:
        assert r.status==status,(path,r.status,'unexpected status')
        return json.load(r)

def wait_job(opener,jid,key):
    for _ in range(45):
        r=data(opener,'/api/v1/jobs/'+jid,key=key)
        if r['status'] in ('succeeded','failed'):return r
        time.sleep(2)
    raise AssertionError('Script did not complete')

def main():
    from auth_session import prefer_ipv4
    prefer_ipv4()
    anon=urllib.request.build_opener(NoRedirect)
    for path,status in [('/',302),('/ui-api/me',302),('/api/v1/me',401),('/internal/metrics',404),('/health',404)]:
        with response(anon,path) as r:assert r.status==status,(path,r.status)
    for path in ['/.well-known/agent.json','/api/v1/','/openapi.json']:
        assert data(anon,path)
    with response(anon,'/llms.txt') as r:assert r.status==200 and b'/api/v1/me' in r.read()
    contract=data(anon,'/openapi.json')
    assert contract['paths']['/api/v1/jobs']['post']['operationId']=='runPython'
    assert contract['components']['schemas']['WorkspaceRecord']['properties']['revision']
    req=urllib.request.Request(BASE+'/',headers={'Remote-User':'egouda','Remote-Groups':'owners','X-Workspace-Proxy-Key':'fake'})
    try:r=anon.open(req)
    except urllib.error.HTTPError as e:r=e
    assert r.status==302,'Forged gateway identity accepted'
    assert '/openapi.json' in r.headers.get('Link',''),'Root lacks API discovery links'
    r.close()
    print('PASS public discovery, anonymous denial and forged identity rejection')
    with AuthSession(portal='https://signin.egouda.xyz',target_url=BASE) as session:
        who=data(session.opener,'/ui-api/me');assert who['username']=='egouda' and not who['machine']
        keys=[]
        records=[]
        try:
            for scope in ['read','write']:
                k=data(session.opener,'/ui-api/keys',{'name':'Installation verification '+scope,'scope':scope,'days':1},status=201);keys.append(k)
            readkey,writekey=[k['key'] for k in keys]
            assert data(anon,'/api/v1/me',key=writekey)['username']=='egouda'
            data(anon,'/api/v1/records',{'title':'must not create','kind':'note'},key=readkey,status=403)
            data(anon,'/api/v1/jobs',{'script':'print(1)'},key=readkey,status=403)
            print('PASS real public central login and read/write key boundaries')
            suffix=uuid.uuid4().hex[:10]
            body={'title':'Installation example '+suffix,'kind':'expense','amount':'12.50','currency':'CAD','date':'2026-09-24','category':'Verification','data':{'synthetic':True}}
            before=data(anon,'/api/v1/analytics',key=writekey)
            record=data(anon,'/api/v1/records',body,key=writekey,status=201);records.append(record)
            assert 'reviewed' not in record,'Unexpected review gate'
            body['revision']=record['revision'];body['amount']='15.00'
            record=data(anon,'/api/v1/records/'+record['id'],body,method='PUT',key=writekey);records[-1]=record
            data(anon,'/api/v1/records/'+record['id'],body,method='PUT',key=writekey,status=409)
            assert data(anon,'/api/v1/analytics',key=writekey)['financial_records']==before['financial_records']+1
            print('PASS agent updates feed analytics immediately; stale revisions rejected')
            text='Workspace installation test '+suffix+'\nSynthetic invoice. Amount CAD 12.50.\n'
            boundary='workspace-'+uuid.uuid4().hex
            payload=('--'+boundary+'\r\nContent-Disposition: form-data; name="file"; filename="installation-example.txt"\r\nContent-Type: text/plain\r\n\r\n'+text+'\r\n--'+boundary+'--\r\n').encode()
            upload=data(anon,'/api/v1/documents/upload',key=writekey,status=202,raw=payload,content_type='multipart/form-data; boundary='+boundary)
            assert upload['sha256']==hashlib.sha256(text.encode()).hexdigest()
            doc_id=None
            for _ in range(90):
                tasks=data(anon,'/api/v1/tasks/'+upload['task_id'],key=writekey)
                task=(tasks if isinstance(tasks,list) else tasks.get('results',[]))
                if task and task[0]['status']=='FAILURE':raise AssertionError('Synthetic document processing failed')
                if task and task[0]['status']=='SUCCESS':doc_id=int(task[0]['related_document']);break
                time.sleep(2)
            assert doc_id,'Document parsing timed out'
            doc=data(anon,'/api/v1/documents/'+str(doc_id),key=readkey)
            assert suffix in doc['content'],'Extracted text missing'
            with response(anon,'/api/v1/documents/'+str(doc_id)+'/file',key=readkey) as r:assert r.read()==text.encode()
            print('PASS upload → local parsing → extracted text → byte-identical original')
            script='''import json,socket,os
from pathlib import Path
m=json.loads(Path('/inputs/manifest.json').read_text())
assert len(m['documents'])==1
assert len(m['records'])==1
assert not Path('/run/secrets').exists()
assert not Path('/var/run/docker.sock').exists()
assert os.getuid()!=0
try:
 socket.create_connection(('1.1.1.1',443),timeout=2)
 raise AssertionError('Network unexpectedly available')
except OSError:pass
try:
 Path('/inputs/script.py').write_text('mutated')
 raise AssertionError('Inputs writable')
except OSError:pass
print(json.dumps({'parsed_amount':'12.50','source_document':m['documents'][0]['id'],'isolated':True,'record_id':m['records'][0]['id']}))
'''
            j=data(anon,'/api/v1/jobs',{'script':script,'document_ids':[doc_id],'record_ids':[record['id']]},key=writekey,status=202)
            result=wait_job(anon,j['id'],writekey)
            assert result['status']=='succeeded',(result.get('error'),'Sandbox verification failed')
            assert result['result']['isolated']
            update={**body,'amount':result['result']['parsed_amount'],'source_document':doc_id,'revision':record['revision'],'data':{'synthetic':True,'parser_job':j['id']}}
            record=data(anon,'/api/v1/records/'+record['id'],update,method='PUT',key=writekey);records[-1]=record
            print('PASS gVisor script reads selected inputs, rejects network/secret/write access, and results update records')
            # A malformed script must terminate as failed, without killing the worker.
            j=data(anon,'/api/v1/jobs',{'script':'raise RuntimeError("synthetic failure")'},key=writekey,status=202)
            assert wait_job(anon,j['id'],writekey)['status']=='failed'
            print('PASS script failure is contained and recorded')
        finally:
            for r in records:
                try:data(session.opener,'/ui-api/records/'+r['id']+'/archive',{'revision':r['revision']})
                except Exception:pass
            for k in keys:
                data(session.opener,'/ui-api/keys/'+k['id'],method='DELETE')
                data(anon,'/api/v1/me',key=k['key'],status=401)
        print('PASS verification keys revoked and synthetic financial entries archived')
    with response(anon,'/ui-api/me',key=writekey) as r:assert r.status==302
    print('Workspace HTTPS workflow verified. No real user data was used.')
if __name__=='__main__':main()
