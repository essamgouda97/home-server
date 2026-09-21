#!/usr/bin/env python3
"""Root-only home-server VPN lifecycle. No secrets are printed.

Stage copies the existing authorized CyberGhost client credentials privately.
Activate is protected by a separate rollback timer until explicitly committed.
Local routes and encrypted Tailscale transport remain reachable.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess

ROOT = Path('/etc/home-server-vpn')
IFACE = 'homevpn0'
TABLE = '51820'
PROBE = '51821'
SCRIPT = '/usr/local/sbin/home-server-vpn'


def run(*args, check=True, input=None):
    result = subprocess.run(args, input=input, text=True, capture_output=True)
    if check and result.returncode:
        raise RuntimeError('Command failed: '+args[0]+' '+args[1])
    return result


def config():
    return json.loads((ROOT/'network.json').read_text())


def firewall():
    c = config()
    local = ', '.join(c['local4'])
    endpoints = ', '.join(c['endpoints'])
    text = f'''table inet home_vpn {{
 set local4 {{ type ipv4_addr; flags interval; auto-merge; elements = {{ {local} }}; }}
 set endpoints {{ type ipv4_addr; elements = {{ {endpoints} }}; }}
 chain output {{ type filter hook output priority -10; policy drop;
  oifname "lo" accept
  oifname "{IFACE}" accept
  oifname "tailscale0" accept
  oifname "br-*" ip daddr {{ 172.16.0.0/12, 192.168.0.0/16 }} accept
  meta mark & 0xff0000 == 0x80000 accept
  ip daddr @endpoints udp dport {c['port']} accept
  udp sport 68 udp dport 67 accept
  oifname "{c['interface']}" udp dport 53 counter drop
  oifname "{c['interface']}" tcp dport 53 counter drop
  ip daddr @local4 accept
  ip6 daddr {{ fe80::/10, fc00::/7, ff02::/16 }} accept
  ip daddr {{ 224.0.0.0/24, 239.255.255.250 }} accept
  counter drop
 }}
 chain forward {{ type filter hook forward priority -10; policy drop;
  oifname "{IFACE}" accept
  iifname "{IFACE}" ct state established,related accept
  oifname "tailscale0" accept
  oifname "br-*" ip daddr {{ 172.16.0.0/12, 192.168.0.0/16 }} accept
  ip daddr @endpoints udp dport {c['port']} accept
  oifname "{c['interface']}" udp dport 53 counter drop
  oifname "{c['interface']}" tcp dport 53 counter drop
  ip daddr @local4 accept
  ip6 daddr {{ fe80::/10, fc00::/7, ff02::/16 }} accept
  counter drop
 }}
 chain nat {{ type nat hook postrouting priority 101; policy accept;
  oifname "{IFACE}" masquerade
 }}
}}
'''
    exists = run('nft','list','table','inet','home_vpn',check=False).returncode == 0
    batch = ('delete table inet home_vpn\n' if exists else '')+text
    run('nft','-c','-f','-',input=batch)
    run('nft','-f','-',input=batch)


def routes():
    c = config()
    for subnet in c['local4']:
        run('ip','route','replace','throw',subnet,'table',TABLE)
    for endpoint in c['endpoints']:
        run('ip','route','replace',endpoint+'/32','via',c['gateway'],'dev',c['interface'],'table',TABLE)
    run('ip','route','replace','unreachable','default','metric','32760','table',TABLE)
    if run('ip','link','show',IFACE,check=False).returncode == 0:
        run('ip','route','replace','default','dev',IFACE,'metric','10','table',TABLE)
    rules = run('ip','rule','show').stdout
    # Honor connected routes (including newly created Docker bridges), never the
    # physical default route. The firewall still blocks public NIC egress.
    if '9000:' not in rules:
        run('ip','rule','add','priority','9000','lookup','main','suppress_prefixlength','0')
    else:
        assert '9000:\tfrom all lookup main suppress_prefixlength 0' in rules, 'Routing priority conflict'
    if '10000:' not in rules:
        run('ip','rule','add','priority','10000','lookup',TABLE)
    else:
        assert '10000:\tfrom all lookup '+TABLE in rules, 'Routing priority conflict'


def up():
    address = os.environ.get('ifconfig_local')
    if address:
        ipaddress.IPv4Address(address)
        run('ip','route','replace','default','dev',IFACE,'table',PROBE)
        run('ip','rule','del','priority','10010',check=False)
        run('ip','rule','add','priority','10010','from',address+'/32','lookup',PROBE)
    if (ROOT/'enabled').exists():
        routes()
        run('resolvectl','dns',IFACE,'1.1.1.1','1.0.0.1')
        run('resolvectl','domain',IFACE,'~.')
        run('resolvectl','default-route',IFACE,'yes')


def stage():
    assert not (ROOT/'enabled').exists(), 'Use a reviewed migration to replace active VPN settings'
    ROOT.mkdir(mode=0o700,exist_ok=True)
    defaults=json.loads(run('ip','-j','-4','route','show','default').stdout)
    assert len(defaults)==1, 'Ambiguous physical default route'
    route=defaults[0]
    source=Path('/mnt/server/vpn')
    text=(source/'vpn.conf').read_text()
    remote=next(l.split() for l in text.splitlines() if l.strip().startswith('remote '))
    endpoints=sorted({r[4][0] for r in socket.getaddrinfo(remote[1],None,socket.AF_INET)})
    assert endpoints, 'No VPN endpoints resolved'
    local=[]
    for r in json.loads(run('ip','-j','-4','route','show','table','main').stdout):
        dst=r.get('dst','default')
        if dst!='default' and ipaddress.ip_network(dst,strict=False).is_private:
            local.append(dst)
    c={'interface':route['dev'],'gateway':route['gateway'],'local4':local,
       'endpoints':endpoints,'port':int(remote[2]),'provider_hostname':remote[1]}
    (ROOT/'network.json').write_text(json.dumps(c,indent=2)+'\n')
    drop={'remote','dev','proto','redirect-gateway','route','route-ipv6','route-nopull',
          'route-noexec','script-security','up','down','up-restart','down-pre',
          'user','group','log','log-append','status','daemon','writepid','persist-tun'}
    lines=[]
    for line in text.splitlines():
        parts=line.strip().split()
        if not parts or parts[0].startswith(('#',';')):continue
        if parts[0] in drop:continue
        if parts[0] in {'auth-user-pass','ca','cert','key'}:
            original=source/Path(parts[1]).name
            target=ROOT/original.name
            shutil.copyfile(original,target);target.chmod(0o600)
            line=parts[0]+' '+str(target)
        lines.append(line)
    lines += ['dev '+IFACE,'dev-type tun','proto udp','route-nopull','route-noexec',
              'script-security 2','up '+SCRIPT+'-up','auth-nocache','verb 3',
              'connect-retry 5 30','resolv-retry 0']
    lines += [f'remote {ip} {c["port"]}' for ip in endpoints]
    (ROOT/'client.conf').write_text('\n'.join(lines)+'\n')
    for p in ROOT.iterdir():
        if p.is_file():p.chmod(0o600)
    shutil.copyfile(Path(__file__),SCRIPT);Path(SCRIPT).chmod(0o755)
    Path(SCRIPT+'-up').write_text('#!/bin/sh\nexec '+SCRIPT+' up\n');Path(SCRIPT+'-up').chmod(0o755)
    units=Path('/etc/systemd/system')
    (units/'home-server-vpn.service').write_text(f'''[Unit]
Description=Home server encrypted internet egress
After=network-online.target home-server-vpn-firewall.service
Wants=network-online.target
[Service]
Type=simple
ExecStart=/usr/sbin/openvpn --config {ROOT}/client.conf
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
''')
    (units/'home-server-vpn-firewall.service').write_text(f'''[Unit]
Description=Fail-closed host and Docker VPN egress firewall
DefaultDependencies=no
After=local-fs.target
Before=network-pre.target
Wants=network-pre.target
ConditionPathExists={ROOT}/enabled
[Service]
Type=oneshot
ExecStart={SCRIPT} firewall
RemainAfterExit=yes
[Install]
WantedBy=network-pre.target
''')
    run('systemctl','daemon-reload')
    run('systemctl','start','home-server-vpn.service')
    print('Staged isolated host tunnel; global routes and firewall unchanged')


def activate():
    assert run('ip','link','show',IFACE,check=False).returncode==0, 'Tunnel must be staged and verified first'
    run('systemd-run','--unit=home-vpn-rollback','--on-active=5m',SCRIPT,'rollback')
    (ROOT/'enabled').touch(mode=0o600)
    firewall()
    routes()
    run('resolvectl','dns',IFACE,'1.1.1.1','1.0.0.1')
    run('resolvectl','domain',IFACE,'~.')
    run('resolvectl','default-route',IFACE,'yes')
    run('systemctl','start','home-server-vpn-firewall.service')
    print('Host and forwarded traffic protected; automatic rollback in five minutes until commit')


def commit():
    assert (ROOT/'enabled').exists()
    run('nft','list','table','inet','home_vpn')
    run('systemctl','is-active','home-server-vpn.service')
    for name in ['NetworkManager','docker']:
        d=Path('/etc/systemd/system')/(name+'.service.d');d.mkdir(exist_ok=True)
        (d/'home-vpn-firewall.conf').write_text('[Unit]\nRequires=home-server-vpn-firewall.service\nAfter=home-server-vpn-firewall.service\n')
    run('systemctl','daemon-reload')
    run('systemctl','enable','home-server-vpn-firewall.service','home-server-vpn.service')
    run('systemctl','stop','home-vpn-rollback.timer',check=False)
    print('Committed persistent VPN protection; rollback timer cancelled')


def rollback():
    # A migrated torrent client must never become direct-egress during rollback.
    qbit=run('docker','inspect','qbittorrent',check=False)
    if qbit.returncode==0:
        q=json.loads(qbit.stdout)[0]
        if q['State']['Running'] and not q['HostConfig']['NetworkMode'].startswith('container:'):
            run('docker','stop','qbittorrent')
    (ROOT/'enabled').unlink(missing_ok=True)
    run('nft','delete','table','inet','home_vpn',check=False)
    run('ip','rule','del','priority','10000','lookup',TABLE,check=False)
    run('ip','rule','del','priority','9000','lookup','main','suppress_prefixlength','0',check=False)
    run('ip','route','flush','table',TABLE,check=False)
    run('resolvectl','revert',IFACE,check=False)
    run('systemctl','disable','home-server-vpn-firewall.service','home-server-vpn.service',check=False)
    for name in ['NetworkManager','docker']:
        (Path('/etc/systemd/system')/(name+'.service.d')/'home-vpn-firewall.conf').unlink(missing_ok=True)
    run('systemctl','daemon-reload')
    print('Rolled back host egress policy; staged tunnel retained')


if __name__=='__main__':
    os.umask(0o077)
    assert os.geteuid()==0, 'Run via the authorized root maintenance flow'
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['stage','activate','commit','rollback','up','firewall'])
    globals()[parser.parse_args().action]()
