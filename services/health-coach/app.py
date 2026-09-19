import hmac
import base64
import json
import math
import os
import re
import secrets
import threading
import time
from datetime import date
from pathlib import Path

from flask import Flask, jsonify, request, session, send_from_directory, Response
from waitress import serve

import model
import store
import sync

os.umask(0o077)
store.init()
with store.connect() as db:
    key=store.get(db,'session_key')
    if not key:key=secrets.token_hex(32);store.put(db,'session_key',key)
app=Flask(__name__,static_folder='static')
app.config.update(SECRET_KEY=key,MAX_CONTENT_LENGTH=128*1024,SESSION_COOKIE_NAME='coach_session',
                  SESSION_COOKIE_SECURE=os.environ.get('COACH_INSECURE_LOCAL')!='1',
                  SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',PERMANENT_SESSION_LIFETIME=2592000)
ORIGIN=os.environ.get('COACH_ORIGIN','https://coach.home.egouda.xyz')
TRUST_PROXY_USER=os.environ.get('COACH_TRUST_PROXY_USER')=='1'
DEVICE_LOCK=threading.Lock()


def failure(message, status=400):return jsonify(error=message),status


@app.before_request
def guard():
    if request.method=='POST' and request.path.startswith('/api/') and not isinstance(request.get_json(silent=True),dict):
        return failure('A JSON object is required',400)
    if request.path.startswith('/api/device/'):
        if request.method!='POST':return failure('Method not allowed',405)
        token_path=Path(os.environ.get('COACH_DEVICE_KEY','/run/secrets/coach-device-key'))
        if not token_path.exists():return failure('Device not commissioned',401)
        if not hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+token_path.read_text().strip()):return failure('Device authentication required',401)
        return None
    if TRUST_PROXY_USER and request.path.startswith('/api/') and request.path!='/api/health':
        user=request.headers.get('Remote-User','')
        if user!='egouda':return failure('Central sign-in required',401 if not user else 403)
        if session.get('user')!='egouda':
            session.clear();session['user']='egouda';session['csrf']=secrets.token_urlsafe(32);session.permanent=True
    if request.method not in ['GET','HEAD','OPTIONS']:
        if request.headers.get('Origin')!=ORIGIN:return failure('Untrusted origin',403)
        if not request.is_json:return failure('JSON required',415)
    if request.path.startswith('/api/') and request.path not in ['/api/login','/api/health']:
        if not session.get('user'):return failure('Sign in to continue',401)
        if request.method not in ['GET','HEAD'] and not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),session.get('csrf','!')):
            return failure('Refresh the page and try again',403)


@app.after_request
def headers(response):
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


@app.errorhandler(400)
def malformed(_):return failure('Invalid request')


@app.errorhandler(413)
def too_large(_):return failure('Entry is too large',413)


@app.get('/')
def index():return send_from_directory('static','index.html')


@app.get('/api/health')
def health():return jsonify(status='ok')


@app.post('/api/logout')
def logout():session.clear();return jsonify(ok=True,url='https://auth.home.egouda.xyz/logout')


@app.get('/api/state')
def state():
    with store.connect() as db:
        p=store.get(db,'model',{})
        edits=[dict(r) for r in db.execute("SELECT * FROM edits WHERE status IN ('pending','conflict') ORDER BY created")]
        entries=[dict(r) for r in db.execute('SELECT * FROM entries ORDER BY day DESC,updated DESC LIMIT 2500')]
        for e in entries:e['value']=json.loads(e['value'])
        for e in edits:
            e['value']=json.loads(e['value']);e['expected']=json.loads(e['expected'])
        events=[dict(r) for r in db.execute("SELECT * FROM device_events WHERE status='suggested' ORDER BY received DESC LIMIT 100")]
        for e in events:e['value']=json.loads(e['value'])
        return jsonify(user=session['user'],csrf=session['csrf'],plan=p,edits=edits,entries=entries,
                       lastRead=store.get(db,'last_read'),lastSync=store.get(db,'last_sync'),syncError=store.get(db,'sync_error',''),
                       deviceLastSeen=store.get(db,'device_seen'),events=events,
                       translations=translations(),
                       stack=[{'plate':i+1,'lbs':20+i*10,'one':v[0],'two':v[1]} for i,v in enumerate(model.STACK)])


def translations():
    path=Path(os.environ.get('COACH_TRANSLATIONS',str(store.DATA/'translations.json')))
    try:
        data=json.loads(path.read_text())
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):return {}


def identifier(value):return isinstance(value,str) and bool(re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',value))


def validate_field(field,value):
    if field['kind'] in ['kg','reps','seconds','weight']:
        if value=='':return True
        if type(value) not in [int,float] or not math.isfinite(value):return False
        low,high=(1,500) if field['kind']=='weight' else (0,1500) if field['kind']=='kg' else (0,86400) if field['kind']=='seconds' else (0,1000)
        return low<=value<=high and (field['kind'] not in ['reps','seconds'] or value==int(value))
    return isinstance(value,str) and len(value)<=2000 and (not field['options'] or value=='' or value in field['options'])


@app.post('/api/edits')
def edit_cells():
    data=request.get_json()
    if not isinstance(data,dict) or not identifier(data.get('id')) or not isinstance(data.get('changes'),list) or not 1<=len(data['changes'])<=30:return failure('Invalid edit')
    # Browser edits, background writes and conflict resolution share the same lock.
    with sync.LOCK,store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        p=store.get(db,'model',{})
        for i,change in enumerate(data['changes']):
            if not isinstance(change,dict):return failure('Invalid field')
            address=change.get('ref');field=p.get('writable',{}).get(address)
            if not field or not validate_field(field,change.get('value')):return failure('Invalid value or protected field')
            if db.execute('SELECT 1 FROM edits WHERE id=?',(data['id']+'_'+str(i),)).fetchone():continue
            if db.execute("SELECT 1 FROM edits WHERE address=? AND status IN ('pending','conflict')",(address,)).fetchone():
                return failure('A change to this field is still waiting to sync. Sync or resolve it first.',409)
            if change.get('expected')!=field['value']:return failure('This field changed. Refresh before editing.',409)
        for i,change in enumerate(data['changes']):
            field=p['writable'][change['ref']]
            db.execute('INSERT OR IGNORE INTO edits(id,address,identity,expected,value,status,created) VALUES (?,?,?,?,?,?,?)',
                        (data['id']+'_'+str(i),change['ref'],field['identity'],json.dumps(field['value']),json.dumps(change['value']), 'pending',time.time()))
    return jsonify(ok=True)


@app.post('/api/resolve')
def resolve():
    data=request.get_json()
    with sync.LOCK,store.connect() as db:
        edit=db.execute("SELECT * FROM edits WHERE id=? AND status IN ('pending','conflict')",(data.get('id'),)).fetchone()
        if not edit:return failure('Edit not found',404)
        if data.get('action')=='discard':db.execute("UPDATE edits SET status='discarded' WHERE id=?",(edit['id'],))
        elif data.get('action')=='retry':
            f=store.get(db,'model',{}).get('writable',{}).get(edit['address'])
            if not f or f['identity']!=edit['identity']:return failure('Mapping changed; enter this value through the current plan instead.',409)
            if data.get('expected')!=f['value']:return failure('Refresh to review the latest sheet value',409)
            db.execute("UPDATE edits SET status='pending',expected=?,error='' WHERE id=?",(json.dumps(f['value']),edit['id']))
        else:return failure('Invalid resolution')
    return jsonify(ok=True)


@app.post('/api/sync')
def sync_now():
    threading.Thread(target=sync.run_sync,daemon=True).start()
    return jsonify(started=True)


@app.post('/api/entries')
def save_entry():
    data=request.get_json()
    if not isinstance(data,dict) or not identifier(data.get('id')) or data.get('kind') not in ['meal','cardio','session','note','weight','set-meta','supplement']:return failure('Invalid entry')
    try:date.fromisoformat(data['day'])
    except (KeyError,TypeError,ValueError):return failure('Choose a valid date')
    v=data.get('value')
    if not isinstance(v,dict) or len(json.dumps(v))>12000:return failure('Invalid entry details')
    if data['kind']=='cardio':
        if type(v.get('minutes')) not in [int,float] or not math.isfinite(v['minutes']) or not 0<v['minutes']<=1440:return failure('Enter a duration between 0 and 1440 minutes')
        if v.get('activity') not in ['Rope','Sandbag','Walking','Other']:return failure('Choose a cardio activity')
    if data['kind']=='weight' and (type(v.get('kg')) not in [int,float] or not math.isfinite(v['kg']) or not 1<=v['kg']<=500):return failure('Enter a valid weight')
    if data['kind']=='session' and (v.get('status') not in ['active','finished'] or not isinstance(v.get('workout'),str)):return failure('Invalid session')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT * FROM entries WHERE id=?',(data['id'],)).fetchone()
        encoded=json.dumps(v,sort_keys=True)
        if old and old['value']==encoded and old['kind']==data['kind'] and old['day']==data['day']:return jsonify(ok=True,version=old['version'])
        if old and (data.get('version')!=old['version'] or old['kind']!=data['kind']):return failure('This entry changed on another device. Refresh to review it.',409)
        if not old and data.get('version',0)!=0:return failure('Entry no longer exists',409)
        if data['kind']=='session' and v['status']=='active':
            active=db.execute("SELECT id FROM entries WHERE kind='session' AND json_extract(value,'$.status')='active' AND id!=?",(data['id'],)).fetchone()
            if active:return failure('Finish your active session first.',409)
        version=old['version']+1 if old else 1
        db.execute('INSERT INTO entries VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET day=excluded.day,value=excluded.value,version=excluded.version,updated=excluded.updated',
                   (data['id'],data['kind'],data['day'],encoded,version,time.time()))
    return jsonify(ok=True,version=version)


def live():
    path=Path(os.environ.get('COACH_BPM','/bridge/fitbit-live.json'))
    try:
        if path.stat().st_size>524288:raise ValueError()
        data=json.loads(path.read_text());now=time.time()*1000
        age=now-float(data.get('observedAtMs') or 0)
        heartbeat=now-float(data.get('updatedAtMs') or 0)
        fresh=data.get('status')=='live' and -10000<=age<12000 and -10000<=heartbeat<15000 and type(data.get('bpm')) is int and 0<data['bpm']<300
        return {'live':fresh,'bpm':data['bpm'] if fresh else None,'observedAtMs':data.get('observedAtMs'),
                'samples':[{'t':s.get('observedAtMs',s.get('timestampMs')),'bpm':s.get('bpm')} for s in data.get('recentSamples',[])][-90:]}
    except (OSError,ValueError,TypeError,KeyError):return {'live':False,'bpm':None,'samples':[]}


@app.get('/api/live')
def live_route():return jsonify(live())


@app.get('/api/history')
def history():
    with store.connect() as db:
        rows=[dict(r) for r in db.execute('SELECT observed,bpm,session FROM heart_samples WHERE observed>? ORDER BY observed',((time.time()-86400)*1000,))]
    return jsonify(samples=rows)


@app.get('/api/export')
def export():
    with store.connect() as db:
        data={table:[dict(r) for r in db.execute('SELECT * FROM '+table)] for table in ['entries','edits','device_events','heart_samples']}
    response=jsonify(data);response.headers['Content-Disposition']='attachment; filename=coach-export.json';return response


@app.post('/api/device/context')
def device_context():
    with store.connect() as db:
        active=db.execute("SELECT id,value FROM entries WHERE kind='session' AND json_extract(value,'$.status')='active'").fetchone()
        store.put(db,'device_seen',time.time())
        return jsonify(schemaVersion=1,session={'id':active['id'],**json.loads(active['value'])} if active else None,
                       control=store.get(db,'device_control',{'preview':False}))


@app.post('/api/device/snapshot')
def device_snapshot():
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or data.get('schemaVersion')!=1:return failure('Invalid snapshot')
    observed=data.get('observedAt')
    if type(observed) not in [int,float] or not math.isfinite(observed) or not time.time()-30<=observed<=time.time()+10:return failure('Stale snapshot')
    status=data.get('status')
    if status not in ['idle','loading','tracking','no-person','multiple-people','keypoints-missing','camera-error','unsupported','uncalibrated']:return failure('Invalid status')
    allowed=['schemaVersion','observedAt','status','exerciseId','sessionId','countingId','count','metric','phase','fps','message']
    metadata={k:data[k] for k in allowed if k in data}
    if len(json.dumps(metadata))>4000:return failure('Oversize metadata')
    for key in ['count','metric','fps']:
        if metadata.get(key) is not None and (type(metadata[key]) not in [int,float] or not math.isfinite(metadata[key])):return failure('Invalid metric')
    encoded=data.get('jpeg')
    if encoded:
        try:jpeg=base64.b64decode(encoded,validate=True)
        except (ValueError,TypeError):return failure('Invalid image')
        if len(jpeg)>90000 or not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):return failure('Invalid JPEG')
        path=store.DATA/'camera.jpg';tmp=store.DATA/'camera.pending'
        with DEVICE_LOCK:
            tmp.write_bytes(jpeg);tmp.replace(path)
        metadata['frameAt']=observed
    with store.connect() as db:store.put(db,'device_snapshot',metadata);store.put(db,'device_seen',time.time())
    return jsonify(ok=True)


@app.get('/api/monitor')
def monitor():
    with store.connect() as db:
        data=store.get(db,'device_snapshot',{})
        data['fresh']=time.time()-data.get('observedAt',0)<15
        data['control']=store.get(db,'device_control',{'preview':False})
    return jsonify(data)


@app.get('/api/camera.jpg')
def camera_image():
    with store.connect() as db:data=store.get(db,'device_snapshot',{})
    if time.time()-data.get('frameAt',0)>15 or not (store.DATA/'camera.jpg').exists():return failure('No fresh camera frame',404)
    return Response((store.DATA/'camera.jpg').read_bytes(),mimetype='image/jpeg')


@app.post('/api/monitor-control')
def monitor_control():
    data=request.get_json()
    if type(data.get('preview')) is not bool:return failure('Invalid preview setting')
    with store.connect() as db:store.put(db,'device_control',{'preview':data['preview']})
    return jsonify(ok=True)


@app.post('/api/device/events')
def device_event():
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or data.get('schemaVersion')!=1 or not identifier(data.get('id')) or not identifier(data.get('sessionId')):return failure('Invalid device event')
    if data.get('kind') not in ['rep-count','form-observation']:return failure('Unsupported observation')
    observed=data.get('observedAt');confidence=data.get('confidence')
    if type(observed) not in [int,float] or not math.isfinite(observed) or not time.time()-86400*7<=observed<=time.time()+30:return failure('Invalid observation timestamp')
    if confidence is not None and (type(confidence) not in [int,float] or not math.isfinite(confidence) or not 0<=confidence<=1):return failure('Invalid confidence')
    if data['kind']=='rep-count' and (type(data.get('reps')) is not int or not 0<=data['reps']<=1000):return failure('Invalid rep count')
    if not isinstance(data.get('exerciseId'),str) or len(data['exerciseId'])>100 or len(json.dumps(data))>8000:return failure('Invalid observation details')
    with store.connect() as db:
        session_row=db.execute("SELECT value FROM entries WHERE id=? AND kind='session'",(data['sessionId'],)).fetchone()
        if not session_row:return failure('Unknown session',404)
        old=db.execute('SELECT value FROM device_events WHERE id=?',(data['id'],)).fetchone()
        if old and json.loads(old['value'])!=data:return failure('Event ID already has different content',409)
        db.execute('INSERT OR IGNORE INTO device_events(id,session,observed,received,value) VALUES (?,?,?,?,?)',
                   (data['id'],data['sessionId'],observed,time.time(),json.dumps(data)))
        store.put(db,'device_seen',time.time())
    return jsonify(ok=True)


@app.post('/api/device-review')
def device_review():
    data=request.get_json()
    if data.get('action') not in ['reviewed','dismissed']:return failure('Invalid review')
    with store.connect() as db:db.execute('UPDATE device_events SET status=? WHERE id=?',(data['action'],data.get('id')))
    return jsonify(ok=True)


def sync_worker():
    while True:
        sync.run_sync()
        time.sleep(60)


def worker():
    last_backup=0
    while True:
        try:
            reading=live()
            if reading['live']:
                with store.connect() as db:
                    active=db.execute("SELECT id FROM entries WHERE kind='session' AND json_extract(value,'$.status')='active'").fetchone()
                    db.execute('INSERT OR IGNORE INTO heart_samples VALUES (?,?,?)',(reading['observedAtMs'],reading['bpm'],active[0] if active else None))
            if time.time()-last_backup>86400:
                store.backup();last_backup=time.time()
        except Exception:
            # No source values, credentials, URLs or request bodies in logs.
            app.logger.warning('Background operation failed; retrying.')
        time.sleep(2)


if __name__=='__main__':
    threading.Thread(target=sync_worker,daemon=True).start()
    threading.Thread(target=worker,daemon=True).start()
    serve(app,host='0.0.0.0',port=int(os.environ.get('PORT','8099')),threads=8)
