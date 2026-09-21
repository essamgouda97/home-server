# Home-server VPN egress

Deployed and verified September 20, 2026. This protects the **home server**, not
the owner's Mac or every device on the household Wi-Fi.

## Deployed boundary

Host processes and Docker containers route public IPv4 internet traffic through
host OpenVPN interface `homevpn0`, using the existing authorized CyberGhost client
configuration. qBittorrent uses this shared boundary instead of a second failing
VPN container. Its `vpn-gateway` Docker alias preserves Nginx, Servarr, Homarr and
monitoring integrations. The web port remains loopback-only; jobs/data are retained.

The `inet home_vpn` nftables table guards host OUTPUT and Docker FORWARD with
default-drop policies. It preserves the existing ingress firewall. Direct public
IPv6 is blocked because this VPN profile provides IPv4. There is no general
established-connection bypass for physical internet egress.

Explicit exceptions preserve local LAN/Docker communication, DHCP/discovery,
encrypted Tailscale transport (its existing socket mark), tailnet traffic, and UDP
transport to configured VPN servers. These necessary local/transport exceptions
mean not every packet traverses CyberGhost. Public DNS follows the tunnel; direct
physical-interface DNS is blocked.

Routing follows Tailscale's existing rules. Priority 9000 honors connected main-table
routes while suppressing its default; priority 10000 uses VPN table 51820, which has
an unreachable fallback. New ordinary Docker bridges inherit internet protection
and connected local routes. Custom Docker ranges outside 172.16/12 and 192.168/16
need review of private-network allowances before publication.

## Persistence and credentials

- `home-server-vpn-firewall.service` loads before networking. Dedicated NetworkManager
  and Docker drop-ins require it.
- `home-server-vpn.service` manages host OpenVPN and reconnects it.
- `/usr/local/sbin/home-server-vpn` is the installed `scripts/host-vpn.py`.
- Root-only `/etc/home-server-vpn/` contains copied client credentials, generated
  configuration, routing parameters and enable marker. Never print or commit it.
- Provider endpoints are resolved to numeric addresses during staging, avoiding
  DNS through a dead tunnel during reconnect. If all saved endpoints are retired,
  refresh through an authorized maintenance session; never allow direct app egress
  as a workaround. Credential rotations must update the host's private copy.
- The retired VPN container was removed after saving its private definition. Its
  image and mounted files remain. Base Compose retains only an opt-in `legacy-vpn`
  recovery profile with restart disabled. The optional Proton overlay explicitly
  restores namespace sharing for a separately reviewed migration.

CyberGhost still lacks inbound port forwarding. This repairs connectivity and
egress protection; it cannot guarantee maximum peer reachability, anonymity,
tracker ratio, or protection from account sanctions.

## Reproduce and verify

Stage on a server with authorized client files under `/mnt/server/vpn`:

```sh
sudo python3 scripts/host-vpn.py stage
# Verify staged tunnel egress before changing global routing.
sudo /usr/local/sbin/home-server-vpn activate
# Five-minute rollback is armed during first activation.
python3 scripts/check-host-vpn.py
make check-network
make check-server
sudo /usr/local/sbin/home-server-vpn commit
```

For the initial migration, move qBittorrent to the checked-in Compose topology
after verifying the host boundary. Stop the old gateway before recreating the
client to release its ports. Back up client configuration/metadata outside Git.
Run `check-download-logins.py --local` before/after recreation and without `--local`
for final HTTPS login. Reload Nginx after the upstream container address changes.

`check-host-vpn.py` checks enabled/active units, effective routing, host/client
egress agreement and blocked direct physical IPv4/IPv6 probes. A private baseline
of pre-migration egress supplies an additional comparison if present; it is not a
permanent trusted provider-IP list.

Actual outage test: stopping the tunnel blocked host IPv4, physical IPv4/IPv6 and
Homarr-container internet access; SSH remained available. Egress recovered after
restart. Tailscale-IP SSH passed using the existing trusted server key. Systemd
units/dependency ordering were validated; no server reboot was performed.

Final checks passed: host VPN audit, local/HTTPS download-app login, Homarr OIDC,
gateway authorization including Mariam's restrictions, Mac network health and
full server health (zero failures; only available-update warnings).

## Recovery

Private snapshots under `~/.local/state/home-server-maintenance/host-vpn/` retain
the egress baseline, consistent qBittorrent metadata and retired container definition.
Do not restore old torrent state over newer jobs casually.

`sudo /usr/local/sbin/home-server-vpn rollback` removes the host egress policy. It
**stops migrated qBittorrent first** so torrents cannot fall back to the ISP. Other
apps regain the previous direct-egress behavior, so use only as an explicitly
chosen recovery action. After commit, ordinary outages stay fail-closed and do not
invoke rollback. Never disable the firewall to make a failing app reachable.

## ArabP2P and diagram

Both existing ArabP2P announces became working after migration; user-started
downloads progressed. Their announce credentials had been compared privately
against fresh metadata from the owner's new account. Unlimited seeding remains
enforced by `home-arabp2p-seeding.timer`. Actual credit requires uploaded bytes
accepted by the tracker.

The additive [editable Draw board](https://draw.home.egouda.xyz/?board=muaju06dplukfuiw429)
has 12 persisted elements verified through the authenticated API. It supersedes
the earlier board's unresolved connectivity status while preserving existing edits.

References: [OpenVPN route controls](https://openvpn.net/community-docs/community-articles/openvpn-2-5-manual.html),
[Tailscale policy routing](https://tailscale.com/docs/solutions/connect-kubernetes-pods-to-tailnet-using-sidecar).
