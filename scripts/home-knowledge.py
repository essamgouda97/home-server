#!/usr/bin/env python3
"""Owner-only, local retrieval for home-server documentation and Draw boards.

The index stores excerpts and local embeddings, never credentials. Run on the server
under the owner's Unix account; the MCP transport is stdio over owner SSH.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import urllib.request

DEFAULT_DB = Path.home() / '.local/share/home-server/knowledge.sqlite3'
DEFAULT_REPO = Path.home() / 'workspace/home-server'
DEFAULT_DRAW = Path('/srv/mergerfs/ssd/excalidraw/excalidraw.db')
EMBED_URL = 'http://127.0.0.1:8090/embed'
TEXT_SUFFIXES = {'.md', '.txt'}
SKIP_NAMES = {'AGENTS.md', 'MEMORY.md', 'SOUL.md', 'USER.md', 'TOOLS.md', 'BOOTSTRAP.md'}
SENSITIVE = re.compile(r'(?i)(password\s*[:=]|api[_ -]?key\s*[:=]|secret\s*[:=]|token\s*[:=]|-----BEGIN [A-Z ]*PRIVATE KEY-----|op://)')


def connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    db = sqlite3.connect(path)
    os.chmod(path, 0o600)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY, source TEXT NOT NULL, title TEXT NOT NULL,
        url TEXT NOT NULL, body TEXT NOT NULL, digest TEXT NOT NULL,
        embedding BLOB, updated_at TEXT
      );
      CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
        title, body, content='documents', content_rowid='rowid'
      );
      CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
        INSERT INTO documents_fts(rowid,title,body) VALUES(new.rowid,new.title,new.body);
      END;
      CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
        INSERT INTO documents_fts(documents_fts,rowid,title,body) VALUES('delete',old.rowid,old.title,old.body);
      END;
      CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
        INSERT INTO documents_fts(documents_fts,rowid,title,body) VALUES('delete',old.rowid,old.title,old.body);
        INSERT INTO documents_fts(rowid,title,body) VALUES(new.rowid,new.title,new.body);
      END;
    ''')
    return db


def chunks(body: str, limit: int = 1400):
    paragraphs = re.split(r'\n\s*\n', body)
    out, current = [], ''
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for piece in (paragraph[i:i+limit] for i in range(0, len(paragraph), limit)):
            if current and len(current) + len(piece) + 2 > limit:
                out.append(current)
                current = ''
            current = (current + '\n\n' + piece).strip()
    if current:
        out.append(current)
    return out


def safe_text(text: str) -> str:
    # Reject a whole line instead of trying to mask an unknown secret syntax.
    return '\n'.join(line for line in text.splitlines() if not SENSITIVE.search(line))


def repo_documents(repo: Path):
    roots = [repo / 'README.md', repo / 'docs']
    for root in roots:
        paths = [root] if root.is_file() else root.rglob('*')
        for path in paths:
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if path.name in SKIP_NAMES or any(part.startswith('.') for part in path.relative_to(repo).parts):
                continue
            # Private app/data directories and agent memory are not crawl targets.
            if any(part in {'memory', 'backups', 'tmp', 'node_modules'} for part in path.relative_to(repo).parts):
                continue
            relative = path.relative_to(repo).as_posix()
            try:
                body = safe_text(path.read_text(encoding='utf-8'))
            except (OSError, UnicodeError):
                continue
            for n, chunk in enumerate(chunks(body)):
                yield (f'repo:{relative}:{n}', 'repository', f'{relative} · {n+1}',
                       f'https://github.com/essamgouda97/home-server/blob/main/{relative}', chunk,
                       str(path.stat().st_mtime_ns))


def draw_documents(path: Path):
    if not path.exists():
        return
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        rows = db.execute('''SELECT p.id,p.name,p.description,p.updated_at,e.data,e.label_text
            FROM projects p LEFT JOIN elements e ON e.project_id=p.id AND e.is_deleted=0
            ORDER BY p.id,e.id''')
        boards = {}
        for pid, name, description, updated, data, label in rows:
            item = boards.setdefault(pid, [name, description or '', updated, []])
            if label:
                item[3].append(label)
            elif data:
                try:
                    element = json.loads(data)
                    value = element.get('text') or element.get('label', {}).get('text')
                    if isinstance(value, str):
                        item[3].append(value)
                except (ValueError, AttributeError):
                    continue
        for pid, (name, description, updated, labels) in boards.items():
            body = safe_text('\n'.join([description, *labels]))
            for n, chunk in enumerate(chunks(body)):
                yield (f'draw:{pid}:{n}', 'draw', f'{name} · {n+1}',
                       f'https://draw.home.egouda.xyz/?board={pid}', chunk, str(updated))
    finally:
        db.close()


def service_documents(repo: Path):
    path = repo / 'config/services.json'
    if not path.exists():
        return
    try:
        services = json.loads(path.read_text(encoding='utf-8'))['services']
    except (OSError, ValueError, KeyError):
        return
    for service in services:
        name = service.get('title') or service.get('id')
        url = service.get('url')
        if not isinstance(name, str) or not isinstance(url, str) or not url.startswith('https://'):
            continue
        sid = service.get('id') or hashlib.sha256(url.encode()).hexdigest()[:16]
        category = service.get('category', '')
        access = service.get('auth', {}).get('access', 'owner')
        body = f'{name}\nCategory: {category}\nAccess: {access}\nURL: {url}'
        yield (f'service:{sid}', 'services', name, url, body, str(path.stat().st_mtime_ns))


def embed(text: str):
    return embed_many([text])[0]


def embed_many(texts: list[str]):
    request = urllib.request.Request(EMBED_URL, json.dumps({'inputs': [t[:3000] for t in texts]}).encode(),
                                     {'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        vectors = json.load(response)
    if len(vectors) != len(texts):
        raise RuntimeError('embedding response count mismatch')
    return [array.array('f', vector).tobytes() for vector in vectors]


def sync(db, repo: Path, draw: Path, use_embeddings: bool = True):
    seen, changed, pending = set(), 0, []
    def flush():
        nonlocal changed
        if not pending:
            return
        vectors = embed_many([item[4] for item in pending]) if use_embeddings else [None] * len(pending)
        for doc, vector in zip(pending, vectors):
            did, source, title, url, body, updated, digest = doc
            db.execute('''INSERT INTO documents(id,source,title,url,body,digest,embedding,updated_at)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                source=excluded.source,title=excluded.title,url=excluded.url,body=excluded.body,
                digest=excluded.digest,embedding=excluded.embedding,updated_at=excluded.updated_at''',
                       (did, source, title, url, body, digest, vector, updated))
            changed += 1
        db.commit()
        pending.clear()

    for doc in [*repo_documents(repo), *draw_documents(draw), *service_documents(repo)]:
        did, source, title, url, body, updated = doc
        if not body.strip():
            continue
        seen.add(did)
        digest = hashlib.sha256(body.encode()).hexdigest()
        previous = db.execute('SELECT digest,embedding FROM documents WHERE id=?', (did,)).fetchone()
        if previous and previous[0] == digest and (previous[1] or not use_embeddings):
            continue
        pending.append((*doc, digest))
        if len(pending) >= 16:
            flush()
    flush()
    for (did,) in db.execute('SELECT id FROM documents').fetchall():
        if did not in seen:
            db.execute('DELETE FROM documents WHERE id=?', (did,))
    db.commit()
    return {'documents': len(seen), 'changed': changed}


def cosine(a: bytes, b: bytes) -> float:
    va, vb = array.array('f'), array.array('f')
    va.frombytes(a)
    vb.frombytes(b)
    if len(va) != len(vb):
        return 0
    dot = sum(x*y for x,y in zip(va,vb))
    norm = math.sqrt(sum(x*x for x in va) * sum(y*y for y in vb))
    return dot / norm if norm else 0


def search(db, query: str, limit: int = 6):
    limit = max(1, min(limit, 20))
    stop = {'the','a','an','and','or','to','of','for','in','on','is','are','where','how','what','my','our','all','do','does','can','i'}
    tokens = [token for token in re.findall(r'[\w]+', query.lower()) if token not in stop]
    if not tokens:
        return []
    expression = ' OR '.join('"' + token.replace('"', '') + '"' for token in tokens[:12])
    lexical = db.execute('''SELECT d.id,bm25(documents_fts, 8.0, 1.0) FROM documents_fts f
        JOIN documents d ON d.rowid=f.rowid WHERE documents_fts MATCH ?
        ORDER BY bm25(documents_fts, 8.0, 1.0) LIMIT 100''',
        (expression,)).fetchall()
    scores = {did: 1/(1+position) for position, (did, _) in enumerate(lexical)}
    try:
        query_vector = embed(query)
    except (OSError, ValueError, IndexError):
        query_vector = None
    if query_vector:
        for did, vector in db.execute('SELECT id,embedding FROM documents WHERE embedding IS NOT NULL'):
            similarity = cosine(query_vector, vector)
            if similarity > .20:
                scores[did] = scores.get(did, 0) + similarity * 2
    result = []
    for did in sorted(scores, key=scores.get, reverse=True)[:limit]:
        row = db.execute('SELECT id,source,title,url,body,updated_at FROM documents WHERE id=?', (did,)).fetchone()
        if row:
            result.append(dict(zip(('id','source','title','url','excerpt','updated_at'),
                                   (*row[:4], row[4][:1100], row[5]))))
    return result


def fetch(db, did: str):
    row = db.execute('SELECT id,source,title,url,body,updated_at FROM documents WHERE id=?', (did,)).fetchone()
    return dict(zip(('id','source','title','url','text','updated_at'), row)) if row else None


def mcp(db):
    tools = [
      {'name':'search_home_knowledge','description':'Search owner-accessible home server documentation and Draw boards. Results include source links; verify fresh operational state in the source app.',
       'inputSchema':{'type':'object','properties':{'query':{'type':'string'},'limit':{'type':'integer','minimum':1,'maximum':20}},'required':['query']}},
      {'name':'read_home_knowledge','description':'Read a full indexed excerpt by ID returned from search.',
       'inputSchema':{'type':'object','properties':{'id':{'type':'string'}},'required':['id']}},
    ]
    for line in sys.stdin:
        try:
            req = json.loads(line)
            method, params = req.get('method'), req.get('params', {})
            if method == 'notifications/initialized':
                continue
            if method == 'initialize':
                result = {'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'home-knowledge','version':'0.1'}}
            elif method == 'tools/list':
                result = {'tools': tools}
            elif method == 'tools/call':
                args = params.get('arguments', {})
                if params.get('name') == 'search_home_knowledge':
                    payload = search(db, str(args['query']), int(args.get('limit', 6)))
                elif params.get('name') == 'read_home_knowledge':
                    payload = fetch(db, str(args['id']))
                else:
                    raise ValueError('unknown tool')
                result = {'content':[{'type':'text','text':json.dumps(payload, ensure_ascii=False)}]}
            else:
                raise ValueError('unknown method')
            if 'id' in req:
                print(json.dumps({'jsonrpc':'2.0','id':req['id'],'result':result}), flush=True)
        except Exception as exc:
            if isinstance(req, dict) and 'id' in req:
                print(json.dumps({'jsonrpc':'2.0','id':req['id'],'error':{'code':-32603,'message':str(exc)}}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    parser.add_argument('--repo', type=Path, default=DEFAULT_REPO)
    parser.add_argument('--draw', type=Path, default=DEFAULT_DRAW)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('sync')
    p.add_argument('--no-embeddings', action='store_true')
    p = sub.add_parser('search')
    p.add_argument('query')
    p.add_argument('--limit', type=int, default=6)
    p = sub.add_parser('read')
    p.add_argument('id')
    sub.add_parser('mcp')
    args = parser.parse_args()
    db = connect(args.db)
    if args.command == 'sync':
        print(json.dumps(sync(db, args.repo, args.draw, not args.no_embeddings)))
    elif args.command == 'search':
        print(json.dumps(search(db, args.query, args.limit), ensure_ascii=False, indent=2))
    elif args.command == 'read':
        print(json.dumps(fetch(db, args.id), ensure_ascii=False, indent=2))
    else:
        mcp(db)

if __name__ == '__main__':
    main()
