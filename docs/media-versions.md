# Multiple movie qualities with retained seeding

Deployed and verified September 20, 2026.

The owner's two selected downloads were Radarr movie jobs, not duplicate Sonarr
episodes. Both completed. Radarr imported the 4K release; the 1080p release is now
also published in Jellyfin. Owner and `mgouda` library views each show one movie
with two sources, 4K first and 1080p available as an alternative. Moonfin consumes
that Jellyfin library. Client playback settings and bandwidth can still affect
which version/transcode a device chooses; actual TV playback was not tested.

## Ownership and storage

- qBittorrent retains both original seed paths and tracker metadata. No torrent
  was added, removed, restarted or renamed by this maintenance.
- Radarr manages its preferred imported file. It is not a multi-version library
  manager; Jellyfin owns the grouping of alternate versions.
- The second library entry is a hardlink to the completed torrent source, with
  no copy fallback. Both versions' physical device/inode identity was verified on
  the mergerfs branches. Distinct qualities occupy distinct files, but library and
  seeding do not duplicate each quality's bytes.
- Jellyfin's supported merge-versions API groups the existing Radarr filename and
  the added alternate. This avoids renaming the Radarr-managed file. The primary
  source is 3840 pixels wide; the alternate is 1920 pixels wide.
- Both ArabP2P jobs retain unlimited ratio/time/inactivity limits, enforced by the
  existing seeding timer. Other tracker jobs retain the global 2.0 policy.

The selected movie uses `Home 1080p + 4K (prefer 4K)`: WEB and Blu-ray 1080p/2160p
are allowed, 4K ranks higher, and the upgrade cutoff is WEB 2160p. No automatic
search/grab was submitted. Other movie profiles and Seerr defaults are unchanged.
This provides a reusable profile without retroactively upgrading the whole library.

## Reproduce or repair a selected movie

Run on the server after Radarr has imported its preferred release:

```sh
python3 scripts/sync-movie-versions.py --movie-id <radarr-id>
python3 scripts/sync-movie-versions.py --movie-id <radarr-id> --apply --prefer-4k
```

The first command audits only. The second creates absent hardlinks, optionally
assigns the quality profile, refreshes Jellyfin, merges the versions, and checks
both owner and family library views. It matches qBittorrent hashes against that
movie's Radarr history, requires completed single-video releases, and refuses
ambiguous resolutions, name collisions, unknown mounts and cross-device copies.
It keeps paths/hashes out of logs and stores rollback metadata outside Git under
`~/.local/state/home-server-maintenance/movie-versions/`.

This is an explicit maintenance command, not a global polling service. Re-run it
after a later replacement/import if that movie needs its alternate version restored
or regrouped. Do not point broad Radarr import/cleanup tools at alternate versions
or delete seed sources to clean up apparent duplicate library names.

Jellyfin's unscoped administrator `/Items` endpoint includes hidden alternate
records. Verify the actual `/Users/{id}/Items` library view instead; an admin count
of two records does not mean users see two movies. Repeated application was tested,
and grouping was checked after a library refresh. Native owner login, Moonfin
English/Arabic catalog search, final HTTPS download-app logins, seeding policy,
host VPN checks and full server health passed. A first Mac UDP DNS probe timed out;
the immediate full network-check repeat passed.

## Architecture and recovery

The additive [editable Draw board](https://draw.home.egouda.xyz/?board=muakbw8mye85kmimbb)
contains 11 API-verified persisted elements. It documents deployed ownership,
hardlinks, quality preference, identity boundaries and maintenance limits without
private media metadata.

Recovery can restore the prior Radarr profile from the private snapshot and split
Jellyfin alternate sources through its supported API. Do not remove any torrent
or source file. Any library-link cleanup must first verify its inode against the
saved source and confirm which file Radarr currently owns.

See [single-copy imports](media-hardlinks.md), [ArabP2P seeding](arabic-seeding.md),
[host VPN](host-vpn.md), and [Jellyfin version documentation](https://jellyfin.org/docs/general/server/media/movies/#multiple-versions).
