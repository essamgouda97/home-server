# Home server operations

Last inspected: 2026-09-14. Host: Ubuntu 22.04.5 LTS, Intel i5-8600K (6 cores),
16 GB RAM, GTX 1070 (8 GB). Media/config data is under `/mnt/server` on a mergerfs
pool spanning SSD and HDD. The pool has approximately 893 GB available; the HDD
branch is 86% full. The OS, home, and var partitions have ample free space.

## Connect and work

From the Mac:

```sh
ssh home-server
cd ~/workspace
git clone git@github.com:essamgouda97/PROJECT.git
cd PROJECT
tmux new -As project
codex
```

Detach from tmux with Ctrl-b, then d. Reconnect with `tmux attach -t project`.
For a development web server bound to loopback, run this on the Mac:

```sh
ssh -L 5173:127.0.0.1:5173 home-server
```

Then open `http://localhost:5173`. Use project-specific virtual environments,
lockfiles, and Docker Compose project names. Keep project databases and package
environments separate from the media stack.

The Mac SSH alias maps `home-server` to `egouda@10.0.0.182`. The old numeric SSH
entry was preserved. Both local and server checkouts are at `~/workspace/home-server`.
GitHub access using the server's existing SSH identity was verified.

Codex CLI 0.154.0 is installed and authenticated with ChatGPT. An actual read-only
request returned `CODEX_AUTH_OK`. Authentication was transferred over SSH following
[OpenAI's documented headless login method](https://developers.openai.com/codex/auth/).
`~/.codex` is mode 700 and `auth.json` is mode 600. Never commit or print this file.
Run `codex login status` to check it or `codex login --device-auth` if a fresh login
is needed. Sessions consume the signed-in ChatGPT account's Codex allowance.

Tools available: Node 22.17.0 through nvm, npm, pnpm 12.4.1, Python 3.10,
uv, git, gcc/g++, make, tmux, Docker/Compose, ripgrep 15.2.0, GitHub CLI 2.100.0.
GitHub CLI is installed but has no separate API login; SSH Git access works.
Use `gh auth login` only if a project needs API operations through gh.
The noninteractive SSH path is set in `~/.zshenv`; interactive nvm still works.

## Network and services

The router reservation is `10.0.0.182`, wired MAC `00:E0:4C:68:2E:C6`.
NetworkManager uses DHCP; there is no old static OS address to remove.
Edit `SERVER_IP` and `LAN_SUBNET` in `server.conf` when moving networks. Both the
Makefile and documented Compose invocations load that file and the private `.env`.
Update `/mnt/server/dnsmasq/dnsmasq.conf` and client DNS at the same time.

On this Mac, `/etc/resolver/lan` routes only `.lan` to the home server, preserving
the VPN's resolver for other domains. To configure another Mac:

```sh
sudo sh scripts/setup-mac-dns.sh 10.0.0.182
```

Other devices must use `10.0.0.182` as DNS or use the IP and port directly.
This change did not alter router-wide DNS or public port forwarding.
The Rogers Xfinity gateway's Local IP Network, Rogers Network, and Advanced
pages were inspected: this firmware exposes no custom DHCP DNS setting.

| Name | LAN URL | Direct port |
|---|---|---:|
| Homarr dashboard | http://home.lan | 3000 |
| Jellyfin | http://jellyfin.lan | 8096 |
| Jellyfin Vue | http://vue.lan | 8097 |
| Jellyseerr requests | http://requests.lan | 5055 |
| Sonarr | http://sonarr.lan | 8989 |
| Radarr | http://radarr.lan | 7878 |
| qBittorrent | http://torrents.lan | 15080 |
| Prowlarr | http://prowlarr.lan | 9696 |
| Uptime Kuma | http://status.lan | 3001 |
| Portainer | http://portainer.lan | 9000 |
| NZBGet | http://nzbget.lan | 6789 |
| Speedtest Tracker | http://speedtest.lan | 8765 |
| Nginx Proxy Manager admin | http://10.0.0.182:81 | 81 |

Additional containers: dnsmasq, VPN gateway, FlareSolverr, Recyclarr, Watchtower.
Total: 18. Watchtower is configured to monitor images, not automatically update them.
It explicitly uses Docker API 1.44 for compatibility with Docker Engine 29.
DNS's web admin binds only to loopback; tunnel port 5380 over SSH if needed.

DNS is deliberately started by the enabled `dnsmasq-docker.service` after Docker
and network readiness, with Docker restart policy `no`. Keep its unit template in
`templates/systemd/`. Its BusyBox nslookup ignores the explicit server parameter;
the container has an explicit loopback DNS override, with `no-resolv` in dnsmasq
to prevent forwarding loops. Both UDP and TCP DNS responses are checked from the Mac.

Internal connections use Docker names: `jellyfin`, `sonarr`, `radarr`, `prowlarr`,
and `vpn-gateway`. qBittorrent shares the VPN gateway network namespace. Its
external IP was verified to differ from the host's external IP. The VPN has a
return route for `10.0.0.0/24`; the host itself retains its normal default route.

## Remote access with Tailscale

Tailscale 1.102.4 was installed from its official signed Ubuntu package repository
on the server and its notarized standalone macOS package on the Mac. The server's
`tailscaled` system service is enabled at boot. Installation left all existing
network and server health checks passing. Account sign-in and remote verification
are still pending; installation alone does not enable remote access.

To reproduce installation on Ubuntu 22.04:

```sh
sudo bash scripts/setup-tailscale.sh egouda
tailscale up --accept-dns=false --hostname=home-server --operator=egouda \
  --advertise-routes=10.0.0.182/32
```

Complete the generated browser sign-in using the same personal Tailscale account
as the client devices. In the Tailscale admin console, approve only the advertised
`10.0.0.182/32` route, then add a restricted DNS nameserver `10.0.0.182` for domain
`lan`. This makes the existing `.lan` URLs and IP/port addresses reachable over
Tailscale without routing access to the rest of the home network. Clients must
accept Tailscale DNS and subnet routes (Linux clients need `--accept-routes`).
The server deliberately does not accept tailnet DNS, avoiding a DNS loop.
IPv4 forwarding is already enabled by Docker on this host.

Keep Tailscale connected on the Mac and sign in to the same account on phones or
other clients. Retain each service's existing login. This setup does not require
router port forwarding, a public Funnel, an exit node, or Tailscale SSH; existing
OpenSSH keys continue to apply. Tailscale credentials remain in its private system
state and must never be committed.

After setup, verify the Mac route to `10.0.0.182` uses Tailscale, test both DNS
transports and service URLs with `make check-network`, and run `make check-server`
on the server. An additional phone test on cellular verifies access from outside
the home network. For rollback, disconnect Tailscale on the client, remove the
restricted DNS entry and approved route from the admin console, and run
`tailscale down` on the server; LAN access remains available.

## Changes and verification

- Fixed DNS bindings/answers and VPN LAN routing for the new subnet.
- Fixed Sonarr/Radarr download clients and Jellyseerr connections; download-client
  API tests passed and Jellyseerr resumed library synchronization.
- Updated Jellyfin Enhanced links to the new LAN IP after checking for active playback.
- Disabled legacy Jackett indexers pointing at the retired service. Removed
  unsupported BitSearch entries after exporting their settings. Working Prowlarr
  integrations remain configured.
- Updated Sonarr to 4.0.19.2979, Radarr to 6.3.0.10514, Prowlarr to 2.5.2.5491.
  Their application health APIs reported no warnings after the updates.
- Migrated Homarr's existing anonymous-volume contents to
  `/mnt/server/homarr/appdata`. Set its default home board to the existing private
  board. Browser navigation reaches login; the board remains private.
- Rotated Homarr session/encryption secrets that matched published repository
  history. Re-encrypted and round-trip verified all six integration secrets.
- Paused the saved Ollama monitor because no Ollama service is deployed.
- Stopped and disabled OpenClaw/Servo at the owner's request. Data remains intact.
  `make start` respects disabled agents and now propagates Compose failures.

Run from the repository:

```sh
make urls
make check-network                 # Mac or server: DNS, direct ports, proxies
make check-server                  # server: also containers, apps, disks, Codex
docker compose --env-file server.conf --env-file .env config --quiet
```

The health command is read-only. It accepts expected authentication challenges
and distinguishes HTTP reachability from an authenticated workflow. It does not
start downloads, send Telegram messages, or play a media item. GPU visibility was
checked with nvidia-smi. Full library playback was not exercised; the hardware
encoding check after the kernel upgrade is documented below.

Final verification after package updates and `make start`: all 18 containers
running, all configured container healthchecks healthy, all 13 active Uptime Kuma
monitors up, no system/user failed units, and no Sonarr/Radarr/Prowlarr health
warnings. Both `make check-network` from the Mac and `make check-server` from the
server completed with zero failing checks. Servo remained inactive and disabled
after `make start`. All three physical drives passed SMART overall-health checks;
an extended surface/self-test was not run.

## Backups and rollback

Private maintenance snapshots are under:
`~/.local/state/home-server-maintenance/2026-09-14/` on the server (mode 700).
They include original Compose/config files, application API settings, the prior
Homarr database and `.env`, the old container image IDs, and a stopped-service
archive of Sonarr/Radarr/Prowlarr config data. Uptime Kuma's consistent snapshot is
`/mnt/server/uptimekuma/data/kuma-before-20260914.db`.

To roll back an application update, stop that application, preserve its current
data separately, restore its configuration from `servarr-before-update.tar.gz`,
and recreate it with its recorded original image ID. Do not run an old application
against a database migrated by a newer release without restoring its matching backup.
For Homarr key rollback, restore both the corresponding DB and private `.env`.

The old anonymous Homarr volume and prior data directories were retained. Do not
prune volumes until backup/recovery requirements have been reviewed. These are
local recovery snapshots, not an off-server backup strategy; no off-server backup
destination or schedule has been configured.

## Remaining maintenance and security

The public Git history contains an old Servo archive with `.env`, OpenClaw config,
and provider auth profiles. The archive is removed from the current tracked tree
and `backups/` is ignored, but it still exists in public Git history. Treat historical credentials
as exposed: revoke/reissue them with their providers. Removing Git history alone
does not revoke credentials or remove copies already downloaded. No public history
rewrite or force-push was performed. Homarr's live secrets have already been rotated.
The owner explicitly chose to keep the repository public and defer history cleanup.

Do not publish new credentials or maintenance snapshots. The repo is public.
Files containing local secrets remain outside version control.

For Ubuntu updates and SMART health, use `sudo sh scripts/update-host.sh` on the
server. This preserves configuration, avoids package removal, and never reboots.
This script completed successfully on 2026-09-14. Docker Engine is now 29.8.0 and
Compose is 5.5.1; `dpkg --audit` reported no unfinished package configuration.
The subsequent kernel/GPU maintenance installed kernel `6.8.0-138-generic` and
NVIDIA `580.178.04`, followed by an explicitly authorized reboot. The new boot ID
was verified over SSH. `/var/run/reboot-required` is cleared, and `dpkg --audit`
reports no unfinished package configuration. The old kernel remains installed as
an emergency boot fallback. Only unrelated fwupd/netplan updates remain pending.

To repeat coordinated kernel/GPU maintenance, inspect the APT plan first, then run:

```sh
sudo bash scripts/upgrade-kernel-nvidia.sh --reboot
```

Without `--reboot`, the script installs and verifies the upgrade but leaves the
reboot to the caller. It refuses package removals, verifies the new kernel and
initramfs, and checks that NVIDIA kernel-module and userspace versions match.
It logs to `/var/log/home-server-kernel-upgrade.log`. For remote work, run it as a
systemd transient service so SSH disconnection cannot interrupt installation.

After the reboot on 2026-09-14, all 18 containers started automatically without
manual starts/restarts. SSH, both DNS transports, reverse-proxy routes, both
physical media mounts and the mergerfs pool returned. Servo stayed disabled.
The GTX 1070 was visible with the new driver both on the host and inside Jellyfin.
A two-second synthetic 720p H.264 NVENC encode passed inside the Jellyfin container:

```sh
docker exec jellyfin /usr/lib/jellyfin-ffmpeg/ffmpeg \
  -hide_banner -loglevel error -f lavfi -i testsrc2=size=1280x720:rate=30 \
  -t 2 -c:v h264_nvenc -f null -
```

This verifies the actual GPU encoder without reading or changing media. Full
client playback remains a separate check. The VPN's external IP differs from the
host's, and Codex's ChatGPT login remains valid after the reboot.

Final checks after reboot: `make check-network` and `make check-server` both
passed with zero failing checks; all 13 active Uptime Kuma monitors were up.
There were no failed system or user services.
