#!/usr/bin/env python3
"""Run on server after escrowing metrics credentials; install isolated monitoring."""
import json
from pathlib import Path
import subprocess
import os
os.umask(0o077)
repo=Path(__file__).resolve().parents[1]
secrets=Path.home()/'.config/home-server/secrets'
password=json.loads((secrets/'pending-service-passwords.json').read_text())['metrics']
key=secrets/'grafana_password';key.write_text(password);key.chmod(0o600)
pw=(secrets/'creative_password').read_text().strip()+'\n'
def sudo(*args):
 r=subprocess.run(['sudo','-S','-p','',*args],input=pw,text=True,capture_output=True)
 if r.returncode:raise SystemExit('Privileged monitoring setup failed')
for name,uid in [('grafana','472'),('prometheus','65534')]:
 sudo('install','-d','-m','750','-o',uid,'-g',uid,'/srv/mergerfs/ssd/monitoring/'+name)
sudo('chown','472:472',str(key))
state=Path.home()/'.local/state/home-server-metrics';state.mkdir(parents=True,exist_ok=True,mode=0o755);state.chmod(0o755)
for name in ['home-server-metrics.service','home-server-metrics.timer']:
 target=Path.home()/'.config/systemd/user'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((repo/'templates/systemd'/name).read_bytes())
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
subprocess.run(['systemctl','--user','enable','--now','home-server-metrics.timer'],check=True)
subprocess.run(['docker','compose','-f','compose.monitoring.yml','config','--quiet'],cwd=repo,check=True)
subprocess.run(['docker','compose','-f','compose.monitoring.yml','up','-d'],cwd=repo,check=True)
config=(repo/'config/nginx/metrics.conf.template').read_bytes()
subprocess.run(['docker','exec','-i','npm','sh','-c','cat > /data/nginx/custom/home-server/metrics.conf'],input=config,check=True)
subprocess.run(['docker','exec','npm','nginx','-t'],check=True,capture_output=True)
subprocess.run(['docker','exec','npm','nginx','-s','reload'],check=True,capture_output=True)
active=secrets/'service-passwords.json';values=json.loads(active.read_text());values['metrics']=password;active.write_text(json.dumps(values));active.chmod(0o600)
print('Grafana private route and monitoring stack deployed.')
