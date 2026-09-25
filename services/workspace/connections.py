"""Agent-initiated, browser-confirmed pairing into existing scoped Workspace keys."""
import hashlib
import secrets
import time
import uuid
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

class ConnectionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name: str=Field(min_length=1,max_length=80,description='A recognizable name the human expects, e.g. My research assistant.')
    scope: str=Field(default='write',pattern='^(read|write)$')
    days: int=Field(default=90,ge=1,le=365)

class ConnectionStarted(BaseModel):
    device_code: str=Field(description='Secret for the requesting agent only. Never display it or include it in a URL.')
    user_code: str=Field(description='Human-visible code; ask the person to compare it on the confirmation page.')
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int
    token_endpoint: str

class ConnectionPoll(BaseModel):
    device_code: str=Field(pattern=r'^wsc_[A-Za-z0-9_-]{43}$')

class ConnectionDecision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    approve: bool
    scope: str=Field(default='write',pattern='^(read|write)$')
    days: int=Field(default=90,ge=1,le=365)

class ConnectionToken(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    scope: str
    key_id: str
    api_base: str

def digest(value):return hashlib.sha256(value.encode()).hexdigest()

def register(app,db,browser,entitled,audit,origin):
    def current(c,code):
        normalized=code.upper().replace('-','')
        row=c.execute('SELECT * FROM connections WHERE user_digest=?',(digest(normalized),)).fetchone()
        if not row or row['expires']<=time.time():raise HTTPException(404,'This connection link expired. Ask your agent for a new one.')
        return row

    @app.post('/api/v1/connections',status_code=201,response_model=ConnectionStarted,
              operation_id='startAgentConnection',tags=['Connect'],summary='Start agent setup without an existing API key',
              description='Give the human verification_uri_complete and user_code. Keep device_code private. Poll token_endpoint no faster than interval until the human confirms. The person must already have a Workspace invitation/account.')
    def start_connection(body:ConnectionRequest):
        now=int(time.time());device='wsc_'+secrets.token_urlsafe(32)
        code=''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(12))
        display='-'.join(code[i:i+4] for i in range(0,12,4))
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT count(*) FROM connections WHERE created>?',(now-60,)).fetchone()[0]>=20:
                raise HTTPException(429,'Connection setup is busy. Try again in a minute.',headers={'Retry-After':'60'})
            c.execute('DELETE FROM connections WHERE expires<?',(now-86400,))
            c.execute('INSERT INTO connections(id,device_digest,user_digest,name,scope,days,created,expires,status,last_poll) VALUES(?,?,?,?,?,?,?,?,?,0)',
                      (uuid.uuid4().hex,digest(device),digest(code),body.name,body.scope,body.days,now,now+600,'pending'))
        return {'device_code':device,'user_code':display,'verification_uri':origin+'/#connect',
                'verification_uri_complete':origin+'/?connect='+display,'expires_in':600,'interval':5,
                'token_endpoint':origin+'/api/v1/connections/token'}

    @app.post('/api/v1/connections/token',response_model=ConnectionToken,
              operation_id='finishAgentConnection',tags=['Connect'],summary='Finish setup after the person confirms',
              description='Submit only the secret device_code. HTTP 202 authorization_pending means wait at least five seconds; 429 means slow down. Stop on access_denied/expired_token/invalid_grant. A successful credential is delivered once: store it securely, never print it, then call GET /api/v1/me. If delivery is lost, start a new connection.',
              responses={202:{'description':'authorization_pending; poll after Retry-After'},400:{'description':'expired_token or invalid_grant; start again'},403:{'description':'access_denied; stop polling'},429:{'description':'slow_down; honor Retry-After'}})
    def finish_connection(body:ConnectionPoll):
        now=int(time.time())
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM connections WHERE device_digest=?',(digest(body.device_code),)).fetchone()
            if not row:return JSONResponse({'error':'invalid_grant'},status_code=400)
            if row['expires']<=now:return JSONResponse({'error':'expired_token'},status_code=400)
            if row['status']=='denied':return JSONResponse({'error':'access_denied'},status_code=403)
            if row['status']=='issued':return JSONResponse({'error':'invalid_grant'},status_code=400)
            if row['last_poll']>now-5:return JSONResponse({'error':'slow_down'},status_code=429,headers={'Retry-After':'5'})
            c.execute('UPDATE connections SET last_poll=? WHERE id=?',(now,row['id']))
            if row['status']=='pending':return JSONResponse({'error':'authorization_pending'},status_code=202,headers={'Retry-After':'5'})
            if not entitled(row['username']):return JSONResponse({'error':'access_denied'},status_code=403)
            if c.execute('SELECT count(*) FROM keys WHERE username=? AND revoked=0 AND expires>?',(row['username'],now)).fetchone()[0]>=30:
                return JSONResponse({'error':'access_denied','detail':'Revoke an unused connection before trying again.'},status_code=403)
            value='ws_'+secrets.token_urlsafe(32);key_id=uuid.uuid4().hex
            c.execute('INSERT INTO keys(id,digest,name,username,scope,expires,created) VALUES(?,?,?,?,?,?,?)',
                      (key_id,digest(value),row['name'],row['username'],row['scope'],now+row['days']*86400,now))
            c.execute("UPDATE connections SET status='issued',key_id=? WHERE id=?",(key_id,row['id']))
            audit(c,{'username':row['username']},'agent.connected',key_id)
        return {'access_token':value,'token_type':'Bearer','expires_in':row['days']*86400,'scope':row['scope'],'key_id':key_id,'api_base':origin+'/api/v1'}

    @app.get('/ui-api/connections/{code}',include_in_schema=False)
    def read_connection(code:str,request:Request):
        actor=browser(request)
        with db() as c:row=current(c,code)
        if row['username'] and row['username']!=actor['username']:raise HTTPException(403,'This connection belongs to another account.')
        return {k:row[k] for k in ('name','scope','days','expires','status')}

    @app.post('/ui-api/connections/{code}',include_in_schema=False)
    def decide_connection(code:str,body:ConnectionDecision,request:Request):
        actor=browser(request)
        with db() as c:
            c.execute('BEGIN IMMEDIATE');row=current(c,code)
            if row['status']!='pending':raise HTTPException(409,'This connection has already been handled.')
            if body.scope=='write' and row['scope']=='read':raise HTTPException(400,'This agent requested read-only access.')
            if body.days>row['days']:raise HTTPException(400,'Choose an expiration no longer than requested.')
            if body.approve and c.execute('SELECT count(*) FROM keys WHERE username=? AND revoked=0 AND expires>?',(actor['username'],int(time.time()))).fetchone()[0]>=30:
                raise HTTPException(400,'Disconnect an unused agent before adding another.')
            status='approved' if body.approve else 'denied'
            c.execute('UPDATE connections SET status=?,username=?,scope=?,days=? WHERE id=?',(status,actor['username'],body.scope,body.days,row['id']))
            audit(c,actor,'agent.connection.'+status,row['id'])
        return {'status':status}
