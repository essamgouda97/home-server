# Arabic torrent seeding

## Current diagnosis

The media library and the torrent queue are separate records. Radarr imported 65
completed downloads and was configured to remove each completed torrent job from
qBittorrent. The media files remained available to Jellyfin, but qBittorrent was
left with one torrent and only one `.torrent`/resume pair. A movie file by itself
does not contain the tracker metadata needed to seed it.

The current CyberGhost VPN connection also has no inbound forwarded port.
Outgoing peer connections can still upload, but peers that cannot accept inbound
connections cannot reach this server. CyberGhost documents that it does not
support port forwarding, so this cannot be repaired by opening a port on the home
router or adding a Docker port mapping.

## Deployed policy

Run on the server:

```sh
python3 scripts/configure-seeding-policy.py
python3 scripts/check-seeding-policy.py
```

The configuration helper:

- makes Radarr and Sonarr retain completed torrent jobs after import;
- pauses a torrent at ratio 2.0 instead of deleting its data or metadata;
- permits 20 active uploads and 50 active torrents;
- excludes slow torrents from consuming queue slots;
- saves non-secret rollback metadata privately under
  `~/.local/state/home-server-maintenance/seeding-policy/`.

The once-per-minute home metrics collector publishes aggregate qBittorrent counts,
active uploads, demand, outstanding ratios, upload speed and a policy-health bit.
Grafana alerts if collection fails, the policy drifts, or demand remains visible
without an upload for six hours. No torrent title, hash, tracker, passkey or path is
included in Prometheus.

Ratio 2.0 is a conservative home default, not a claim about any specific
tracker's rules. If a tracker requires a higher ratio or a minimum seed duration,
follow the stricter rule. Do not use a short inactive-seeding cutoff: a torrent
with no current demand still needs to remain available. qBittorrent's displayed
ratio is client-local; the tracker's recorded ratio is authoritative.

## Restore an existing film to the seed queue

Only use a `.torrent` file obtained from the same authorized tracker/account as
the original download.

1. In qBittorrent, add the original `.torrent` in a paused state.
2. Select the exact existing download directory. Do not rename or reorganize
   files before verification.
3. Force recheck. Resume only when qBittorrent reports 100% complete.
4. Keep the Radarr category and add an `arabic` tag for easier auditing.
5. Confirm the tracker reports the torrent as seeding. The local audit deliberately
   reports counts and policy state without exposing movie names, tracker URLs or
   passkeys.

If the force recheck is below 100%, stop. Pointing at a similar Jellyfin file is
not sufficient because release filenames and byte content must match exactly.
Never bypass the hash check.

## Reliable inbound seeding

The clean migration is from the legacy `dperson/openvpn-client` container and
CyberGhost to Gluetun with a VPN provider that explicitly supports port forwarding.
Proton VPN is the recommended fit: its paid plans support P2P port forwarding,
and Gluetun can request the forwarded port and update qBittorrent whenever that
random port changes. This preserves the VPN kill switch and does not expose the
qBittorrent web interface.

Migration requires a compatible VPN subscription and its dedicated WireGuard or
OpenVPN credentials. Prepare it as a separate Compose profile, verify external IP,
DNS, kill-switch behavior and the forwarded port, then move qBittorrent during a
quiet window. Keep the existing CyberGhost configuration as rollback until upload
traffic is proven. Do not change household router forwarding for this migration.

The opt-in implementation is versioned in `compose.vpn-forwarding.yml`. It pins
Gluetun, requests a Canadian Proton P2P server and stores the random forwarded port
under `/mnt/server/vpn/gluetun`. A host timer synchronizes that port into
qBittorrent using its private runtime credential and reannounces existing jobs.
The overlay is deliberately not part of normal `make start`.

Provision and migrate during a quiet window:

1. Generate a Proton WireGuard configuration with NAT-PMP enabled. Save only the
   private key in `~/.config/home-server/secrets/protonvpn.env`, following
   `config/vpn/protonvpn.env.example`, and set mode 600.
2. Run `python3 scripts/prepare-forwarding-vpn.py`.
3. Back up the current VPN and qBittorrent configuration outside Git.
4. Run `docker compose --env-file server.conf --env-file .env -f docker-compose.yml
   -f compose.vpn-forwarding.yml up -d vpn qbittorrent`.
5. Enable `home-qbittorrent-port-sync.timer`, wait for a forwarded port, then run
   `scripts/sync-qbittorrent-forwarded-port.py` and
   `scripts/check-forwarding-vpn.py`.
6. Require the real external probe, distinct VPN egress, qBittorrent login audit,
   DNS, server and network checks to pass before calling the migration complete.

Rollback disables the port-sync timer and starts `vpn qbittorrent` using only the
base Compose file. Restore the pre-migration qBittorrent preferences if necessary;
do not restore its database over newer torrent jobs. The Gluetun state and Proton
credential can remain offline for investigation without affecting CyberGhost.

References:

- [qBittorrent option behavior](https://github.com/qbittorrent/qBittorrent/wiki/Explanation-of-Options-in-qBittorrent)
- [qBittorrent Web API share limits](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-%28qBittorrent-4.1%29)
- [CyberGhost port-forwarding limitation](https://www.cyberghostvpn.com/privacyhub/port-forwarding/)
- [Proton VPN manual port forwarding](https://protonvpn.com/support/port-forwarding-manual-setup)
- [Gluetun port-forwarding integration](https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/vpn-port-forwarding.md)
