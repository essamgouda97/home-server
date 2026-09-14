# Creative storage and smart home setup

Requested 2026-09-14. This extends the active creative-storage goal with Home
Assistant and a configuration-first structure suitable for a later NixOS migration.

## Completion criteria

- SSD-backed Creative folder shared by File Browser and Samba, managed in the
  existing Docker Compose project, with authenticated access and no public ports.
- Finder access verified by writing and reading a file over SMB. Web upload and
  download verified against the same directory. Access works through Tailscale.
- A repeatable footage-ingest workflow verifies copied files and never erases a
  source card. Active proxies/cache stay local on the Mac.
- A repeatable Resolve project-backup workflow preserves local project libraries
  and stores recoverable snapshots on the server; existing edits are preserved.
- Home Assistant starts automatically, passes configuration checks, and is ready
  for device onboarding. Device pairing requires the actual devices/radios.
- Service definitions, non-secret config, setup/check/backup scripts, and recovery
  instructions are versioned in this public repo. Credentials and mutable app
  databases are stored outside Git.
- Existing media/network checks remain healthy. Changes are pushed and both
  checkouts are synchronized.

## Architecture decisions

- File Browser plus Samba was selected by the owner over Nextcloud. Both use
  ordinary filesystem directories, avoiding a separate application-owned media
  store or mandatory sync of large originals to the Mac.
- Home Assistant Container uses host networking for local device discovery.
  Its UI-managed integration state remains private; YAML packages and examples
  live in Git. Additional protocol services are added when hardware requires them.
- Ubuntu host preparation is separate from OCI service declarations. A future
  NixOS configuration can provide the same mounts, UID/GID, secret files and
  containers without moving application data into the Nix store.
- The server is not a second independent backup of footage unless another copy
  also exists. No spare off-server backup destination has been provided.

## Deployment verification (2026-09-14)

- Creative Drive and Home Assistant web login verified in the browser.
- Finder mounted at `/Volumes/Creative`; SMB 3.1.1 with AES-128-GCM encryption
  and encryption required confirmed by macOS and Samba.
- Web upload → SMB read and SMB write → authenticated web download matched;
  unauthenticated file access was rejected.
- Real SMB footage-ingest regression checks passed, including duplicate imports,
  conflicting filenames, exclusive publication and source-symlink rejection.
  macOS SMB does not support atomic hard links/exclusive rename, so the last
  publish operation runs over SSH on the native server filesystem.
- Resolve project snapshot extracted successfully and all 18 SQLite databases
  passed integrity checks. Verified archives copied to server. Daily Mac backup
  LaunchAgent installed for 19:00 local time.
- Home Assistant configuration and its confirmed HTTP settings passed; the
  repeat reconciliation preserved users and did not request another restart.
- The three new services restarted successfully with `unless-stopped` policy.
  Existing `make check-network` and `make check-server` reported zero failures
  across 21 containers. This addition was tested with container recreation and
  restart, not another full host reboot.
- A private app-state backup exists outside Git. Backups contain credentials;
  scripts test a disposable restore of the HA SQLite and File Browser databases.

## Physical and personal setup still required

- Set the actual Home zone privately and enroll the phone companion app for
  location, push notifications and push-to-talk controls.
- Attach a Zigbee coordinator, pair the THIRDREALITY sensor, instantiate the
  supplied leak-alert blueprint and test it with the phone.
- Trial two ESPresense receivers and a carried beacon, then configure MQTT,
  rooms and calibration. Room identity tracking is not running yet.
- Configure a speech pipeline if spoken Assist is desired; no speech engines
  or always-listening microphones were installed.
- Add an independent footage/app-state backup destination. The server's SSD
  alone is not a second independent copy of footage.
