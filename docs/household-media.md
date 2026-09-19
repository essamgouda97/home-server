# Household media requests and management

## Daily use

- Requests: https://requests.home.egouda.xyz
- Watch: https://jellyfin.home.egouda.xyz
- Downloads: https://torrents.home.egouda.xyz
- Movies: https://radarr.home.egouda.xyz
- Shows: https://sonarr.home.egouda.xyz

The owner login for all five is `egouda` with the private household password.
Mariam uses her own `mgouda` Jellyfin login in Requests and Jellyfin, with her
own password. Her Requests display name is Mariam. She has no access to the
owner's download-management credentials or administrator permissions.

On 2026-09-15 the owner selected automatic processing rather than manual
approval. Mariam and newly provisioned standard users have Request + Auto
Approve (permission mask 160). They do not have 4K, advanced-request, or admin
permissions. The owner can still review requests from the Requests page on a
phone. Restoring manual approval means removing only the Auto Approve permission
(128) from the relevant user and/or new-user default; pending requests can then
be approved in that queue. No external bot is needed.

## Quality and progress

New movies, shows, and anime requests use **Home 1080p (WEB / Blu-ray)** in
Radarr/Sonarr. Only WEBDL-1080p, WEBRip-1080p and Bluray-1080p are allowed.
CAM, screeners, SD/720p, remux, discs and 4K are excluded. Automatic upgrades
are disabled, avoiding repeat downloads merely to improve an acceptable file.
Existing library items retain their current profile assignments.

Size definitions for these three qualities are 10 MiB/min minimum,
40 MiB/min preferred, and 80 MiB/min maximum. For a two-hour film that is
approximately 4.7 GiB preferred and 9.4 GiB maximum; for a 45-minute episode,
1.8 GiB preferred and 3.5 GiB maximum. These are runtime-scaled release limits,
not guaranteed final sizes. **Quality definitions are global** in each app and
also affect future grabs for existing items using these qualities.

The single Radarr and Sonarr instances are now correctly configured as normal
default servers, not separate 4K servers. Automatic search and status sync are
enabled. The existing download-sync job runs every minute. Requests can show
download progress when the download client has an active item; a completed
download still needs importing and Jellyfin's library scan before it is watchable.
No percentage or reliable ETA exists while waiting for a release or a matching
source. An empty download queue does not by itself indicate a broken service.

Mariam's request 36 was released after these settings were applied. Radarr
accepted it as movie 145, with the new profile and monitoring enabled. At the
verification time it was `inCinemas`, `isAvailable=false`, and had no file or
download-queue item. The released-only availability rule was preserved. This
verifies request delivery and monitoring, not a completed download.

## Phone notifications

Web Push is enabled globally; VAPID keys already exist. Each user must opt in:

1. Open Requests over HTTPS while on household Wi-Fi.
2. On a phone, add it to the Home Screen and open that installed shortcut.
3. Sign in; open Profile → Edit Settings → Notifications → Web Push.
4. Enable push, allow the device permission prompt, and choose desired events
   such as media becoming available.

No notification was sent as a test and no device permission was granted on a
user's behalf. The link in a notification still needs household Wi-Fi or the
existing authorized Tailscale route when opened away from home.
See [Seerr Web Push](https://docs.seerr.dev/using-seerr/notifications/webpush/).

## Deploy and verify

Run on the server:

```sh
python3 scripts/align-download-credentials.py
python3 scripts/check-download-logins.py --local
python3 scripts/configure-household-requests.py
python3 scripts/check-household-requests.py
python3 scripts/configure-household-https.py
python3 scripts/check-download-logins.py
python3 scripts/check-household-https.py
make check-server
```

Run `make check-network` from the Mac after changes. The HTTPS deployment script
now refuses to proceed unless the direct qBittorrent/Sonarr/Radarr shared-password
logins pass. The final HTTPS login checker uses actual credentials and session
cookies, not API-key bypasses. Sonarr/Radarr APIs separately require API keys;
their owner login check verifies the protected UI session. Sonarr/Radarr use
forms login with authentication required, including local addresses.

The alignment script also updates both apps' saved qBittorrent credentials and
runs their download-client connection tests. API keys remain unchanged, so
Requests, Homarr and other integrations continue working. The VPN container,
torrents, seeding policy, and existing files were not restarted or modified.

Completed torrent retention, ratio policy, title-free auditing and the VPN
port-forwarding limitation are documented in [Arabic torrent seeding](arabic-seeding.md).

Private backups are under `~/.local/state/home-server-maintenance/`:

- `download-credentials/`: qBittorrent config, Sonarr/Radarr databases and configs.
- `household-requests/`: Requests settings/database/user permissions, original
  quality profiles and global size definitions.

Restore selected settings through their APIs. For credential rollback, restore
qBittorrent and both download clients together. Preserve any newer requests or
watch history instead of restoring whole databases over live services. If a
database restore is necessary, stop only its service and preserve current state
first. Do not put backups or credentials in Git.
