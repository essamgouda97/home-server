"""Shared document/data workspace. Central browser identity; scoped machine keys."""
import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager, contextmanager
from datetime import date as Date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
import uuid

import httpx
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, UploadFile, File, Query
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, ConfigDict

DATA = Path(os.environ.get('WORKSPACE_DATA', '/data'))
POLICY = Path(os.environ.get('WORKSPACE_POLICY', '/policy/identities.json'))
PRIVATE = Path(os.environ.get('WORKSPACE_SECRETS', '/run/secrets'))
ORIGIN = os.environ.get('WORKSPACE_ORIGIN', 'https://workspace.egouda.xyz')
PAPERLESS = os.environ.get('PAPERLESS_ORIGIN', 'http://workspace-paperless:8000')
STATIC = Path(__file__).with_name('static')
MAX_UPLOAD = 50 * 1024 * 1024
RATE = defaultdict(deque)
INGEST_LOCK = asyncio.Semaphore(2)
JOB_LOCK = asyncio.Lock()
METRICS = defaultdict(float, {key:0.0 for key in ('requests_total','request_seconds_total','errors_total','auth_denials_total','uploaded_bytes_total','uploads_total')})

@contextmanager
def db():
    c = sqlite3.connect(DATA / 'workspace.sqlite3', timeout=20)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    try:
        with c:
            yield c
    finally:
        c.close()

@asynccontextmanager
async def lifespan(app):
    os.umask(0o077)
    DATA.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS keys (
            id TEXT PRIMARY KEY, digest TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
            username TEXT NOT NULL, scope TEXT NOT NULL, expires INTEGER NOT NULL,
            created INTEGER NOT NULL, last_used INTEGER, revoked INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS records (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL,
            source_document INTEGER, amount TEXT, currency TEXT, date TEXT,
            category TEXT NOT NULL, data TEXT NOT NULL,
            revision INTEGER NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
            created INTEGER NOT NULL, updated INTEGER NOT NULL, updated_by TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS connections (
            id TEXT PRIMARY KEY, device_digest TEXT UNIQUE NOT NULL, user_digest TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL, scope TEXT NOT NULL, days INTEGER NOT NULL, created INTEGER NOT NULL,
            expires INTEGER NOT NULL, status TEXT NOT NULL, last_poll INTEGER NOT NULL,
            username TEXT, key_id TEXT);
        CREATE INDEX IF NOT EXISTS connections_created ON connections(created);
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY, timestamp INTEGER NOT NULL, actor TEXT NOT NULL,
            key_id TEXT, action TEXT NOT NULL, object_id TEXT NOT NULL, snapshot TEXT);
        CREATE INDEX IF NOT EXISTS audit_object ON audit(object_id,id);
        CREATE INDEX IF NOT EXISTS records_date ON records(date,kind);
        ''')
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(90, connect=10), follow_redirects=False)
    yield
    await app.state.http.aclose()

app = FastAPI(title='Shared Workspace API', version='1.0.0', lifespan=lifespan,
              description='A shared repository of original documents, parsed text and structured records. Start at /agent-guide.md.',
              docs_url=None, redoc_url=None, openapi_url=None)
api = APIRouter()

def audit(c, actor, action, object_id, snapshot=None):
    c.execute('INSERT INTO audit(timestamp,actor,key_id,action,object_id,snapshot) VALUES(?,?,?,?,?,?)',
              (int(time.time()), actor['username'], actor.get('key_id'), action, str(object_id),
               json.dumps(snapshot) if snapshot is not None else None))

def entitled(username):
    user = json.loads(POLICY.read_text())['users'].get(username)
    return user if user and (user.get('owner') or 'workspace' in user.get('services', [])) else None

def browser(request):
    expected = (PRIVATE / 'proxy-key').read_text().strip()
    if not secrets.compare_digest(request.headers.get('X-Workspace-Proxy-Key', ''), expected):
        raise HTTPException(403, 'Trusted gateway required')
    username = request.headers.get('Remote-User', '')
    user = entitled(username)
    if not user:
        raise HTTPException(403, 'Workspace invitation required')
    if request.method not in ('GET', 'HEAD') and request.headers.get('Origin') != ORIGIN:
        raise HTTPException(403, 'Same-origin request required')
    return {'username': username, 'scope': 'write', 'owner': user['owner'], 'machine': False}

async def identity(request: Request):
    if request.url.path.startswith('/ui-api/'):
        return browser(request)
    supplied = request.headers.get('Authorization', '')
    if not supplied.startswith('Bearer ws_') or len(supplied) > 160:
        raise HTTPException(401, 'Use Authorization: Bearer <workspace API key>', headers={'WWW-Authenticate': 'Bearer'})
    digest = hashlib.sha256(supplied[7:].encode()).hexdigest()
    with db() as c:
        row = c.execute('SELECT * FROM keys WHERE digest=? AND revoked=0 AND expires>?', (digest, int(time.time()))).fetchone()
        if not row or not entitled(row['username']):
            raise HTTPException(401, 'Invalid, expired or revoked API key')
        now = time.monotonic()
        q = RATE[row['id']]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= 120:
            raise HTTPException(429, '120 requests per minute per key', headers={'Retry-After': '60'})
        q.append(now)
        c.execute('UPDATE keys SET last_used=? WHERE id=?', (int(time.time()), row['id']))
        return {'username': row['username'], 'scope': row['scope'], 'key_id': row['id'], 'machine': True, 'owner': False}

def require_write(actor):
    if actor['scope'] != 'write':
        raise HTTPException(403, 'This key is read-only')

def paperless_headers():
    return {'Authorization': 'Token ' + (PRIVATE / 'paperless-token').read_text().strip()}

async def paperless(method, path, **kwargs):
    response = await app.state.http.request(method, PAPERLESS + '/api/' + path.lstrip('/'), headers=paperless_headers(), **kwargs)
    if response.status_code >= 400:
        # Upstream response bodies can contain document contents or internal details.
        raise HTTPException(response.status_code if response.status_code < 500 else 502,
                            'Document engine rejected this request' if response.status_code < 500 else 'Document engine unavailable')
    if response.status_code in (301, 302, 307, 308):
        raise HTTPException(502, 'Unexpected document engine redirect')
    return response

@app.middleware('http')
async def boundary(request, call_next):
    start = time.monotonic()
    length = request.headers.get('Content-Length')
    if length and (not length.isdigit() or int(length) > MAX_UPLOAD + 1048576):
        return JSONResponse({'detail': 'Maximum upload size is 50 MiB'}, status_code=413)
    if length and int(length) > 1024*1024 and not request.url.path.endswith('/documents/upload'):
        return JSONResponse({'detail': 'JSON requests are limited to 1 MiB'}, status_code=413)
    if request.method in ('POST', 'PATCH', 'PUT') and not length:
        return JSONResponse({'detail': 'Content-Length required'}, status_code=411)
    try:
        response = await call_next(request)
    except Exception:
        response = JSONResponse({'detail': 'Request failed; retry or contact the owner'}, status_code=500)
    if request.url.path.startswith(('/api/', '/ui-api/')):
        METRICS['requests_total'] += 1
        METRICS['request_seconds_total'] += time.monotonic() - start
        if response.status_code >= 400:
            METRICS['errors_total'] += 1
        if response.status_code in (401, 403):
            METRICS['auth_denials_total'] += 1
    response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
        'Referrer-Policy': 'no-referrer',
        'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"})
    return response

@app.get('/health', include_in_schema=False)
def health():
    with db() as c:
        c.execute('SELECT count(*) FROM keys').fetchone()
    return {'ok': True}

@app.get('/internal/metrics', include_in_schema=False)
def metrics(request: Request):
    # Not routed publicly; host collector still authenticates to this endpoint.
    expected = (PRIVATE / 'proxy-key').read_text().strip()
    if not secrets.compare_digest(request.headers.get('X-Workspace-Proxy-Key', ''), expected):
        raise HTTPException(403)
    with db() as c:
        counts = {'records': c.execute('SELECT count(*) FROM records WHERE archived=0').fetchone()[0],
                  'financial_records': c.execute("SELECT count(*) FROM records WHERE archived=0 AND kind IN ('income','expense')").fetchone()[0],
                  'active_keys': c.execute('SELECT count(*) FROM keys WHERE revoked=0 AND expires>?', (int(time.time()),)).fetchone()[0],
                  'audit_events': c.execute('SELECT count(*) FROM audit').fetchone()[0]}
    return Response('\n'.join('workspace_' + k + ' ' + str(v) for k, v in {**METRICS, **counts}.items()) + '\n', media_type='text/plain')

@app.get('/openapi.json', include_in_schema=False)
def schema():
    from api_contract import enrich
    return enrich(app.openapi(), ORIGIN)

@app.get('/api/v1/', include_in_schema=False)
@app.get('/.well-known/agent.json', include_in_schema=False)
def discovery():
    return {'name': 'Shared Workspace', 'version': '1', 'api_base': ORIGIN + '/api/v1',
            'entrypoint': ORIGIN + '/llms.txt', 'instructions': ORIGIN + '/agent-guide.md', 'openapi': ORIGIN + '/openapi.json',
            'authentication': {'type': 'bearer', 'header': 'Authorization', 'verify': ORIGIN + '/api/v1/me', 'key_creation': ORIGIN + '/#agents', 'agent_setup': ORIGIN + '/api/v1/connections'},
            'onboarding': {'recommended': 'agent-initiated browser confirmation', 'start': ORIGIN + '/api/v1/connections', 'poll': ORIGIN + '/api/v1/connections/token', 'requires_existing_api_key': False, 'requires_invited_human': True},
            'integration': {'protocol': 'REST', 'mcp': False, 'schema_version': '1.0.0'},
            'limits': {'upload_bytes': MAX_UPLOAD, 'requests_per_minute_per_key': 120, 'script_seconds': 60},
            'capabilities': ['upload', 'local OCR', 'search', 'read originals', 'structured records', 'analytics', 'sandboxed Python scripts'],
            'sharing': 'Every invited member can read and edit the entire workspace.'}

@app.get('/llms.txt', include_in_schema=False)
def agent_entrypoint():
    return FileResponse(STATIC / 'llms.txt', media_type='text/plain')

@app.get('/agent-guide.md', include_in_schema=False)
def guide():
    return FileResponse(STATIC / 'agent-guide.md', media_type='text/plain')

@api.get('/me')
def me(actor=Depends(identity)):
    return actor

@api.get('/documents')
async def documents(q: str = '', page: int = Query(1, ge=1), actor=Depends(identity)):
    params = {'page': page, 'page_size': 30, 'ordering': '-added'}
    if q:
        params['query'] = q[:500]
    result = (await paperless('GET', 'documents/', params=params)).json()
    result['next'] = page + 1 if result.get('next') else None
    result['previous'] = page - 1 if result.get('previous') else None
    return result

@api.post('/documents/upload', status_code=202)
async def upload(file: UploadFile = File(...), title: str = Query('', max_length=200), actor=Depends(identity)):
    require_write(actor)
    if file.size is not None and file.size > MAX_UPLOAD:
        raise HTTPException(413, 'Maximum upload size is 50 MiB')
    async with INGEST_LOCK:
        payload = await file.read(MAX_UPLOAD + 1)
        if len(payload) > MAX_UPLOAD:
            raise HTTPException(413, 'Maximum upload size is 50 MiB')
        if not payload:
            raise HTTPException(400, 'File is empty')
        filename = Path(file.filename or 'document').name[:180]
        fields = {'title': title} if title else {}
        r = await paperless('POST', 'documents/post_document/', files={'document': (filename, payload, file.content_type or 'application/octet-stream')}, data=fields)
        task = r.json()
        METRICS['uploaded_bytes_total'] += len(payload)
        METRICS['uploads_total'] += 1
        with db() as c:
            audit(c, actor, 'document.upload', task)
        return {'task_id': task, 'status': 'queued', 'sha256': hashlib.sha256(payload).hexdigest(), 'poll': '/api/v1/tasks/' + str(task)}

@api.get('/tasks/{task_id}')
async def task(task_id: uuid.UUID, actor=Depends(identity)):
    result = (await paperless('GET', 'tasks/', params={'task_id': str(task_id)})).json()
    items = result if isinstance(result, list) else result.get('results', [])
    for item in items:
        item['status'] = item['status'].upper()
        ids = item.get('related_document_ids') or []
        item['related_document'] = ids[0] if ids else (item.get('result_data') or {}).get('document_id')
    return result

@api.get('/documents/{document_id}')
async def document(document_id: int, actor=Depends(identity)):
    return (await paperless('GET', f'documents/{document_id}/')).json()

class DocumentEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=200)
    content: str | None = Field(default=None, max_length=2000000)

@api.patch('/documents/{document_id}')
async def edit_document(document_id: int, body: DocumentEdit, actor=Depends(identity)):
    require_write(actor)
    value = body.model_dump(exclude_none=True)
    r = (await paperless('PATCH', f'documents/{document_id}/', json=value)).json()
    with db() as c:
        audit(c, actor, 'document.edit', document_id)
    return r

@api.get('/documents/{document_id}/file')
async def file(document_id: int, original: bool = True, actor=Depends(identity)):
    r = await paperless('GET', f'documents/{document_id}/download/', params={'original': 'true' if original else 'false'})
    # Preserve the engine's filename while forcing an attachment on this origin.
    disposition = r.headers.get('content-disposition', '')
    attachment = 'attachment' + disposition[disposition.index(';'):] if ';' in disposition else f'attachment; filename="document-{document_id}"'
    return Response(r.content, media_type='application/octet-stream', headers={'Content-Disposition': attachment})

class RecordBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=200)
    kind: str = Field(default='note', pattern='^(note|income|expense|transaction|email|research|other)$')
    source_document: int | None = Field(default=None, ge=1)
    amount: str | None = Field(default=None, max_length=40)
    currency: str | None = Field(default=None, pattern='^[A-Z]{3}$')
    date: Date | None = None
    category: str = Field(default='', max_length=100)
    data: dict = Field(default_factory=dict)

class RecordEdit(RecordBody):
    revision: int = Field(ge=1)

class Revision(BaseModel):
    revision: int = Field(ge=1)

def record_value(row):
    r = dict(row)
    r['data'] = json.loads(r['data'])
    r.pop('reviewed', None)
    r['archived'] = bool(r['archived'])
    return r

async def validate_record(body):
    v = body.model_dump(mode='json', exclude={'revision'})
    if len(json.dumps(v['data'])) > 200000:
        raise HTTPException(400, 'Structured data exceeds 200 KB')
    if v['amount'] is not None:
        try:
            amount = Decimal(v['amount'])
            if not amount.is_finite() or abs(amount) > Decimal('1000000000000') or amount.as_tuple().exponent < -6:
                raise InvalidOperation
        except InvalidOperation:
            raise HTTPException(400, 'Use a finite decimal amount with up to 6 decimal places')
        if not v['currency']:
            raise HTTPException(400, 'Amount requires a three-letter currency')
        v['amount'] = format(amount, 'f')
    if v['kind'] in ('income', 'expense', 'transaction') and (v['amount'] is None or not v['date']):
        raise HTTPException(400, 'Financial records require amount, currency and date')
    if v['kind'] in ('income', 'expense') and Decimal(v['amount']) < 0:
        raise HTTPException(400, 'Income and expense amounts must be nonnegative')
    if v['source_document']:
        await paperless('GET', f"documents/{v['source_document']}/")
    return v

@api.get('/records')
def records(q: str = '', archived: bool = False, page: int = Query(1, ge=1), actor=Depends(identity)):
    with db() as c:
        where = 'archived=? AND (title LIKE ? OR category LIKE ?)'
        params = (int(archived), '%' + q[:200] + '%', '%' + q[:200] + '%')
        count = c.execute('SELECT count(*) FROM records WHERE ' + where, params).fetchone()[0]
        rows = c.execute('SELECT * FROM records WHERE ' + where + ' ORDER BY updated DESC,id LIMIT 100 OFFSET ?', params + ((page - 1) * 100,)).fetchall()
    return {'count': count, 'results': [record_value(r) for r in rows], 'next': page + 1 if page * 100 < count else None}

@api.post('/records', status_code=201)
async def create_record(body: RecordBody, actor=Depends(identity)):
    require_write(actor)
    v = await validate_record(body)
    ident, now = uuid.uuid4().hex, int(time.time())
    with db() as c:
        c.execute('INSERT INTO records(id,title,kind,source_document,amount,currency,date,category,data,revision,created,updated,updated_by) VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?)',
                  (ident,v['title'],v['kind'],v['source_document'],v['amount'],v['currency'],v['date'],v['category'],json.dumps(v['data']),now,now,actor['username']))
        result = record_value(c.execute('SELECT * FROM records WHERE id=?', (ident,)).fetchone())
        audit(c, actor, 'record.create', ident, result)
    return result

@api.get('/records/{record_id}')
def read_record(record_id: str, actor=Depends(identity)):
    with db() as c:
        row = c.execute('SELECT * FROM records WHERE id=?', (record_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Record not found')
    return record_value(row)

@api.put('/records/{record_id}')
async def edit_record(record_id: str, body: RecordEdit, actor=Depends(identity)):
    require_write(actor)
    v = await validate_record(body)
    with db() as c:
        r = c.execute('UPDATE records SET title=?,kind=?,source_document=?,amount=?,currency=?,date=?,category=?,data=?,revision=revision+1,updated=?,updated_by=? WHERE id=? AND revision=?',
                      (v['title'],v['kind'],v['source_document'],v['amount'],v['currency'],v['date'],v['category'],json.dumps(v['data']),int(time.time()),actor['username'],record_id,body.revision))
        if r.rowcount != 1:
            raise HTTPException(409, 'Record changed or missing. Read it again before editing.')
        result = record_value(c.execute('SELECT * FROM records WHERE id=?', (record_id,)).fetchone())
        audit(c, actor, 'record.edit', record_id, result)
    return result

@api.post('/records/{record_id}/archive')
def archive_record(record_id: str, body: Revision, archived: bool = True, actor=Depends(identity)):
    require_write(actor)
    with db() as c:
        r = c.execute('UPDATE records SET archived=?,revision=revision+1,updated=?,updated_by=? WHERE id=? AND revision=?', (int(archived),int(time.time()),actor['username'],record_id,body.revision))
        if r.rowcount != 1:
            raise HTTPException(409, 'Record changed or missing')
        audit(c, actor, 'record.archive' if archived else 'record.restore', record_id)
    return {'ok': True}

@api.get('/records/{record_id}/history')
def history(record_id: str, actor=Depends(identity)):
    with db() as c:
        rows = c.execute('SELECT timestamp,actor,action,snapshot FROM audit WHERE object_id=? ORDER BY id DESC LIMIT 100', (record_id,)).fetchall()
    return {'results': [{**dict(r), 'snapshot': json.loads(r['snapshot']) if r['snapshot'] else None} for r in rows]}

@api.get('/analytics')
def analytics(actor=Depends(identity)):
    totals, months, categories = defaultdict(lambda: {'income': Decimal(0), 'expense': Decimal(0)}), {}, {}
    with db() as c:
        rows = c.execute('SELECT * FROM records WHERE archived=0').fetchall()
    for row in rows:
        if row['kind'] not in ('income', 'expense'):
            continue
        amount, currency, kind = Decimal(row['amount']), row['currency'], row['kind']
        totals[currency][kind] += amount
        month_key = (row['date'][:7], currency, kind)
        months[month_key] = months.get(month_key, Decimal(0)) + amount
        cat_key = (row['category'] or 'Uncategorized', currency, kind)
        categories[cat_key] = categories.get(cat_key, Decimal(0)) + amount
    return {'record_count': len(rows), 'financial_records': sum(r['kind'] in ('income', 'expense') for r in rows),
            'totals': [{'currency': c, **{k: str(v) for k,v in t.items()}, 'net': str(t['income']-t['expense'])} for c,t in sorted(totals.items())],
            'months': [{'month': k[0], 'currency': k[1], 'kind': k[2], 'amount': str(v)} for k,v in sorted(months.items())],
            'categories': [{'category': k[0], 'currency': k[1], 'kind': k[2], 'amount': str(v)} for k,v in sorted(categories.items())],
            'basis': 'All active income and expense records. Currencies are never combined. Parsed data may contain errors.'}

app.include_router(api, prefix='/api/v1')
app.include_router(api, prefix='/ui-api', include_in_schema=False)

class KeyBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scope: str = Field(default='write', pattern='^(read|write)$')
    days: int = Field(default=90, ge=1, le=365)

@app.get('/ui-api/keys', include_in_schema=False)
def keys(request: Request):
    actor = browser(request)
    with db() as c:
        rows = c.execute('SELECT id,name,username,scope,expires,created,last_used,revoked FROM keys WHERE username=? OR ? ORDER BY created DESC', (actor['username'], int(actor['owner']))).fetchall()
    return {'results': [dict(r) for r in rows], 'owner': actor['owner']}

@app.post('/ui-api/keys', include_in_schema=False, status_code=201)
def create_key(body: KeyBody, request: Request):
    actor = browser(request)
    value, ident, now = 'ws_' + secrets.token_urlsafe(32), uuid.uuid4().hex, int(time.time())
    with db() as c:
        if c.execute('SELECT count(*) FROM keys WHERE username=? AND revoked=0 AND expires>?', (actor['username'],now)).fetchone()[0] >= 30:
            raise HTTPException(400, 'Revoke an unused key before creating another')
        c.execute('INSERT INTO keys(id,digest,name,username,scope,expires,created) VALUES(?,?,?,?,?,?,?)', (ident,hashlib.sha256(value.encode()).hexdigest(),body.name,actor['username'],body.scope,now+body.days*86400,now))
        audit(c, actor, 'key.create', ident)
    return {'id': ident, 'key': value, 'url': ORIGIN, 'expires': now+body.days*86400}

@app.delete('/ui-api/keys/{key_id}', include_in_schema=False)
def revoke_key(key_id: str, request: Request):
    actor = browser(request)
    with db() as c:
        c.execute('UPDATE keys SET revoked=1 WHERE id=? AND (username=? OR ?)', (key_id,actor['username'],int(actor['owner'])))
        audit(c, actor, 'key.revoke', key_id)
    return {'ok': True}

@app.get('/ui-api/activity', include_in_schema=False)
def activity(request: Request):
    browser(request)
    with db() as c:
        rows = c.execute('SELECT timestamp,actor,action,object_id FROM audit ORDER BY id DESC LIMIT 100').fetchall()
    return {'results': [dict(r) for r in rows]}

@app.get('/', include_in_schema=False)
def index(request: Request):
    browser(request)
    return FileResponse(STATIC / 'index.html')

@app.get('/static/{name}', include_in_schema=False)
def assets(name: str, request: Request):
    browser(request)
    if name not in ('app.js', 'style.css'):
        raise HTTPException(404)
    return FileResponse(STATIC / name)

JOBS = Path(os.environ.get('WORKSPACE_JOBS', '/jobs'))
class JobBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    script: str = Field(min_length=1, max_length=64000)
    document_ids: list[int] = Field(default_factory=list, max_length=10)
    record_ids: list[str] = Field(default_factory=list, max_length=100)

@app.post('/api/v1/jobs', status_code=202)
@app.post('/ui-api/jobs', status_code=202, include_in_schema=False)
async def create_job(body: JobBody, actor=Depends(identity)):
    require_write(actor)
    async with JOB_LOCK:
        JOBS.mkdir(parents=True, exist_ok=True)
        queued = sum((d / 'pending.json').exists() or (d / 'running.json').exists() for d in JOBS.iterdir() if d.is_dir())
        if queued >= 10:
            raise HTTPException(429, 'Job queue full; wait for a running job to finish')
        ident = uuid.uuid4().hex
        dest = JOBS / ident
        inputs = dest / 'inputs'
        inputs.mkdir(parents=True, mode=0o700)
        manifest = {'documents': [], 'records': []}
        total = 0
        try:
            for doc_id in dict.fromkeys(body.document_ids):
                if doc_id < 1:
                    raise HTTPException(400, 'Invalid document ID')
                doc = (await paperless('GET', f'documents/{doc_id}/')).json()
                original = await paperless('GET', f'documents/{doc_id}/download/', params={'original':'true'})
                total += len(original.content)
                if total > MAX_UPLOAD:
                    raise HTTPException(413, 'Selected job inputs exceed 50 MiB')
                suffix = Path(doc.get('original_file_name') or '').suffix
                if not re.fullmatch(r'\.[a-zA-Z0-9]{1,8}', suffix):
                    suffix = '.bin'
                filename = f'original-{doc_id}{suffix}'
                (inputs / filename).write_bytes(original.content)
                textfile = f'document-{doc_id}.txt'
                (inputs / textfile).write_text(doc.get('content') or '')
                manifest['documents'].append({'id':doc_id,'title':doc['title'],'path':'/inputs/'+filename,'text_path':'/inputs/'+textfile})
            for record_id in dict.fromkeys(body.record_ids):
                manifest['records'].append(read_record(record_id, actor))
            (inputs / 'manifest.json').write_text(json.dumps(manifest))
            (inputs / 'script.py').write_text(body.script)
            for file in inputs.iterdir():
                file.chmod(0o444)
            inputs.chmod(0o555)
            pending = {'id':ident,'actor':actor,'created':int(time.time()),'script_sha256':hashlib.sha256(body.script.encode()).hexdigest()}
            (dest / 'pending.tmp').write_text(json.dumps(pending))
            (dest / 'pending.tmp').replace(dest / 'pending.json')
            with db() as c:
                audit(c, actor, 'job.submit', ident, {'script_sha256':pending['script_sha256'],'document_ids':body.document_ids,'record_ids':body.record_ids})
        except Exception:
            import shutil
            inputs.chmod(0o700)
            shutil.rmtree(dest)
            raise
        return {'id':ident,'status':'queued','poll':'/api/v1/jobs/'+ident}

@app.get('/api/v1/jobs')
@app.get('/ui-api/jobs', include_in_schema=False)
def list_jobs(actor=Depends(identity)):
    if not JOBS.exists():
        return {'results':[]}
    ids = sorted((p for p in JOBS.iterdir() if p.is_dir()), key=lambda p:p.stat().st_mtime, reverse=True)[:100]
    return {'results':[job(p.name,actor,summary=True) for p in ids if re.fullmatch('[a-f0-9]{32}',p.name)]}

@app.get('/api/v1/jobs/{job_id}')
@app.get('/ui-api/jobs/{job_id}', include_in_schema=False)
def job(job_id: str, actor=Depends(identity), summary: bool = False):
    if not re.fullmatch('[a-f0-9]{32}',job_id):
        raise HTTPException(404)
    dest = JOBS / job_id
    if not dest.is_dir():
        raise HTTPException(404)
    for file,status in [('result.json','finished'),('running.json','running'),('pending.json','queued')]:
        if (dest/file).exists():
            value=json.loads((dest/file).read_text())
            result={'id':job_id,'status':value.get('status',status),'created':value.get('created'),
                    'actor':value.get('actor',{}).get('username'),'duration_seconds':value.get('duration_seconds')}
            if not summary:
                result.update({k:value[k] for k in ('result','error','stderr','script_sha256') if k in value})
            return result
    return {'id':job_id,'status':'staging'}

from connections import register as register_connections
register_connections(app, db, browser, entitled, audit, ORIGIN)
