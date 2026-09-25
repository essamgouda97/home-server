#!/usr/bin/env python3
"""Install pinned gVisor, preserving Docker runtime configuration and live apps."""
import hashlib,json,os,shutil,subprocess,sys,tarfile,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PRIVATE=Path.home()/'.config/home-server/secrets'
VERSION='20260921.0'

def sudo(args):
    p=subprocess.run(['sudo','-S','-p','']+args,input=((PRIVATE/'creative_password').read_text().strip()+'\n').encode(),capture_output=True)
    if p.returncode:raise RuntimeError('Sandbox installation command failed: '+args[0])
    return p.stdout

def main():
    os.umask(0o077)
    backup=Path.home()/'.local/state/home-server-maintenance/workspace-sandbox'/time.strftime('%Y%m%dT%H%M%S')
    backup.mkdir(parents=True,mode=0o700)
    previous=sudo(['cat','/etc/docker/daemon.json'])
    (backup/'daemon.json').write_bytes(previous)
    if not Path('/usr/local/bin/runsc').exists():
        base='https://storage.googleapis.com/gvisor/releases/release/'+VERSION+'/x86_64/'
        archive=backup/'gvisor.tar.bz2'
        if len(sys.argv)>1:
            source=Path(sys.argv[1]);shutil.copy2(source,archive)
            expected=source.with_suffix(source.suffix+'.sha512').read_text().split()[0]
        else:
            with urllib.request.urlopen(base+'gvisor.tar.bz2',timeout=20) as response:archive.write_bytes(response.read())
            with urllib.request.urlopen(base+'gvisor.tar.bz2.sha512',timeout=20) as response:expected=response.read().decode().split()[0]
        assert hashlib.sha512(archive.read_bytes()).hexdigest()==expected,'gVisor checksum mismatch'
        with tarfile.open(archive) as tar:
            assert all(not x.name.startswith('/') and '..' not in Path(x.name).parts for x in tar),'Invalid release archive'
        sudo(['tar','-xjf',str(archive),'-C','/usr/local/bin'])
        sudo(['/usr/local/bin/runsc','install'])
        sudo(['systemctl','reload','docker'])
    check=subprocess.run(['docker','info','--format','{{json .Runtimes}}'],capture_output=True,text=True,check=True)
    assert 'runsc' in json.loads(check.stdout),'gVisor runtime not registered; no fallback allowed'
    subprocess.run(['docker','build','--network','none','-t','home-server/workspace-sandbox:1',str(ROOT/'services/workspace/sandbox')],check=True)
    unit=Path.home()/'.config/systemd/user/home-workspace-worker.service'
    unit.write_bytes((ROOT/'templates/systemd/home-workspace-worker.service').read_bytes())
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    subprocess.run(['systemctl','--user','enable','--now','home-workspace-worker.service'],check=True)
    print('gVisor runtime and bounded Workspace worker installed; existing Docker runtimes preserved.')
if __name__=='__main__':main()
