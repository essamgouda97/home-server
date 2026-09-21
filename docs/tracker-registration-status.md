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
