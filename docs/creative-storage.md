# Creative Drive

The owner selected a web file manager plus a Finder drive for DJI footage and
DaVinci Resolve editing. Both services use the same ordinary SSD filesystem;
there is no application database holding the originals.

| Access | Address |
|---|---|
| Web UI (phone, tablet, laptop) | http://files.lan |
| Web UI fallback | http://10.0.0.182:8082 |
| Finder: Go → Connect to Server (⌘K) | smb://egouda@home-server.lan/Creative |
| Finder IP fallback | smb://egouda@10.0.0.182/Creative |

Use Tailscale with the same account outside home. Tailscale's existing `/32`
route and split DNS cover these addresses. The username is `egouda`; use the
generated password saved in the Mac's login Keychain under `files.lan` and
`home-server.lan`. Open Keychain Access and search for either name to retrieve
it after authenticating to macOS. New devices need that password too.
Web sessions require login; anonymous signup, file sharing and command execution
are disabled initially. SMB requires authenticated SMB3 with encryption.
Service ports bind only to the server's private LAN IP. Do not forward them on
the router or enable Tailscale Funnel for them.

## Layout and editing

The share maps directly to `/srv/mergerfs/ssd/creative`, outside the combined
media folders. It contains `Projects`, `Assets`, `Exports`, `ProjectBackups`, and
`Incoming`. `server.conf` owns the path. The SSD must be mounted before service
startup; Docker is configured not to silently create a missing share directory.

For a shoot, use a unique project and card name:

```sh
python3 scripts/ingest-footage.py /Volumes/DJI/DCIM 2026-09-14-river pocket-card-01
```

This creates `Projects/2026-09-14-river/Originals/pocket-card-01`, preserves the
source tree, checks SHA-256 after copying, and writes a verification manifest.
The Mac needs its existing `ssh home-server` connection as well as SMB: a tiny
server-side operation atomically publishes each verified file without replacing
an existing original. macOS SMB does not support exclusive rename or hard links.
An identical re-run skips identical originals. A conflicting filename aborts;
it never overwrites different footage or erases the source. Use another card
name for a new card to avoid camera filename collisions. Finder drag-and-drop
and web uploads are also available, but do not provide this verified-ingest
manifest. Large uploads are streamed through the reverse proxy without a small
request-size limit. Browser previews depend on the browser's codec support;
DJI H.265 footage may need downloading even when upload succeeds.

Keep the existing Resolve project library on the Mac. Setup does not relocate
or rewrite existing projects. Import originals from `/Volumes/Creative/Projects`.
For each new project, set its proxy location under `~/Movies/Creative/Proxies`
and cache location under `~/Movies/Creative/Cache` in Resolve, then generate
proxy media. Use local proxies while travelling or if Wi-Fi scrubbing is slow;
reconnect to originals for full-quality delivery. Resolve renders on the Mac.
Mounted SMB folders require an active connection; they do not automatically
sync originals for offline use. Keep an active project's proxies locally.

The server Ethernet link is 1 Gbps. This is a theoretical 125 MB/s before
overhead, not a measured disk or Wi-Fi benchmark. The SSD shared space is also
used by existing applications. Monitor free space with `make check-server`.
On 2026-09-14, a 64 MiB synthetic transfer from this Mac through the Tailscale
route measured about 20 MiB/s writing over encrypted SMB and 37 MiB/s downloading
through the authenticated web UI, with matching SHA-256. This is one network
sample, not a Resolve playback benchmark. Use local proxies for demanding edits.

## Resolve backups

```sh
python3 scripts/backup-resolve.py
python3 scripts/install-mac-creative-backup.py
python3 scripts/backup-resolve.py --verify /path/to/resolve-library-TIMESTAMP.tar.gz
```

The backup tool uses SQLite's online backup API for each project database,
archives the project library, and extracts/checks the snapshot before reporting
success. It does not modify the live databases. The daily per-user launch agent
runs at 19:00 local time; macOS can defer it while the Mac sleeps. Logs are under
`~/Library/Logs/home-server`. Moving this checkout requires reinstalling the job.
It keeps 14 snapshots under `~/Movies/Creative/ProjectBackups` and copies pending
snapshots to `Creative/ProjectBackups/MacBookAir` whenever the share is mounted,
keeping the latest 30 there. Only this tool's `resolve-library-*.tar.gz` archives
are pruned. If disconnected, backups remain local until a connected run.

To restore, first verify the archive, close Resolve, and extract it to a NEW
folder. Connect that recovered project library through Resolve's Project Manager.
Preserve the live library until the restored projects have been checked. These
archives contain project metadata, not footage, fonts, LUTs or plugins. Export
important projects as `.drp` files into the project backup folder as well.

## Installation and recovery

On the server, from this checkout:

```sh
bash scripts/prepare-creative.sh
```

On the Mac, provision the password and local editing directories:

```sh
python3 scripts/setup-mac-creative.py --generate
```

On the server:

```sh
make creative-start
make home-proxies
python3 scripts/configure-homeassistant.py
make home-config-check
make check-server
```

On the Mac: `make creative-mount`, `make check-creative`, then `make check-network`.
Install the daily Resolve backup with `python3 scripts/install-mac-creative-backup.py`
and run `make creative-backup-mac` once. Store credentials
in a password manager for access from additional devices. File Browser's
database is at `${SERVER_DATA_DIR}/filebrowser`; Samba state is at
`${SERVER_DATA_DIR}/samba`; the private password file is under
`${HOME_SERVER_SECRETS_DIR}`. All are outside Git. The NPM reconciliation script
owns only its custom include and two routes, validates nginx, and rolls its file
changes back on validation failure. Existing NPM-managed routes are preserved.

After editing a configuration that is mounted as an individual file, recreate
the affected container (`docker compose --env-file server.conf --env-file .env
up -d --force-recreate SERVICE`) so it sees the new file inode. HA network settings
are reconciled separately through its API; see the smart-home guide.

Run `make backup-home-services` on the server for a consistent private snapshot
of Home Assistant, File Browser and runtime secrets. It briefly stops those two
services and restarts them afterward. Archives live under
`~/.local/state/home-server-backups` with private permissions. Samba credentials
are regenerated from the password secret. This app-state backup is manual;
the Resolve project backup is daily. Copy app-state archives to independent
storage, and restore the matching Git revision alongside them.

To stop the new services, use Compose `stop samba filebrowser homeassistant`.
Do not use `down -v` or delete state. To migrate, copy the footage, private
application state and secret files, keep UID/GID 1000 consistent, and restore
the same paths before starting the versioned Compose services.

## Backup boundary

There is no independent off-server footage backup configured. The media pool
is not mirrored. Keep SD cards or another disk copy until a second verified copy
exists. The HDD has too little free capacity to mirror the available creative
SSD space, so setup does not pretend it protects all future footage. A future
USB/off-site backup target should use versioned backups and a tested restore.
