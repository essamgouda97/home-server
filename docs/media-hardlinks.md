# Single-copy media imports

September 20 update: [multiple movie qualities](media-versions.md) now documents
the selected dual-version library setup. ArabP2P jobs have unlimited seeding;
other jobs retain the 2.0 default. The owner later authorized local filename
matching and hashing, with private names/content excluded from logs and chat.

Deployed September 19, 2026. Radarr and Sonarr now mount the whole
`/mnt/server/media` directory at `/data`. Their legacy `/downloads`, `/movies`
and `/tv` paths are symlinks within the container to directories beneath that
single mount. The root-owned, read-only startup hook is installed from
`config/media-path-init/10-paths.sh`.

The download directory was renamed to `/mnt/server/media/downloads` without
enumerating or opening its contents. `/mnt/server/downloads` is a compatibility
symlink, preserving existing qBittorrent, NZBGet and Drive paths. Jellyfin's
library mounts and all existing movie/show records retain their paths.

Before this change, synthetic hardlinks failed with EXDEV in both importers.
Afterward, `python3 scripts/check-media-hardlinks.py` proves the two names refer
to one inode on one physical mergerfs branch, with link count two. It also proves
removing the synthetic download entry leaves its library entry intact. The check
creates and removes only its own disposable files. mergerfs can briefly cache an
old link count, so physical-branch metadata is used for these probes.

`copyUsingHardlinks` is enabled in both importers. New successful hardlink imports
use one physical copy with two directory entries. Existing duplicate copies are
not deduplicated, and existing media/torrent metadata was not inspected. Native
applications may still fall back to copying if permissions or storage layout
later prevent linking; rerun this probe after storage changes.

qBittorrent's global ratio limit is enabled at 2.0, with pause action and no time
or inactivity cutoff. Radarr/Sonarr retain completed jobs, preserving the seed
source and metadata. Tracker-specific requirements and per-torrent overrides must
still be respected. This setup cannot fabricate upload credit or guarantee peer
demand. The CyberGhost inbound-port limitation remains.

Configuration backups live under the private maintenance `media-hardlinks` folder.
The migration helper stops download consumers for the directory rename and retains
rollback configuration. Do not rerun an older checkout with separate mounts: this
would reintroduce copy imports. Do not delete either directory tree as a cleanup.

## Arabic search

The shared Radarr Home 1080p profile uses Original Language, allowing Arabic films
in Arabic and English films in English. ArabP2P is enabled for automatic and
interactive searches. `scripts/configure-arabic-indexer.py` sets a 2.0 seed target
in both Prowlarr and Radarr and removes the year from ArabP2P search queries.
It preserves credentials, categories and configured seed-time requirements.

For the owner's supplied example, searches returned zero ArabP2P releases with the
year, and seven without it. Radarr still rejected those results for title parsing
or movie mismatch. They were not grabbed. Do not disable matching or falsify
release metadata to make them pass. Seerr catalog searches already returned the
correct movie in both English and Arabic. Finding a catalog movie and finding a
parseable tracker release are separate steps.

This does not reconnect old files to missing torrent metadata. The owner has
explicitly prohibited inspection of private media; preserve that boundary.
