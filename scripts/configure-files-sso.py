#!/usr/bin/env python3
"""Enable supported header SSO only on an isolated, unpublished backend."""
import datetime,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(args):
 r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
 assert r.returncode==0,'File storage adapter operation failed; native database rollback retained'
 return r.stdout

def main():
 backup=Path.home()/'.local/state/home-server-maintenance/sso/files';backup.mkdir(parents=True,exist_ok=True)
 compose=['docker','compose','--env-file','server.conf','--env-file','.env']
 run(['docker','stop','filebrowser'])
 database=Path('/mnt/server/filebrowser/filebrowser.db');saved=backup/(datetime.datetime.now().strftime('%Y%m%dT%H%M%S')+'.db');shutil.copy2(database,saved)
 try:
  run(compose+['run','--rm','--no-deps','filebrowser','--config','/config/settings.json','config','set','--auth.method=proxy','--auth.header=Remote-User','--auth.logoutPage=https://auth.home.egouda.xyz/logout','--signup=false','--disableExec=true','--perm.execute=false','--perm.share=false'])
  network=json.loads(run(['docker','network','inspect','home-server_files_auth']))[0]
  if not any(v['Name']=='npm' for v in network.get('Containers',{}).values()):run(['docker','network','connect','home-server_files_auth','npm'])
  run(compose+['up','-d','--no-deps','filebrowser'])
  state=json.loads(run(['docker','inspect','filebrowser']))[0]
  assert not state['HostConfig']['PortBindings'] and set(state['NetworkSettings']['Networks'])=={'home-server_files_auth'}
  network=json.loads(run(['docker','network','inspect','home-server_files_auth']))[0]
  assert network['Internal'] and {v['Name'] for v in network['Containers'].values()}=={'npm','filebrowser'}
  run(['docker','exec','npm','nginx','-t']);run(['docker','exec','npm','nginx','-s','reload'])
 except Exception:
  run(['docker','stop','filebrowser']);shutil.copy2(saved,database);run(compose+['up','-d','--no-deps','filebrowser']);raise
 print('PASS file storage header adapter enabled; backend isolated to Nginx, no published port')
if __name__=='__main__':main()
