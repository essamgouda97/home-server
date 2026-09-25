"""Aggregate Workspace telemetry for the existing host textfile collector."""
import json
from pathlib import Path
import sqlite3
import subprocess
import time

def collect(metric):
    root=Path('/srv/mergerfs/ssd/shared-workspace')
    if not root.exists():return
    try:
        # Read private credentials only inside the app. Output is numeric metrics.
        code="import urllib.request;from pathlib import Path;r=urllib.request.Request('http://127.0.0.1:8080/internal/metrics',headers={'X-Workspace-Proxy-Key':Path('/run/secrets/proxy-key').read_text().strip()});print(urllib.request.urlopen(r,timeout=5).read().decode())"
        r=subprocess.run(['docker','exec','shared-workspace','python','-c',code],capture_output=True,text=True,timeout=10,check=True)
        for line in r.stdout.splitlines():
            if not line.strip():continue
            name,value=line.split()
            if name.startswith('workspace_') and all(c.isalnum() or c=='_' for c in name):metric('home_'+name,float(value))
        path=root/'paperless/data/db.sqlite3'
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=5) as c:
            metric('home_workspace_documents',c.execute('SELECT count(*) FROM documents_document WHERE deleted_at IS NULL').fetchone()[0])
            # Task metadata only; no titles, paths or task messages are exported.
            table=next((r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0].endswith('_paperlesstask')),None)
            if table:
                counts=dict(c.execute('SELECT status,count(*) FROM "'+table+'" GROUP BY status'))
                for status in ['pending','started','success','failure']:
                    metric('home_workspace_document_tasks',counts.get(status,0),status=status.lower())
        sizes={'originals':root/'paperless/media','database':root/'app','jobs':root/'jobs'}
        for label,directory in sizes.items():
            metric('home_workspace_storage_bytes',sum(p.stat().st_size for p in directory.rglob('*') if p.is_file() and not p.is_symlink()),kind=label)
        statuses={s:0 for s in ['queued','running','succeeded','failed']};duration=0
        for d in (root/'jobs').iterdir():
            if not d.is_dir():continue
            if (d/'result.json').exists():
                r=json.loads((d/'result.json').read_text());statuses[r['status']]+=1;duration+=r.get('duration_seconds',0)
            elif (d/'running.json').exists():statuses['running']+=1
            elif (d/'pending.json').exists():statuses['queued']+=1
        for status,count in statuses.items():metric('home_workspace_script_jobs',count,status=status)
        metric('home_workspace_script_seconds_total',duration)
        metric('home_workspace_metrics_up',1)
    except Exception:
        metric('home_workspace_metrics_up',0)
    metric('home_workspace_collected_seconds',time.time())


if __name__=='__main__':
    import os
    rows=[]
    def emit(name,value,**labels):
        suffix='{'+','.join(k+'='+json.dumps(str(v)) for k,v in sorted(labels.items()))+'}' if labels else ''
        rows.append(name+suffix+' '+str(float(value)))
    collect(emit)
    destination=Path.home()/'.local/state/home-server-metrics'
    destination.mkdir(parents=True,exist_ok=True)
    temp=destination/('workspace-'+str(os.getpid())+'.pending')
    temp.write_text('\n'.join(rows)+'\n');temp.chmod(0o644);temp.replace(destination/'workspace.prom')
    print('Workspace aggregate metrics refreshed.')
