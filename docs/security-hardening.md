# Home-server security and recovery

Applied September 16, 2026. Read together with [operations](server-operations.md),
[service registration](service-registration.md), and [monitoring](monitoring.md).

## Access boundaries

- Household DNS remains Cloudflare DNS-only: `home.egouda.xyz` and its wildcard
  resolve to private `10.0.0.182`. No public Cloudflare Tunnel/Funnel was enabled.
  The HTTPS name does not mean the server is internet-published.
- NPM HTTP/HTTPS bind only the private IPv4 address. Web-app backends bind loopback;
  integrations continue using Docker names. NPM admin is loopback port 81:
  `ssh -L 8181:127.0.0.1:81 home-server`, then open `http://localhost:8181`.
- Jellyfin retains private LAN port 8096 for native TV clients, plus loopback for
  local verification. SMB/DNS/Home Assistant retain their private LAN bindings.
- UFW denies unsolicited host ingress, allows the household LAN, authenticated
  Tailscale interface, container subnet integrations, and UDP 41641 for Tailscale.
- Docker bypasses UFW for published ports. The persistent
  `home-server-docker-firewall.service` installs a DOCKER-USER chain that rejects
  non-LAN sources arriving on `enp2s0`, preserving established traffic and Tailscale.
  Update the interface/subnet in `scripts/docker-ingress-firewall.sh` after a move.
- OpenSSH accepts keys, disables password authentication/root login/X11 forwarding.
  Existing independent SSH and service checks passed before cancelling rollback.
  Legacy vsftpd is disabled. Servo remains disabled.
- Tailnet policy is [tracked here](../config/security/tailscale-policy.json): only
  `essamgouda97@github` may connect. Positive/negative access tests are included.
  Only the server's `/32` LAN route is advertised. Family use on home Wi-Fi is
  unaffected; give future remote family accounts explicit limited grants.
- GitHub has MFA and a passkey. Cloudflare now has the `Home admin passkey`
  security key; the owner confirmed recovery codes saved in 1Password.
- Certificate renewal uses a token restricted to DNS editing on `egouda.xyz`.
  A disposable TXT create/read/delete test and certbot dry-run both passed.
  The original broad Mac token serves other projects and was not revoked globally.

## Password source of truth

The owner expressly authorized personal use of the work 1Password account.
Vault creation was forbidden by that account's permissions, so items are in its
**Employee** vault (API type **PERSONAL**), tagged **HomeServer**, named
`Home Server — <service>`. Do not put these in a company shared vault.

Distinct credentials have been applied and real HTTPS authentication verified for:
Homarr, Jellyfin, qBittorrent, Sonarr, Radarr, Prowlarr, Draw, Life Dashboard,
Footage/ingest, ODS proxy protection, and Grafana. Jellyseerr uses the **Jellyfin**
identity and credential; do not invent another password for that linked login.
Mariam's separate account is unchanged.

Runtime private files are under `~/.config/home-server/secrets` on the server:

- `service-passwords.json`: applied service credentials, mode 600.
- `pending-service-passwords.json`: vault-verified credentials awaiting/applying migration.
- `creative_password`: remaining legacy storage/Home Assistant/OS recovery secret.
  **Do not overwrite this to rotate a single service.** Finder/SMB and other legacy
  consumers need an explicit coordinated migration.
- `grafana_password`: Docker bootstrap secret, owned by UID 472, mode 600.
- `cloudflare-dns.ini`: narrowly scoped certificate token, mode 600.

The main AGENTS.md policy now requires unique credentials. The old shared-password
instruction is superseded. Read credentials through `scripts/service_credentials.py`;
never print values, export them into command arguments, or commit them.

### Save before changing an app

On the Mac, authorize the 1Password desktop prompt, then run:

```sh
python3 scripts/prepare-security-credentials.py --service example \
  --url https://example.home.egouda.xyz/
```

This creates a random password only if the tagged item is absent, reads it back
from the vault, and stages it over encrypted SSH stdin. It does **not** change the
app. Repeated runs reuse the existing vault item. Additional `--url` arguments
support one identity used at multiple sites. Store human logins as Login items so
1Password can fill them; recovery/encryption secrets are separate Password items.

Then back up the app, change the credential via its supported API, update all
consumers, test a real login at the final HTTPS URL, and write the successfully
applied value to `service-passwords.json`. Stage and apply one migration at a time.
Do not log API response bodies, password hashes, cookies, tokens, or settings.

The `align-*-credentials/password.py` historical filenames now migrate to staged
individual passwords; they no longer restore password reuse. Rotation snapshots
live outside Git under `~/.local/state/home-server-maintenance/`.

### Recovery

1Password also holds `legacy-household-recovery`, `backup-encryption`, and
`cloudflare-certificate-dns`. Keep your SSH private key and vault recovery method
available independently of the server. A work-account recovery dependency remains;
a separate personal account can later receive these items without changing services.

Host protection recovery script: `/root/home-server-security-20260916/rollback.sh`.
It restores the earlier open state and should be used only for recovery. Read it
before use. Deployment had a ten-minute rollback timer; it is now cancelled.
Do not rerun `harden-host.sh` without treating it as another timed rollout.

## Backups

`scripts/backup-security-to-mac.py` creates a server-side configuration snapshot,
uses SQLite's online backup API, encrypts it with restic onto the Mac, verifies all
repository data, and streams a restore into a disposable server directory for
SQLite integrity checks. The first restore verified **37 databases**. Later
snapshots also include Grafana, Portainer, Uptime Kuma, and Speedtest configuration.

- Mac destination: `~/Library/Application Support/HomeServer/EncryptedBackups`.
- Daily Mac launch agent: `local.home-server.security-backup`, 18:30 local time.
  The Mac must be awake/reachable; missed calendar work runs when launchd resumes.
- Logs: `~/Library/Logs/home-server/security-backup*.log`.
- Encryption key: 1Password plus Mac mode-600 `~/.config/home-server/backup-password`.
- Low Mac disk space (under 1.5 GiB) defers backup rather than filling the disk.
- Config snapshots exclude media, original footage, logs, caches, and Prometheus
  metric history. This is **not a complete backup of all personal files**, nor a
  disaster-proof off-site copy. ODS PostgreSQL stores need separate database dumps.
- Retention is currently non-destructive; monitor backup growth. The new metrics
  dashboard reports disk pressure. No unrelated user files were removed.

## Historical credential exposure / remaining limits

An old public Git archive still contains Servo/OpenClaw credentials. The archived
Telegram token returns 401. The archived Anthropic OAuth credential returns 403
(`OAuth authentication ... not allowed for this organization`), which does **not**
prove revocation. Revoke that old Claude authorization through the provider account
before considering the exposure resolved. Servo's old local gateway stays disabled.
History rewriting was not performed; it would require coordinating other checkouts.

Remaining legacy credential consumers are explicitly listed above. This rollout
has not added full SSO to every application, removed all Docker socket access from
existing admin tools, proven off-LAN router reachability from an independent host,
or produced an off-site backup of the media/footage library. Do not describe these
as completed. Cloudflare WAF/Access does not protect DNS-only private records;
local firewall, Tailscale identity policy, TLS and application authentication do.

## Verification

Run `make check-network` on the Mac and `make check-server` on the server, plus:

```sh
python3 scripts/check-household-https.py
python3 scripts/check-household-media-login.py
python3 scripts/check-download-logins.py
python3 scripts/check-monitoring.py
python3 scripts/sync-service-catalog.py
```

Checks distinguish login-page availability from actual authenticated access.
Docker image digests are pinned to deployed versions; schedule deliberate reviewed
updates rather than assuming restarts upgrade safely.

## Central sign-in follow-up

The shared [authentication platform](authentication.md) is live for all 35
registered HTTPS browser routes. Normal central sign-in replaces proxy Basic
dialogs, including NZBGet through a private upstream credential adapter. Native SSO adapters are separate
from gateway access and must be tested per application.

The historical Speedtest Tracker `APP_KEY` literal also remains a migration item:
rotate through the application-supported procedure and test encrypted data before
removing the literal. Merely moving that exposed value to a private file is not
credential rotation.

Latest backup attempt (September 16, during auth preparation) was safely deferred
because the Mac had less than 1.5 GiB free. The previously verified encrypted
snapshot remains available; no newer snapshot is claimed. Free space or select
a larger backup destination before relying on the expanded backup source list.

A smaller central-auth-only encrypted snapshot was subsequently saved and restored
successfully. It contains the new Authelia state/configuration and does not replace
the full configuration backup. See `scripts/backup-auth-to-mac.py`.
