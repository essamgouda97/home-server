"""Read / preview / apply coach edits using the supported Google Sheets API."""
import argparse
import fcntl
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import model
import store

LOCK = threading.Lock()


class Sheets:
    def __init__(self):
        self.config=json.loads(Path(os.environ.get('COACH_CONFIG','/run/secrets/coach-config.json')).read_text())
        self.credentials=json.loads(Path(os.environ.get('COACH_GOOGLE','/run/secrets/coach-google.json')).read_text())
        self.token=None
        self.expiry=0

    def request(self, suffix='', method='GET', body=None, params=None):
        if time.time() >= self.expiry:
            fields={k:self.credentials[k] for k in ['refresh_token','client_id','client_secret']}
            fields['grant_type']='refresh_token'
            req=urllib.request.Request('https://oauth2.googleapis.com/token',data=urllib.parse.urlencode(fields).encode())
            try:
                with urllib.request.urlopen(req,timeout=30) as res: result=json.load(res)
            except urllib.error.HTTPError:
                raise RuntimeError('Google authorization needs renewal.') from None
            self.token=result['access_token']; self.expiry=time.time()+result['expires_in']-60
        ident=self.config['spreadsheet_id']
        if not isinstance(ident,str) or not all(c.isalnum() or c in '_-' for c in ident):raise ValueError('Invalid spreadsheet ID')
        url='https://sheets.googleapis.com/v4/spreadsheets/'+ident+suffix
        if params:url+='?'+urllib.parse.urlencode(params,doseq=True)
        req=urllib.request.Request(url,method=method,data=json.dumps(body).encode() if body is not None else None,
                                   headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=45) as res:return json.load(res)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'Google Sheets returned HTTP {exc.code}; edit remains saved locally.') from None

    def read(self):
        return self.request(params={'includeGridData':'true','ranges':model.RANGES})


def refresh(client):
    raw=client.read()
    projected=model.projection(raw)
    with store.connect() as db:
        store.put(db,'source',raw);store.put(db,'model',projected)
        store.put(db,'last_read',time.time());store.put(db,'sync_error','')
    return projected


def apply(client):
    # One worker owns writes. Only user-selected cells are included, never formulas.
    with store.connect() as db:
        pending=[dict(r) for r in db.execute("SELECT * FROM edits WHERE status='pending' ORDER BY created")]
    current=refresh(client)
    if not pending:
        with store.connect() as db:store.put(db,'last_sync',time.time())
        return {'sent':0,'conflicts':0}
    updates=[];done=[];conflicts=[]
    for edit in pending:
        field=current['writable'].get(edit['address'])
        desired=json.loads(edit['value']);expected=json.loads(edit['expected'])
        if not field or field['identity']!=edit['identity']:
            conflicts.append((edit['id'],'Sheet layout or exercise changed.'))
        elif field['value']==desired:
            done.append(edit['id']) # A previous response may have been lost after success.
        elif field['value']!=expected:
            conflicts.append((edit['id'],'This cell changed in Google Sheets. Review both values.'))
        else:
            updates.append({'range':edit['address'],'values':[[desired]]})
            done.append(edit['id'])
    if updates:
        store.backup()
        client.request('/values:batchUpdate','POST',{'valueInputOption':'RAW','data':updates})
        # Read-back is required before reporting an edit as sent.
        verified=refresh(client)
        for edit in pending:
            if edit['id'] in done and verified['writable'].get(edit['address'],{}).get('value')!=json.loads(edit['value']):
                done.remove(edit['id']); conflicts.append((edit['id'],'Read-back differs; review the sheet.'))
    with store.connect() as db:
        for ident in done:db.execute("UPDATE edits SET status='sent',error='' WHERE id=?",(ident,))
        for ident,error in conflicts:db.execute("UPDATE edits SET status='conflict',error=? WHERE id=?",(error,ident))
        store.put(db,'last_sync',time.time())
    return {'sent':len(done),'conflicts':len(conflicts)}


def run_sync(client=None):
    if not LOCK.acquire(blocking=False):return {'busy':True}
    lockfile=None
    try:
        lockfile=(store.DATA/'sync.lock').open('a')
        try:fcntl.flock(lockfile,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'busy':True}
        return apply(client or Sheets())
    except (OSError,ValueError,RuntimeError,KeyError) as exc:
        message=str(exc) if isinstance(exc,RuntimeError) else 'Sync unavailable. Your entries remain saved locally.'
        with store.connect() as db:store.put(db,'sync_error',message)
        return {'error':message}
    finally:
        if lockfile:lockfile.close()
        LOCK.release()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['read','preview','apply','status','backup','import'])
    parser.add_argument('--file')
    args=parser.parse_args();store.init()
    if args.command=='import':
        raw=json.loads(Path(args.file).read_text());p=model.projection(raw)
        with store.connect() as db:store.put(db,'source',raw);store.put(db,'model',p);store.put(db,'last_read',time.time())
        print('Imported private source snapshot.')
    elif args.command=='backup':print(store.backup())
    elif args.command=='read':
        p=refresh(Sheets());print(json.dumps({'workouts':len(p['workouts']),'meals':len(p['meals']),'formulaWarnings':len(p['warnings'])}))
    elif args.command=='apply':print(json.dumps(run_sync()))
    else:
        with store.connect() as db:
            if args.command=='preview':
                print(json.dumps([dict(r) for r in db.execute("SELECT id,address,expected,value,status,error FROM edits WHERE status IN ('pending','conflict')")],ensure_ascii=False))
            else:print(json.dumps({'lastRead':store.get(db,'last_read'),'lastSync':store.get(db,'last_sync'),'error':store.get(db,'sync_error'),
                                  'edits':dict(db.execute('SELECT status,count(*) FROM edits GROUP BY status').fetchall())}))


if __name__=='__main__':main()
