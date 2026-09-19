#!/usr/bin/env python3
"""Export selected host/container metrics; no socket or credentials given to Grafana."""
import concurrent.futures
import http.cookiejar
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

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

# Aggregate-only torrent telemetry: never export titles, hashes, tracker hosts,
# messages, paths, or credentials to Prometheus.
try:
 secrets=Path.home()/'.config/home-server/secrets'
 password=json.loads((secrets/'service-passwords.json').read_text())['torrents']
 jar=http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
 base='http://127.0.0.1:15080'
 login=urllib.request.Request(base+'/api/v2/auth/login',data=urllib.parse.urlencode({'username':'egouda','password':password}).encode())
 with opener.open(login,timeout=10) as response:assert response.read() in (b'Ok.',b'')
 with opener.open(base+'/api/v2/app/preferences',timeout=10) as response:prefs=json.load(response)
 with opener.open(base+'/api/v2/torrents/info',timeout=10) as response:torrents=json.load(response)
 with opener.open(base+'/api/v2/transfer/info',timeout=10) as response:transfer=json.load(response)
 metric('home_qbittorrent_metrics_up',1)
 metric('home_qbittorrent_torrents',len(torrents))
 metric('home_qbittorrent_uploading',sum(1 for t in torrents if t.get('upspeed',0)>0))
 metric('home_qbittorrent_with_demand',sum(1 for t in torrents if t.get('num_leechs',0)>0))
 metric('home_qbittorrent_complete_below_ratio',sum(1 for t in torrents if t.get('progress',0)>=1 and t.get('ratio',0)<2))
 metric('home_qbittorrent_upload_bytes_per_second',transfer.get('up_info_speed',0))
 policy_ok=all(prefs.get(k)==v for k,v in {'max_ratio':2.0,'max_ratio_act':0,'max_active_uploads':20,'max_active_torrents':50,'dont_count_slow_torrents':True}.items())
 for name,port,path in [('radarr',7878,'/mnt/server/radarr/config/config.xml'),('sonarr',8989,'/mnt/server/sonarr/data/config.xml')]:
  key=ET.parse(path).getroot().findtext('ApiKey')
  req=urllib.request.Request('http://127.0.0.1:'+str(port)+'/api/v3/downloadclient',headers={'X-Api-Key':key})
  with urllib.request.urlopen(req,timeout=10) as response:clients=json.load(response)
  torrent_clients=[c for c in clients if c.get('protocol')=='torrent' or c.get('implementation')=='QBittorrent']
  policy_ok=policy_ok and bool(torrent_clients) and all(not c.get('removeCompletedDownloads') for c in torrent_clients)
 metric('home_qbittorrent_seed_policy_ok',policy_ok)
except Exception:
 metric('home_qbittorrent_metrics_up',0)
metric('home_metrics_collected_seconds',time.time())
tmp=ROOT/('home-'+str(os.getpid())+'.pending');tmp.write_text('\n'.join(rows)+'\n');tmp.chmod(0o644);tmp.replace(ROOT/'home.prom')
print('Metrics refreshed:',len(containers),'containers and',len(services),'service probes.')
