# Household access on the existing Wi-Fi

Entry point: **https://home.egouda.xyz**. Service tiles use trusted HTTPS names
under `*.home.egouda.xyz`, for example `draw.home.egouda.xyz` and
`requests.home.egouda.xyz`. Existing `.lan` routes remain available.

## Network design

Cloudflare publishes two DNS-only A records: `home.egouda.xyz` and
`*.home.egouda.xyz`, both `10.0.0.182`. The domain's website, mail and other
records are unchanged. Traffic goes directly to Nginx Proxy Manager on the home
server; there is no Cloudflare Tunnel, public ingress or router port forwarding.
Public DNS contains the private address but does not make it internet-routable.
Away from home, an authorized Tailscale connection with the existing server route
is still needed.

The Mac's actual Wi-Fi DHCP lease advertises Rogers DNS servers
`64.59.135.148` and `64.59.128.114`; both returned the private address when queried
from the server. Cloudflare and Quad9 resolvers also returned it. The gateway's
own DNS proxy at `10.0.0.1` filters this answer, but that is not the DNS server
advertised in the observed DHCP leases. A phone on household Wi-Fi with VPNs off
successfully opened the HTTPS Homarr login page on 2026-09-15.

No DHCP, Wi-Fi, IPv6, client DNS or Tailscale configuration was changed. The
previous DHCP migration plan is unnecessary for this access goal. Pi-hole
remains staged at port 1053; household-wide ad blocking is a separate goal.
Guest Wi-Fi client isolation, a VPN blocking LAN access, or a resolver that
filters private-address answers can still prevent access; these are not solved
by public DNS records.

## HTTPS and application behavior

Let's Encrypt DNS-01 issued a certificate for `home.egouda.xyz` and
`*.home.egouda.xyz`; verification uses temporary Cloudflare TXT records and needs
no inbound ports. Initial certificate expiry: 2026-12-14.
See [Let's Encrypt DNS-01](https://letsencrypt.org/docs/challenge-types/#dns-01-challenge)
and [Cloudflare DNS records](https://developers.cloudflare.com/dns/manage-dns-records/how-to/create-dns-records/).

`scripts/configure-household-https.py` derives 33 HTTPS routes from the existing
NPM and repository-owned `.lan` configurations. It namespaces origin-check maps,
preserves each service's authentication, adds HTTP-to-HTTPS redirects, validates
Nginx before graceful reload, and updates Homarr links with a SQLite backup.
Nested ODS names flatten to a single label, e.g.
`n8n.ods.lan` → `n8n-ods.home.egouda.xyz`, matching the wildcard certificate.
The ODS external-links API and footage UI have their legacy links translated
only in HTTPS responses. Original app configuration and `.lan` responses remain
intact. Re-run the script when routes are added or changed. Other app-specific
callback/webhook base URLs may still need explicit migration if those features
are used.

New hostnames have separate browser sessions. Existing application credentials
still apply; this does not create single sign-on or remove app authentication.
Homarr's username is `egouda`. Its password initially differed from Creative
Drive/Draw; on 2026-09-15 it was aligned with that existing household password
after the owner reported login failure. A private SQLite backup was taken first,
and actual HTTPS credential login plus authenticated-session retrieval passed.

### Media credentials and family accounts

The owner also requested aligning Jellyfin's `egouda` password with the same
household credential. The direct Jellyfin API and Requests initially rejected
that password with HTTP 401; this was independent of HTTPS. The supported
Jellyfin password API updated the account, and Homarr's encrypted Jellyfin
integration password was updated alongside it. No service restart was needed.
Private SQLite backups are under
`~/.local/state/home-server-maintenance/jellyfin-password/`.

`python3 scripts/check-household-media-login.py` on the server verifies real
Jellyfin authentication and both Requests routes, checks the authenticated user,
and signs its test sessions out. All passed after the alignment. It reads the
private household secret without displaying it. Run
`scripts/align-jellyfin-password.py` only when the owner explicitly requests
another alignment, not as a routine health check.

To create a separate family account, run on the Mac in Terminal:

```sh
python3 scripts/create-media-user.py --username mgouda --display-name Mariam
```

The hidden prompt asks twice for a new password. The script sends it through
SSH stdin, creates a password-protected Jellyfin user, imports only that user
into Requests, and verifies login including the HTTPS route. Passwords are not
written to command arguments, files, logs or the chat. Requests uses Jellyfin
authentication; its friendly display name can differ from the `mgouda` login.
New accounts have normal media access, no administrative or media-deletion
rights, and standard request permission. They inherit the household's optional
auto-approval flag (enabled on 2026-09-15). Existing
accounts are not overwritten. A private result file on the Mac records only
account IDs and pass/fail status. A partial failure needs inspection before
retrying; the script refuses to recreate an existing Jellyfin account.

## Reproduce and maintain

On the Mac, `python3 scripts/configure-household-dns.py` reads the existing
literal Cloudflare token from `.zshrc`, preserves private snapshots, creates only
missing records, and refuses conflicting records. It never prints credentials.

On the server, the DNS credential is private at
`~/.config/home-server/secrets/cloudflare-dns.ini`, mode 600. Its format is
`dns_cloudflare_api_token = TOKEN`. The provided token could manage zone DNS but
could not list token permission groups to mint a narrower token. It is therefore
the existing token; it is mounted read-only only into the short-lived certificate
container. Prefer a zone-scoped DNS-edit token here when one is issued separately.

Initial certificate issuance:

```sh
docker run --rm \
  -v /mnt/server/npm/letsencrypt:/etc/letsencrypt \
  -v /home/egouda/.config/home-server/secrets/cloudflare-dns.ini:/run/secrets/cloudflare.ini:ro \
  certbot/dns-cloudflare@sha256:0dbdb8667052256f5ebdd8a56bbf24cf80b6045a9520fdfb5575c087011341ee \
  certonly --dns-cloudflare --dns-cloudflare-credentials /run/secrets/cloudflare.ini \
  --dns-cloudflare-propagation-seconds 30 --non-interactive --agree-tos \
  --register-unsafely-without-email --cert-name household \
  -d home.egouda.xyz -d '*.home.egouda.xyz'
python3 scripts/configure-household-https.py
cp templates/systemd/household-certificate.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now household-certificate.timer
```

`household-certificate.timer` checks renewal twice daily and reloads Nginx after
success. Keys/certificates live in the existing persistent NPM letsencrypt
directory. Check the timer/journal and monitor certificate expiry; this ACME
account was registered without an email address.

Validation:

On 2026-09-15, all 33 HTTPS routes passed trusted-certificate/reachability checks;
the whiteboard passed authenticated board retrieval, secure WebSocket upgrade
and cross-origin write rejection. ODS/footage navigation responses contained no
legacy `.lan` links. Certificate renewal dry-run completed successfully and the
renewal timer is active. Both required infrastructure health commands passed
with zero failures. App reachability does not test every service workflow.

```sh
python3 scripts/check-household-https.py             # server
sh scripts/renew-household-certificate.sh --dry-run  # server
make check-server                                 # server
make check-network                                # Mac
```

## Rollback

Private snapshots are under `~/.local/state/home-server-maintenance/household-https/`
on the server, and `~/.local/state/home-server-maintenance/cloudflare/` on the Mac.

1. Restore only Homarr app href values from the first pre-migration snapshot,
   matching app IDs, in a transaction. Do not overwrite newer boards/accounts
   by restoring the entire database.
2. Move `household-https.conf` outside Nginx's include directory, validate with
   `docker exec npm nginx -t`, then gracefully reload. Existing `.lan` routes
   remain present.
3. Delete only the two DNS record IDs recorded in the private creation snapshot,
   after verifying their names and private address still match this deployment.
   Do not alter apex, email, other subdomains or unrelated challenge records.
4. Disable `household-certificate.timer` if retiring the HTTPS setup. Preserve
   keys and backups privately until the rollback is verified.

No router rollback is needed: its settings were not changed.
