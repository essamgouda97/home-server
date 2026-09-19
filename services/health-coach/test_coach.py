import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

TMP=tempfile.TemporaryDirectory()
os.environ['COACH_DATA']=TMP.name
os.environ['COACH_DEVICE_KEY']=str(Path(TMP.name)/'device')
os.environ['COACH_TRUST_PROXY_USER']='1'
Path(os.environ['COACH_DEVICE_KEY']).write_text('test-device-key')
import app
import store
import sync
import model


class CoachTest(unittest.TestCase):
    def setUp(self):
        self.client=app.app.test_client()
        self.headers={'Origin':app.ORIGIN,'Remote-User':'egouda'}
        r=self.client.get('/api/state',headers=self.headers)
        self.headers['X-CSRF-Token']=r.json['csrf']
        with store.connect() as db:
            for t in ['edits','entries','device_events']:db.execute('DELETE FROM '+t)
            store.put(db,'model',{'writable':{"'Log book'!I6":{'value':10,'kind':'kg','identity':'exercise','label':'kg','options':[]}}})

    def test_auth_and_csrf(self):
        self.assertEqual(app.app.test_client().get('/api/state').status_code,401)
        self.assertEqual(app.app.test_client().get('/api/state',headers={'Remote-User':'mgouda'}).status_code,403)
        self.assertEqual(self.client.post('/api/entries',json={}).status_code,401)
        self.assertEqual(self.client.post('/api/entries',json={},headers={'Remote-User':'egouda'}).status_code,403)
        r=self.client.get('/api/state',headers=self.headers);self.assertIn('no-store',r.headers['Cache-Control'])

    def test_edit_replay_and_stale_value(self):
        request={'id':'one','changes':[{'ref':"'Log book'!I6",'value':20,'expected':10}]}
        self.assertEqual(self.client.post('/api/edits',json=request,headers=self.headers).status_code,200)
        self.assertEqual(self.client.post('/api/edits',json=request,headers=self.headers).status_code,200)
        with store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM edits').fetchone()[0],1)
        request['id']='two';self.assertEqual(self.client.post('/api/edits',json=request,headers=self.headers).status_code,409)

    def test_protected_and_bad_numeric_edits(self):
        for address,value in [("'Log book'!S6",20),("'Log book'!I6",-1),("'Log book'!I6",'20'),("'Log book'!I6",float('nan'))]:
            r=self.client.post('/api/edits',json={'id':'x','changes':[{'ref':address,'value':value,'expected':10}]},headers=self.headers)
            self.assertEqual(r.status_code,400)

    def test_entry_versions(self):
        request={'id':'weight','day':'2026-09-16','kind':'weight','value':{'kg':80},'version':0}
        self.assertEqual(self.client.post('/api/entries',json=request,headers=self.headers).status_code,200)
        self.assertEqual(self.client.post('/api/entries',json=request,headers=self.headers).status_code,200)
        request['value']['kg']=81
        self.assertEqual(self.client.post('/api/entries',json=request,headers=self.headers).status_code,409)
        request['version']=1;self.assertEqual(self.client.post('/api/entries',json=request,headers=self.headers).status_code,200)

    def test_device_event_dedupe_and_auth(self):
        import time
        self.client.post('/api/entries',json={'id':'session','day':'2026-09-16','kind':'session','value':{'workout':'Push','status':'active'}},headers=self.headers)
        event={'schemaVersion':1,'id':'event','sessionId':'session','exerciseId':'training-27','kind':'rep-count','reps':10,'confidence':.8,'observedAt':time.time()}
        self.assertEqual(self.client.post('/api/device/events',json=event).status_code,401)
        headers={'Authorization':'Bearer test-device-key'}
        self.assertEqual(self.client.post('/api/device/events',json=event,headers=headers).status_code,200)
        self.assertEqual(self.client.post('/api/device/events',json=event,headers=headers).status_code,200)
        event['reps']=11;self.assertEqual(self.client.post('/api/device/events',json=event,headers=headers).status_code,409)

    def test_stale_bpm_hidden(self):
        p=Path(TMP.name)/'bpm.json';os.environ['COACH_BPM']=str(p)
        p.write_text(json.dumps({'status':'live','bpm':120,'observedAtMs':1,'updatedAtMs':1}))
        self.assertFalse(app.live()['live']);self.assertIsNone(app.live()['bpm'])

    def test_table_preserves_owner_rounding(self):
        self.assertEqual(model.STACK[4],(27.2,13.6));self.assertEqual(model.STACK[-1],(77.1,38.6))
        self.assertEqual(model.column(198),'GP')

    def test_sync_conflict_and_lost_response(self):
        from unittest.mock import patch
        self.client.post('/api/edits',json={'id':'one','changes':[{'ref':"'Log book'!I6",'value':20,'expected':10}]},headers=self.headers)
        current={'writable':{"'Log book'!I6":{'value':15,'identity':'exercise'}}}
        with patch('sync.refresh',return_value=current):result=sync.apply(object())
        self.assertEqual(result['conflicts'],1)
        with store.connect() as db:db.execute("UPDATE edits SET status='pending'")
        current['writable']["'Log book'!I6"]['value']=20
        with patch('sync.refresh',return_value=current):result=sync.apply(object())
        self.assertEqual(result['sent'],1)

    def test_sync_writes_only_mapped_cell_and_verifies(self):
        from unittest.mock import Mock,patch
        self.client.post('/api/edits',json={'id':'write','changes':[{'ref':"'Log book'!I6",'value':20,'expected':10}]},headers=self.headers)
        before={'writable':{"'Log book'!I6":{'value':10,'identity':'exercise'}}}
        after={'writable':{"'Log book'!I6":{'value':20,'identity':'exercise'}}}
        client=Mock()
        with patch('sync.refresh',side_effect=[before,after]):result=sync.apply(client)
        client.request.assert_called_once_with('/values:batchUpdate','POST',{'valueInputOption':'RAW','data':[{'range':"'Log book'!I6",'values':[[20]]}]})
        self.assertEqual(result,{'sent':1,'conflicts':0})
        with store.connect() as db:self.assertEqual(db.execute('SELECT status FROM edits').fetchone()[0],'sent')

    def test_private_camera_freshness_and_input(self):
        import time,base64
        headers={'Authorization':'Bearer test-device-key'}
        snapshot={'schemaVersion':1,'observedAt':time.time(),'status':'tracking','count':2,'jpeg':base64.b64encode(b'\xff\xd8test\xff\xd9').decode()}
        self.assertEqual(self.client.post('/api/device/snapshot',json=snapshot,headers=headers).status_code,200)
        self.assertEqual(app.app.test_client().get('/api/camera.jpg').status_code,401)
        self.assertEqual(self.client.get('/api/camera.jpg',headers=self.headers).status_code,200)
        with store.connect() as db:
            data=store.get(db,'device_snapshot');data['observedAt']=data['frameAt']=time.time()-20;store.put(db,'device_snapshot',data)
        self.assertEqual(self.client.get('/api/camera.jpg',headers=self.headers).status_code,404)
        self.assertFalse(self.client.get('/api/monitor',headers=self.headers).json['fresh'])
        self.assertEqual(self.client.post('/api/entries',json=[],headers=self.headers).status_code,400)


if __name__=='__main__':unittest.main()
