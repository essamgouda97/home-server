#!/usr/bin/env python3
"""Archive selected unreferenced images before authorized Docker space recovery."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,tarfile,time
from datetime import datetime,timezone
CANDIDATES=['ollama/ollama:0.6.4','ggcad-worker:local','ggcad-app:local','jc21/nginx-proxy-manager:latest','ghcr.io/linuxserver/jellyfin:latest','louislam/uptime-kuma:1','ghcr.io/gethomepage/homepage:latest','lscr.io/linuxserver/speedtest-tracker:latest','linuxserver/radarr:latest','linuxserver/sonarr:latest','portainer/portainer-ce:latest','ghcr.io/linuxserver/nzbget:latest']
def used():
    ids=subprocess.check_output(['docker','ps','-aq'],text=True).split()
    return set(subprocess.check_output(['docker','inspect','--format','{{.Image}}',*ids],text=True).split()) if ids else set()
def main():
    os.umask(0o077)
    dest=Path.home()/'.local/state/home-server-maintenance/workspace-image-archive'/time.strftime('%Y%m%dT%H%M%S')
    dest.mkdir(parents=True,mode=0o700)
    active=used();selected=[]
    candidates=CANDIDATES
    if '--dangling' in sys.argv:
        candidates=subprocess.check_output(['docker','image','ls','--filter','dangling=true','-q','--no-trunc'],text=True).split()
    for tag in candidates:
        r=subprocess.run(['docker','image','inspect',tag],capture_output=True,text=True)
        if r.returncode:continue
        item=json.loads(r.stdout)[0]
        if '--dangling' in sys.argv and datetime.fromisoformat(item['Created'][:19]+'+00:00').timestamp()>time.time()-86400:continue
        if item['Id'] not in active:selected.append({'id':item['Id'],'tag':tag,'size':item['Size']})
    assert shutil.disk_usage(dest).free>sum(r['size'] for r in selected)*2+2*1024**3
    archive=dest/'images.tar'
    # Docker export itself stages layers under its full /var partition. Give
    # only the temporary export directory a reversible /home-backed bind mount.
    private=Path.home()/'.config/home-server/secrets'
    def sudo(args):
        r=subprocess.run(['sudo','-S','-p','']+args,input=((private/'creative_password').read_text().strip()+'\n').encode(),capture_output=True)
        if r.returncode:raise RuntimeError('Could not prepare temporary export space')
    staging=dest/'export-staging'
    sudo(['install','-d','-m','700',str(staging)])
    sudo(['mount','--bind',str(staging),'/var/lib/docker/tmp'])
    try:
        subprocess.run(['docker','image','save','-o',str(archive),*[r['tag'] for r in selected]],check=True)
    finally:
        sudo(['umount','/var/lib/docker/tmp'])
    # Verify every expected image config and every tar member is readable.
    with tarfile.open(archive) as tar:
        manifest=json.load(tar.extractfile('manifest.json'))
        saved={tag for r in manifest for tag in (r.get('RepoTags') or [])}
        configs={hashlib.sha256(tar.extractfile(r['Config']).read()).hexdigest() for r in manifest}
        assert all(r['id'].split(':')[1] in configs for r in selected)
        for member in tar:
            if member.isfile():
                stream=tar.extractfile(member)
                while stream.read(1024*1024):pass
    digest=hashlib.sha256()
    with archive.open('rb') as stream:
        while chunk:=stream.read(1024*1024):digest.update(chunk)
    (dest/'manifest.json').write_text(json.dumps({'images':selected,'sha256':digest.hexdigest()},indent=2))
    for item in selected:
        assert item['id'] not in used(),'Image became referenced; stop cleanup'
        subprocess.run(['docker','image','rm',item['tag']],check=True,stdout=subprocess.DEVNULL)
    print('Verified and archived',len(selected),'unused images before removing their Docker copies.')
    print('Restore with docker image load -i',archive)
    print('Free /var bytes:',shutil.disk_usage('/var').free)
if __name__=='__main__':main()
