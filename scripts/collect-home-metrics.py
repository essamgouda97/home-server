#!/usr/bin/env python3
"""Export selected host/container metrics; no socket or credentials given to Grafana."""
import concurrent.futures
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request

ROOT=Path.home()/'.local/state/home-server-metrics'
ROOT.mkdir(parents=True,exist_ok=True,mode=0o755)
ROOT.chmod(0o755)
rows=[]
def metric(metric_name,value,**labels):
 suffix='{'+','.join(k+'='+json.dumps(str(v)) for k,v in sorted(labels.items()))+'}' if labels else ''
 rows.append(metric_name+suffix+' '+str(float(value)))
def size(text):
 m=re.match(r'([0-9.]+)\s*([a-zA-Z]+)',text.strip())
 units={'B':1,'kB':1000,'MB':1e6,'GB':1e9,'TB':1e12,'KiB':1024,'MiB':1024**2,'GiB':1024**3,'TiB':1024**4}
 return float(m[1])*units[m[2]]
ids=subprocess.check_output(['docker','ps','-aq'],text=True).split()
containers=json.loads(subprocess.check_output(['docker','inspect',*ids])) if ids else []
for c in containers:
 name=c['Name'].lstrip('/')
 if name in ['ods-langfuse-minio-init','creative-init'] or 'servo' in name:continue
 state=c['State'];health=state.get('Health',{}).get('Status')
 metric('home_container_running',state['Running'],name=name)
 metric('home_container_healthy',health not in ['unhealthy','starting'] and state['Running'],name=name)
 metric('home_container_restart_count',c['RestartCount'],name=name)
for line in subprocess.check_output(['docker','stats','--no-stream','--format','{{json .}}'],text=True).splitlines():
 c=json.loads(line);name=c['Name']
 metric('home_container_cpu_percent',float(c['CPUPerc'].rstrip('%')),name=name)
 metric('home_container_memory_bytes',size(c['MemUsage'].split('/')[0]),name=name)
 for direction,part in zip(['receive','transmit'],c['NetIO'].split('/')):metric('home_container_network_bytes_total',size(part),name=name,direction=direction)
for mount in ['/','/home','/var','/srv/mergerfs/ssd','/srv/mergerfs/hdd']:
 d=shutil.disk_usage(mount);metric('home_filesystem_size_bytes',d.total,mountpoint=mount);metric('home_filesystem_available_bytes',d.free,mountpoint=mount)
for line in Path('/proc/net/dev').read_text().splitlines()[2:]:
 interface,values=line.split(':',1);parts=values.split()
 if interface.strip() in ['lo'] or interface.strip().startswith(('veth','br-','docker')):continue
 metric('home_network_receive_bytes_total',parts[0],interface=interface.strip());metric('home_network_transmit_bytes_total',parts[8],interface=interface.strip())
catalog=json.loads((Path(__file__).resolve().parents[1]/'config/services.json').read_text())['services']
services={s['id']:s for s in catalog}
services['home']={'url':'https://home.egouda.xyz/','expected_status':[200,302,307]}
def probe(service):
 url=services[service]['url'];start=time.monotonic()
 try:
  with urllib.request.urlopen(url,timeout=8) as r:code=r.status
 except urllib.error.HTTPError as e:code=e.code
 except Exception:code=0
 return service,code,time.monotonic()-start
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 for service,code,elapsed in pool.map(probe,services):
  metric('home_service_up',code in services[service]['expected_status'],service=service)
  metric('home_service_http_status',code,service=service)
  metric('home_service_response_seconds',elapsed,service=service)
try:
 output=subprocess.check_output(['nvidia-smi','--query-gpu=index,temperature.gpu,utilization.gpu,memory.used,memory.total','--format=csv,noheader,nounits'],text=True,timeout=10)
 for line in output.splitlines():
  index,temp,util,used,total=[x.strip() for x in line.split(',')]
  for name,value in [('temperature_celsius',temp),('utilization_percent',util),('memory_used_mib',used),('memory_total_mib',total)]:metric('home_gpu_'+name,value,gpu=index)
except (OSError,subprocess.SubprocessError):pass
metric('home_metrics_collected_seconds',time.time())
tmp=ROOT/('home-'+str(os.getpid())+'.pending');tmp.write_text('\n'.join(rows)+'\n');tmp.chmod(0o644);tmp.replace(ROOT/'home.prom')
print('Metrics refreshed:',len(containers),'containers and',len(services),'service probes.')
