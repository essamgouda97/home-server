# Tracker registration status

Verified 2026-09-20 through Chrome. Search-only setup; no media downloaded.

| Tracker | Registration | Prowlarr |
| --- | --- | --- |
| ArabTorrents (`arab-torrents.net`) | Blocked: submitting without an invitation returns “The invite code you specified is invalid!” | Not added; no account exists yet |
| ArabScene (`arabscene.me`) | Same invitation requirement | Not added; no account exists yet |
| RuTracker | Browser security policy denied access; do not bypass through alternate tools or domains | Not added |

The owner authorized these registrations. Distinct proposed logins and random
recovery answers are saved and read-verified in the authorized 1Password vault as
`Home Server — arabtorrents` and `Home Server — arabscene`. These are **pending
registration**, not working accounts. Non-secret references are in
`config/1password/`; no passwords or personal signup details belong here.

Next step: obtain legitimate invitation codes, finish registration, confirm any
verification email, then test actual login and Prowlarr search before enabling an
indexer. Do not purchase membership without explicit authorization. Preserve
existing tracker settings; do not bypass ArabP2P's separate account-point limit.

No deployment or architecture change was made in this registration attempt.

## ArabP2P account-session repair — September 20, 2026

After the owner updated the indexer credentials, fresh direct login used the new
account successfully, but Prowlarr's persisted tracker cookies still authenticated
as a different account. Search worked while Prowlarr's torrent-metadata endpoint
returned HTTP 500 / invalid torrent. Saving credentials had not replaced that
existing authenticated session.

Repair: stop only Prowlarr, take a consistent SQLite backup outside Git, verify
indexer ID 3 is ArabP2P, clear only its `IndexerStatus.Cookies` and
`CookiesExpirationDate`, check SQLite integrity and start Prowlarr. Backup location:
`~/.local/state/home-server-maintenance/arabp2p-session/` on the server. Do not
delete/recreate indexers or change Radarr mappings to refresh a session. Never
print persisted cookies, passwords or metadata URLs.

Verified afterward: Prowlarr's persisted session identifies the new account;
Arabic search returned 18 results; the previously failing metadata endpoint
returned HTTP 200 and structurally valid bencoded torrent metadata. Metadata was
discarded, never submitted to a client. Radarr's ArabP2P connection test passed
and its `DisabledTill` backoff cleared. Existing torrents were not changed.
Network checks passed; the full server check still flags the separately unhealthy
VPN gateway. No full media download was tested.

## Unlimited ArabP2P seeding — September 20, 2026

The owner requested unlimited contribution for ArabP2P. Both matching current
jobs now have ratio, seeding-time and inactive-seeding-time limits set to `-1`
(unlimited). Other trackers retain the global 2.0 ratio/stop policy. Completed
jobs remain retained by Radarr and Sonarr.

`scripts/apply-arabp2p-seeding.py --apply` matches only `arabp2p.net` and its
subdomains in qBittorrent tracker metadata, saves previous limits privately, and
read-verifies the changes. Without `--apply` it audits only. qBittorrent 5.2
requires `shareLimitAction` along with all three limits. The script does not
resume, add, remove or read media files. New jobs receive the exception on the
next timer tick (30 seconds plus scheduling/API latency).

Install/reproduce on the server:

```sh
python3 scripts/apply-arabp2p-seeding.py --apply
install -m 644 templates/systemd/home-arabp2p-seeding.service templates/systemd/home-arabp2p-seeding.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now home-arabp2p-seeding.timer
python3 scripts/apply-arabp2p-seeding.py
```

To roll back, disable the timer first and restore per-job limits from the private
records under `~/.local/state/home-server-maintenance/arabp2p-seeding/`.
Regular `configure-seeding-policy.py` still configures the global default; the
tracker-specific exception is maintained separately by this timer.

Attribution check: both ArabP2P jobs' full announce URLs match fresh metadata
obtained while authenticated as the owner's new account. URLs/passkeys were
compared locally and never printed. This verifies intended account attribution,
not tracker-side credited upload. At verification, both tracker requests reported
DNS failure, the VPN gateway could not resolve its own CyberGhost endpoint, and
no upload was occurring. Seeder availability cannot be inferred from this failure.
Unlimited seeding does not guarantee upload credit or prevent an account ban.

Both policy audits and Mac network checks pass. Server health still fails on the
VPN gateway. The [editable Draw companion board](https://draw.home.egouda.xyz/?board=muaj85ardrdsipsi5l)
records deployed policy and this unresolved boundary; all 8 elements were verified
persisted. Existing boards were preserved.
