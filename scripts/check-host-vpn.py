#!/usr/bin/env python3
"""Read-only host/container VPN and direct-egress checks; no IPs or secrets logged."""
import ipaddress
import json
from pathlib import Path
import subprocess


def run(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=25)


def main():
    for unit in ['home-server-vpn.service', 'home-server-vpn-firewall.service']:
        assert run(['systemctl','is-active',unit]).returncode == 0, unit+' inactive'
        assert run(['systemctl','is-enabled',unit]).returncode == 0, unit+' not enabled'
    route=json.loads(run(['ip','-j','route','get','1.1.1.1']).stdout)
    assert route[0]['dev']=='homevpn0', 'Internet route does not select host VPN'
    baseline=Path.home()/'.local/state/home-server-maintenance/host-vpn/egress-baseline.json'
    old=json.loads(baseline.read_text())['normal'] if baseline.exists() else None
    addresses=[]
    for label,prefix in [('host',[]),('qbittorrent',['docker','exec','qbittorrent'])]:
        r=run(prefix+['curl','-4','--fail','--silent','--max-time','15','https://api.ipify.org'])
        assert r.returncode==0,label+' cannot reach internet through VPN'
        address=str(ipaddress.IPv4Address(r.stdout.strip()))
        assert address!=old,label+' is using pre-migration direct egress'
        addresses.append(address)
        print('PASS '+label+' VPN egress')
    assert len(set(addresses))==1,'Host and torrent-client egress differ'
    defaults=json.loads(run(['ip','-j','-4','route','show','table','main','default']).stdout)
    nic=defaults[0]['dev']
    for family,url in [('-4','http://1.1.1.1/cdn-cgi/trace'),('-6','http://[2606:4700:4700::1111]/cdn-cgi/trace')]:
        r=run(['curl',family,'--noproxy','*','--interface',nic,'--silent','--max-time','4',url])
        assert r.returncode!=0,'Direct '+family+' internet bypass succeeded'
        print('PASS direct '+family+' internet bypass blocked')
    print('PASS enabled host VPN services, route and shared container egress')


if __name__=='__main__':
    main()
