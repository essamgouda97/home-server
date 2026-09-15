# Life Dashboard

The application stays in the **private** `essamgouda97/life-dashboard` repository.
This public infrastructure repository contains only deployment configuration and
operating instructions. Never copy its private config, source documents, database,
Google credentials, or Codex auth into this repository or a public image registry.

## Use

- Dashboard: **http://life.lan**, locally or through the existing Tailscale route.
- Login: `egouda`, using the existing home-services / `files.lan` password.
- Web uploads: **http://files.lan/files/LifeDashboard/docs/**.
- Finder: **smb://home-server.lan/LifeDashboard**, then open **docs**.
- On this Mac: `make life-mount`; files appear in `/Volumes/LifeDashboard/docs`.
- The Mac app checkout's ignored `server-docs` link points to that Finder folder.

Upload into the existing institution/domain folder. The Documents page shows
import status and parser warnings. The worker checks content hashes every 20
seconds, waits for 60 seconds without changes, verifies a private source snapshot,
then calls the app's deterministic importer. It has no network access. A completed
upload is not necessarily a successfully parsed document: unknown formats remain
explicit, and `_inbox` is excluded from parsing until classified. Avoid editing or
deleting originals that are still needed as historical evidence. The importer does
not automatically retract historical facts when a source disappears.

## Layout

`server.conf` defines:

- `LIFE_DASHBOARD_REPO`: `/home/egouda/workspace/personal-finances`, an SSH clone
  of the private application repository. Compose builds its Dockerfile directly.
- `LIFE_DASHBOARD_DATA`: `/srv/mergerfs/ssd/life-dashboard`, the persistent SSD root.
  `docs`, `data`, `generated`, `codex`, and `bridge` live here.
- Google Health credentials: `${HOME_SERVER_SECRETS_DIR}/life-dashboard-health`.

Inside the application containers, these bind mounts populate the app's original
`docs/`, `data/`, and generated-public-assets paths. The runtime database lives on
local SSD, never over SMB. The app's `config/` is mounted from its private checkout
because existing app actions also update config files. Preserve/commit those
changes before pulling a new app revision.

The Next.js service has only a loopback host port, `127.0.0.1:3030`; clients use the
authenticated Nginx route. Nginx rejects cross-origin writes. No public ingress or
router port forwarding is configured. HTTP LAN access is intended for the private
network; Tailscale encrypts remote access. The app's existing personal-screen lock
is a privacy UI and is not a substitute for the reverse proxy's authentication.

## Deploy and update

```sh
# On the server, after restoring/migrating the private docs and SQLite database:
make life-start
python3 scripts/install-life-backup.py

# On the Mac, after the server becomes authoritative:
python3 scripts/install-life-mac.py
make life-mount
```

`prepare-life-dashboard.sh` verifies the SSD mount and clones the private app via
the operator's SSH identity when needed. Git credentials are not passed into Docker.
The application Dockerfile excludes docs/data/secrets and builds against an empty
schema. Application images contain private application config and remain local.

To update, commit/push application code from its private repository, preserve any
server-side config edits, fast-forward its server checkout, then run `make life-start`.
Run `make check-network` from the Mac, `make check-server` on the server, and
`python3 scripts/check-life-dashboard.py` from the Mac afterward.

For a manual document refresh on the server, use the container, not a host checkout
with a separate database:

```sh
docker exec life-dashboard python3 /app/personal-finances/scripts/sync_docs.py
```

Stop `life-dashboard-sync` around an intentional manual sync to avoid concurrent
imports, then start it again. App reads/writes use the same server database.

## Mac companions

The server performs scheduled Google Health imports and imports relayed Fitbit
minute history. Existing macOS Bluetooth capture/watchdog remain on the Mac.
`install-life-mac.py` disables the two old local history-import LaunchAgents and
installs an SSH snapshot relay plus a Resolve companion. Their plist backups are
under `~/.local/state/life-dashboard-migration/launchagents`.

The Resolve companion exposes only the existing bridge commands over a mode-0600
SSH-forwarded Unix socket. No inbound Mac SSH service or LAN listener is required.
The web app handles storage on the server and delegates Resolve inspection,
planning timelines, marker pushes and explicit Finder reveal to the Mac. The Mac
must be awake and connected; direct editing still requires a running Resolve and
the edition/scripting capabilities reported by the original bridge. OTIO planning
package export works on the server even when Resolve is closed.

Google Health may require renewed user consent when its existing refresh token
expires. Use the application's documented OAuth helper, keep callbacks and tokens
private, and write the renewed token into its server secret directory. Never place
tokens into an environment file or Git. Codex canvas uses the existing ChatGPT
subscription; it receives the requested canvas context with shell/apps/browser
tools disabled. Financial documents continue to use deterministic local parsing.

## Backups and rollback

`make life-backup` stops only the three Life Dashboard containers, makes an online
SQLite snapshot that includes committed WAL contents, archives docs/data/config/
generated assets and private credentials, and always restarts the previously
running containers. The user timer runs daily at 04:15 and retains seven archives
under `${LIFE_DASHBOARD_DATA}/backups`. Automatic document imports keep seven
separate pre-import snapshots under `data/backups/automatic`; pre-migration backups
are preserved. Logs/status report counts and error categories, not document text.

These backups are on the same SSD and do not protect against drive loss. Copy
archives to an independent destination for that protection. To restore, stop the
three services, extract into a new private staging directory, validate SQLite with
`PRAGMA quick_check`, preserve the current state, then restore data and matching
private app/config revisions. `health-secrets` restores to the secret directory.
Do not overwrite a live SQLite database or run `docker compose down -v`.

The original Mac docs/database remain preserved. They are no longer the live
dashboard. Rollback requires disabling the companions, restoring the original
LaunchAgents, and deliberately choosing which server edits to bring back first.
