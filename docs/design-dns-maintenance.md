# Private design workspace and household DNS

Requested 2026-09-15. The owner selected a free, self-hosted Excalidraw experience
with saved boards and Codex MCP, replacing the initial tldraw request.

## Current work and acceptance

- Jellyseerr Jellyfin login recovered after an isolated Jellyfin restart; the
  actual browser reached Discover. Jellyfin 10.11.6 had
  `DbUpdateConcurrencyException` during authentication. Database backup passed
  integrity checking. This is recovery, not proof the upstream bug cannot recur.
  See [upstream report](https://github.com/jellyfin/jellyfin/issues/16304) and
  [upstream fix](https://github.com/jellyfin/jellyfin/pull/15368). Evaluate a pinned
  compatible upgrade separately; do not blindly recreate the `latest` image.
- Homarr used `.lan` URLs for probes that its container could not resolve.
  Internal probe addresses restore accurate reachability while retaining clean
  browser links. The media widget recovered with Jellyfin authentication.
- Pi-hole is staged at `10.0.0.182:1053` (TCP/UDP); dnsmasq still owns port 53.
  Router DHCP, client DNS, Tailscale DNS, and the host's DHCP configuration remain
  unchanged. Local lookup, public lookup, and ad blocking passed from the Mac.
- Excalidraw is at `http://draw.lan`, behind the same private login as Creative
  Drive (`egouda`). It is based on the MIT-licensed
  [mcp-excalidraw-local](https://github.com/sanjibdevnathlabs/mcp-excalidraw-local)
  revision `a1977d86f9529276ed1b97cbf1d05de4319c59cb`, with the reviewed patch in
  `config/excalidraw/`. This is not the proprietary Excalidraw+ product.
- The owner selected **planning a household DHCP migration with rollback**.
  Household cutover remains a separate step after the plan's prerequisites.

## Reproduce the whiteboard

On the server, from this repository:

```sh
sh scripts/prepare-excalidraw.sh
python3 scripts/configure-design-dns-proxies.py
python3 scripts/configure-dashboard-health.py
python3 scripts/check-excalidraw.py
```

The pinned upstream checkout is under `~/.local/share/home-server/excalidraw`.
SQLite data, uploaded images, and exports live under
`/srv/mergerfs/ssd/excalidraw` with UID 1000 and mode 700. Fonts are bundled locally.
The container has an internal-only Docker network shared with Nginx and Homarr;
the browser policy permits same-origin connections. The public upload MCP tool
is removed and rejects direct calls. Codex still processes the diagram content
you explicitly ask it to read or edit through your existing subscription.

The New board form creates a separate saved board. Use the board menu to return
to it. Each tab's `?board=` URL identifies its board. Autosave defaults on and runs
after three seconds of idle editing; Sync explicitly saves pending changes.
Board switching saves the current board first. Export `.excalidraw` files using
the native editor menu or `export_scene` MCP tool. This setup provides saved
boards, workspace separation, live editing, local images, snapshots and exports;
it does not implement Excalidraw+ accounts, billing, or all of its organizational
features. Board names can be organized by project (for example, `Home / Network`).

MCP is installed as `home-draw` on both machines:

```sh
# Mac
codex mcp add home-draw -- /usr/bin/ssh -T -o BatchMode=yes home-server docker exec -i excalidraw node dist/index.js
# Server
codex mcp add home-draw -- docker exec -i excalidraw node dist/index.js
```

Use `list_tenants` to list saved boards and `switch_tenant` to select the intended
board before drawing. Keep its browser tab open for screenshot/export rendering.
New Codex sessions load the connection. Configuration backups are private under
`~/.local/state/home-server-maintenance/codex/`. The upstream README's suggested
`~/.codex/mcp.json` is not used; the installed CLI manages its actual config.

## Pi-hole staging

On a fresh server, first start the main stack to create `home-server_proxy`.
Create the private password once without displaying it (existing secrets must
not be overwritten):

```sh
python3 - <<'PY'
from pathlib import Path
import os, secrets
os.umask(0o077)
path = Path.home() / '.config/home-server/secrets/pihole_password'
path.parent.mkdir(parents=True, exist_ok=True)
if not path.exists():
    with path.open('x') as out:
        out.write(secrets.token_urlsafe(32) + '\n')
PY
```

```sh
docker compose --env-file server.conf -f compose.pihole.yml -p home-dns up -d
dig @10.0.0.182 -p 1053 home.lan +short
dig @10.0.0.182 -p 1053 home.lan +tcp +short
dig @10.0.0.182 -p 1053 example.org +short
dig @10.0.0.182 -p 1053 doubleclick.net +short
```

The expected local answer is `10.0.0.182`; the blocked test answer is `0.0.0.0`.
Admin: `http://dns.lan/admin/`. The password is in the private server file
`~/.config/home-server/secrets/pihole_password`; never print or commit it.
DNS query logging is off and privacy level 3 avoids retaining household browsing
details. DHCP, router advertisements and NTP are disabled. No DHCP port is
published. Pi-hole uses public resolvers directly, avoiding a forwarding loop.

## Household DHCP migration plan — not executed

### Gateway inspection: 2026-09-15

Authenticated, read-only inspection confirmed:

- IPv4 gateway `10.0.0.1`, mask `255.255.255.0`, DHCP pool
  `10.0.0.2–10.0.0.253`, lease time **2 days**.
- No IPv4 DHCP enable/disable control on Local IP Network; Advanced exposes
  forwarding, triggering, remote management, DMZ and discovery only.
- IPv6 stateless auto-configuration is checked and disabled (locked on);
  stateful DHCPv6 is also checked. No custom DNS control is exposed here.
- Seven reserved entries, including the server and footage station. Full
  address/MAC inventory is saved privately on the Mac under
  `~/.local/state/home-server-maintenance/router/2026-09-15-reservations.txt`.
  Device listings are not a complete export of active lease expiration times.

**Decision: direct DHCP replacement on the current Rogers LAN is not ready for
cutover.** There is no verified supported way to disable only its IPv4 DHCP.
The current pool also leaves no useful disjoint migration pool. Do not shrink
it to one address or start a competing DHCP server as a workaround.

The workable migration path is a configurable router and Wi-Fi access point,
prepared offline first. Existing suitable hardware can be reused. Rogers
[documents bridge mode](https://www.rogers.com/support/internet/turn-bridge-mode-on-or-off-for-your-rogers-xfinity-gateway)
as disabling routing and built-in Wi-Fi; it also affects Pods and Wi-Fi TV.
Inventory those dependencies before selecting this route. Bridge mode has not
been enabled.

### Plan for a replacement router

1. Confirm available router/AP hardware and Rogers TV, phone, or Pod dependencies.
   Build the new LAN offline at `10.0.0.1/24`, import the seven reservations,
   and prepare Wi-Fi. Its WAN must remain disconnected from the current
   `10.0.0.0/24` LAN during this same-subnet preparation.
2. Prefer DHCP on the new router advertising Pi-hole `.182` as DNS. This meets
   the household goal while keeping address assignment independent of the home
   server. If Pi-hole itself must provide DHCP, disable the new router's DHCP
   and pass the isolated Docker DHCP tests below first.
3. Complete the fixed server address, DNS port-53, lease-conflict and IPv6
   prerequisites below. Import existing leases if supported; otherwise prepare
   a documented renewal/pool transition accounting for all 48-hour leases.
4. During an agreed maintenance window, connect a recovery laptop directly to
   Rogers, enable bridge mode, and connect the new router WAN to Rogers. Move
   the LAN switch/AP to the new router. Keep only one router serving the LAN.
   Test one wired and one wireless pilot before moving the remaining household.
5. Roll back on lost gateway/internet/DNS, conflicting leases, inaccessible
   required services, or failure to pass the pilot within ten minutes: disconnect
   the new router from the household LAN first; directly access Rogers at
   `10.0.0.1`, disable bridge mode, restore original switch/AP cabling, and verify
   original Wi-Fi/DHCP. Stop Pi-hole DHCP first if it was enabled. Restore
   dnsmasq at `.182:53` if DNS was moved, then renew pilot leases and run checks.
   Do not factory-reset the gateway as the normal rollback method.

The router transition needs an operator physically present; no unattended timer
can be assumed to reverse a web-UI bridge-mode change. The separate host/DNS
changes must have tested automatic rollback before the router window starts.
No hardware purchase or bridge-mode change is authorized by this planning step.

Known baseline: router `10.0.0.1/24`; server `10.0.0.182`, wired interface `enp2s0`,
MAC `00:E0:4C:68:2E:C6`; server obtains its address from a router reservation.
Observed DHCP lease length is **48 hours**. Rogers firmware has no custom DHCP
DNS field. Turning off router DHCP alone will not immediately change existing
clients' DNS.

### Before scheduling cutover

1. Read and privately record the router's DHCP start/end, subnet, reservations,
   connected clients, and IPv6 router-advertisement/DNS settings. Export settings
   if supported. Do not publish household device identifiers in Git.
2. Confirm router DHCP can actually be disabled without bridge mode. If firmware
   cannot do this, stop: use a configurable downstream router rather than running
   competing DHCP servers. Retain Rogers routing, NAT, and Wi-Fi.
3. Give the home server an independent, conflict-checked fixed address at
   `10.0.0.182` before relying on its DHCP service. Preserve the existing
   NetworkManager profile and prepare a timed automatic rollback; verify SSH,
   gateway access, and internet before committing that change. The DHCP server
   must not depend on obtaining its own lease from itself.
4. Build an isolated DHCP test network with a disposable client and the final
   Pi-hole configuration. Verify address, mask, router, DNS option, reservation,
   renew/rebind, lease persistence, and service restart. Never broadcast this test
   on the household network.
5. Choose a migration address pool only after checking existing leases and
   reservations. Exclude all fixed addresses, especially `.182`, router `.1`, and
   infrastructure devices. Existing 48-hour leases must not collide with newly
   issued addresses: preserve/import mappings or use a verified disjoint pool.
6. Design Docker DHCP delivery deliberately: host networking with restricted
   interface/bindings, or a LAN address with tested broadcast reception. Simply
   publishing UDP 67 from the current bridge container is insufficient.
7. Review IPv6 DNS advertisements and encrypted DNS on pilot clients. Otherwise
   clients may bypass Pi-hole or fail to resolve `.lan` despite correct IPv4 DHCP.
8. Keep one laptop with a verified recovery address and direct router access.
   Record the original DHCP/DNS values and rollback commands privately. Have
   local physical access available; do not attempt this only through Tailscale.

### Direct DHCP cutover — conditional alternative only

Use this branch only if a supported standalone DHCP-off control is subsequently
verified. It is not executable with the gateway controls observed today.

1. Back up Pi-hole's database/config, dnsmasq config/unit, NetworkManager profile,
   router settings, and old container image IDs outside Git.
2. Keep the gateway at `.1`. With DHCP still disabled in Pi-hole, move tested DNS
   from staging port 1053 to standard port 53 at `.182`, replacing dnsmasq only
   after a rollback timer is armed. Validate UDP/TCP and public lookup immediately.
   Preserve the `.lan` wildcard so existing Mac and Tailscale routes keep working.
3. Disable Rogers DHCP, then enable tested Pi-hole DHCP. At no point intentionally
   run two DHCP servers on the same LAN. Advertise gateway `.1`, DNS `.182`, and
   the reviewed pool/reservations. Use a short initial lease for commissioning.
4. Renew a single pilot client's lease. Verify `home.lan`, Requests login, a public
   site, ad blocking, and connectivity with Tailscale both off and on as applicable.
5. Only after the pilot passes, renew remaining clients gradually. Some sleeping
   devices will retain old DNS until renewal. Verify phones, TVs, and smart-home
   devices before restoring a normal lease duration.
6. Run `make check-network` from the Mac and `make check-server` from the server;
   confirm the pilot's actual DNS server and test Pi-hole service restart.

### Direct DHCP rollback order

1. Disable Pi-hole DHCP first, then restore Rogers DHCP with the recorded pool and
   reservations. Avoid simultaneous DHCP services during recovery too.
2. Stop the production Pi-hole DNS binding, restore dnsmasq's exact config and
   original systemd-managed startup, then verify `.lan` and public DNS over UDP/TCP.
3. Renew affected client leases. Clients retaining Pi-hole-issued DNS continue
   reaching the restored dnsmasq at `.182` until they renew onto Rogers DNS.
4. Restore the host NetworkManager profile only if necessary and only with the
   recovery connection available. Retain the known server address throughout.
5. Re-run both health commands. Return Pi-hole to its isolated staging port only
   after household connectivity is stable.

No public "secondary DNS" is proposed as a transparent backup: clients may use
it at any time and it cannot resolve private `.lan` names. Real redundancy needs
a second local resolver with the same local records, preferably on separate
hardware/power. Server failure remains a household DNS dependency after cutover.

## Recovery snapshots

Whiteboard acceptance passed on 2026-09-15: browser edits autosaved to SQLite;
two tabs displayed the same new shape without reload; separate board selection
remained independent; URL selection and saved drawings survived container
recreation. Saved boards are Default, Home server architecture, and Planning.
The architecture board contains a Codex-generated diagram. Planning contains
two clearly disposable test shapes. MCP viewport control was verified in the
browser. This verifies persistence and live synchronization, not conflict-free
simultaneous editing of the same shape by multiple people.

Final `make check-network` on the Mac and `make check-server` on the server both
reported zero failing checks. Separate authenticated HTTP/MCP checks passed
for the whiteboard; Pi-hole staging passed local/public/ad-blocking DNS tests
and an administrator API sign-in check. Router settings were inspected only.

Jellyfin: `~/.local/state/home-server-maintenance/2026-09-15/jellyfin-login/`.
Homarr: `~/.local/state/home-server-maintenance/dashboard/`.
Proxy config: `~/.local/state/home-server-maintenance/proxies/`.
Whiteboard: `~/.local/state/home-server-maintenance/excalidraw/`.
`excalidraw-backup.timer` takes a consistent SQLite snapshot daily at 04:30 with
up to ten minutes of jitter; each snapshot passes an integrity check. It is a
local recovery copy on the same server, not an off-server backup. Snapshots are
retained; review disk usage periodically. Re-run manually with
`python3 scripts/backup-excalidraw.py`.
Restore SQLite snapshots with the relevant service stopped; preserve the current
database first. Never restore over a running SQLite database or delete its WAL.
