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
