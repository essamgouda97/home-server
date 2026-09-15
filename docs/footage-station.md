# Raspberry Pi footage import station

The owner selected a Raspberry Pi **3 Model B**, an approximately 64 GB boot
microSD card and Ethernet for first boot. The Pi reads camera cards and transfers
originals to the existing server. Thumbnail generation, transcription, proxies,
classification and Codex edit preparation belong on the server; Resolve finishing
and local proxy playback belong on the Mac.

## Goal and delivery stages

1. Prepare and read-back-verify the boot card with a pinned Raspberry Pi OS Lite
   image, Ethernet DHCP, SSH public keys and repeatable first-boot configuration.
2. After the owner inserts the card and powers the Pi, verify real hardware boot,
   storage expansion, networking, SSH and base package installation.
3. Commission the camera-card importer: read-only source mounting, automatic
   Inbox imports, server-side project assignment, progress, retries, checksums, conflict refusal,
   manifests and safe card removal. Test unplug/retry and reboot recovery using
   synthetic footage before importing valuable originals.
4. Connect verified import manifests to the future server shot catalog, browser
   previews, transcription, proxy delivery and versioned OTIO rough cuts for
   DaVinci Resolve. This is planned follow-on work, not installed by this image.

**Current boundary:** the boot card is provisioned and the owner has connected
it to Pi power and Ethernet. The server console is live at ingest.lan. The automatic
Pi daemon, restricted transfer receiver, server console and Codex metadata review
queue are implemented in this repository. Physical Pi boot, read-only camera
mounting, unplug/retry and reboot acceptance checks are still required. No camera
card is mounted or imported by the base OS image alone; commissioning installs
and enables the application. [Clustering and editing plan](footage-clustering.md)
records the later scene-oriented, cross-camera catalog and Resolve handoff.

Prepared on 2026-09-14 (Edmonton): the 63,864,569,856-byte USB card passed
full-image SHA-256 read-back and persisted boot-configuration verification.
The writable Ubuntu installer data was archived and compared successfully under
`~/.local/state/home-server-maintenance/footage-station/20260915T035100Z` on
home-server. `prepared.json` records the checks; physical Pi boot is still pending.
Five preparation regression tests and both existing server/network health checks
passed. An initial partition-listing bug was corrected before final preparation;
the untouched writable data was recovered and verified, and the original partition
table is retained with that backup. Missing partition trees now fail closed.

Server acceptance on 2026-09-14: all 21 transfer/mount-selection/workflow tests
passed on both Mac and Ubuntu. The browser assignment flow worked at desktop and
390px phone widths with no horizontal overflow or JavaScript errors. NPM rejected
unauthenticated reads and cross-origin changes; authenticated tracking and worker
heartbeat checks passed. A synthetic original reached the real Creative root,
matched its SHA-256 manifest, and automatically produced a successful Codex review
using the subscription login. Test media was removed after private evidence was
archived under `~/.local/state/home-server-maintenance/footage-console/`.
`make check-network` and `make check-server` passed, including all 29 containers.
The Pi has not yet appeared through mDNS or the LAN SSH check; hardware acceptance
remains pending. These results do not claim visual clustering or real camera-card
mount/reboot testing.

## Hardware and first boot

- Put the prepared microSD in the Pi's **built-in microSD slot**, not a USB reader.
- Connect Ethernet to the same router/network as home-server.
- Connect a suitable Pi 3 micro-USB power supply. No screen or keyboard is required.
- Allow several minutes for first boot and package installation. Keep power on.
- The hostname is `footage-pi`; try `ssh egouda@footage-pi.local` from the Mac.
  If mDNS is unavailable, find `footage-pi` in the router DHCP clients and use its IP.
- After boot, the USB reader can be attached to the Pi for **separate camera
  cards**. The prepared 64 GB card remains its operating-system disk.

The 3 B is a modest ingestion device; do not promise fast bulk transfers or
video transcoding. The next stage will measure its actual transfer speed.
An unplugged/disconnected import must remain pending rather than being reported
as complete. This station is an import endpoint, not an independent footage backup.

```sh
python3 scripts/check-footage-station.py
# Or with the DHCP address (replace the example):
python3 scripts/check-footage-station.py egouda@10.0.0.123
```

These checks accept a new SSH host key on first contact, retain it in known_hosts,
and refuse changed keys. Inspect any unexpected hostname/hardware before continuing.
The Mac and server public keys are provisioned; private keys and server credentials
are never copied onto the boot card. SSH password/root login are disabled. The
owner's SSH account has passwordless sudo for subsequent device administration.

Cloud-init establishes access without waiting for package downloads. A separate
systemd unit installs Python, rsync, exFAT tools and Avahi and retries failures.
Successful setup writes `/var/lib/footage-station/base-ready`.

```sh
cloud-init status --long
sudo journalctl -u footage-station-bootstrap -b --no-pager
sudo systemctl restart footage-station-bootstrap
```

Restarting the unit after success is harmless: the marker prevents it running.
OS updates and real-device reboot testing happen during commissioning. Do not
reflash a working station to apply ordinary application changes.

## Reproduce card preparation on Linux

The pinned source, expanded image size and SHA-256 live in
`config/footage-station/image.json`. It is Raspberry Pi OS Lite 64-bit, Debian
Trixie, release 2026-06-18, with `cloudinit-rpi` first-boot customization.
The upstream manifest explicitly includes the Pi 3 64-bit family.

Download the `.img.xz` URL in that file to a private cache outside Git. Fetch its
`.sha256` companion, verify with `sha256sum -c`, and decompress with `xz -dk`.
The preparation tool independently verifies the expanded pinned SHA-256.

Use `lsblk -b -o NAME,SIZE,MODEL,TRAN,RM,FSTYPE,LABEL,MOUNTPOINTS` to identify the
card. Never assume `/dev/sdd` remains the correct device after reconnection.
Copy only the Mac's **public** SSH key to the server's private staging directory.

```sh
# On home-server; substitute the actual inspected link/size and local paths.
sudo python3 scripts/prepare-footage-station.py \
  --device /dev/disk/by-id/usb-Generic_STORAGE_DEVICE-0:0 \
  --expected-size 63864569856 \
  --image /home/egouda/.cache/home-server/pi-images/2026-06-18-raspios-trixie-arm64-lite.img \
  --public-key /home/egouda/.cache/home-server/pi-images/mac-admin.pub \
  --public-key /home/egouda/.ssh/id_rsa.pub \
  --backup-root /home/egouda/.local/state/home-server-maintenance/footage-station
```

Without `--erase`, this only inspects the target and validates the public keys.
Add `--erase` only when deliberately repurposing the selected card. The tool:

1. Requires a partitioned removable USB whole disk, matching capacity and no system
   mounts. Missing partition trees abort; raw/unpartitioned cards need separate
   inspection instead of silently bypassing the existing-data backup.
2. Verifies the official raw image before changing the card.
3. Unmounts the old partitions and archives existing supported non-ISO filesystems
   read-only, including their metadata. Small unformatted partitions are saved raw.
   Unsupported filesystems abort preparation. It compares archives to the source
   and records their hashes before writing.
4. Writes the image and checks the complete written image against its pinned hash.
5. Writes `user-data`, `network-config` and `meta-data`, then remounts read-only
   and compares the persisted configuration. All card filesystems end unmounted.

The old Ubuntu installer ISO itself is **not** archived; its identity/partition
layout and writable installation logs are preserved. This is a file backup,
not a bootable forensic image. Formatting is not secure erasure.
The timestamped backup contains `archives.json` and, on success, `prepared.json`.
Backups are private and root-owned; use sudo to inspect/restore them. Do not commit
them. Test the guards with `python3 scripts/test-prepare-footage-station.py`.

## Automatic import contract

The Pi's own root/boot disk must never appear as an ingest source. Only supported removable
USB FAT/exFAT camera volumes are mounted read-only; their DCIM folders import automatically. Each shoot has a project
and unique card identifier; original file names and relative paths are retained.
Use the existing `Creative/Projects/<project>/Originals/<card>/` layout, alongside
SHA-256 manifests, compatible with `scripts/ingest-footage.py` on the Mac.

Provision a separate restricted transfer identity after first boot, without giving
the station the owner's server shell or whole-disk File Browser credentials.
Persist transfer state, retry interrupted files, and publish complete files without
overwriting conflicting originals. A completed import requires source and server
hash agreement. Re-running an identical card skips matching data. The UI should
report verification separately from copying and warn that another independent
copy is still needed before reusing camera cards.

The next stage must test this contract end-to-end rather than assuming the existing
Mac SMB importer's publication semantics work unchanged on the Pi.

## Transfer backend implementation

`services/footage-station/receiver.py` is designed for an SSH forced command with
a fixed Creative root. It accepts a bounded JSON/binary protocol, never shell
commands. A single receiver lock serializes imports; partial files live under
`.footage-ingest/partials`. A retry verifies the saved prefix against the source,
continues at that byte offset, or explicitly resets a corrupt partial. Complete
files are SHA-256 verified and atomically hard-linked into Originals without
overwriting a conflicting name. Completion manifests are published only after all
expected files have been verified and the originals rechecked.

`transfer.py` reads an explicitly supplied camera folder, rejects symlinks and
special files, detects source changes and emits machine-readable progress events.
Its production SSH command requires a pinned host key and dedicated identity.
The commissioning script installs the dedicated forced key and Pi service after hardware boot.

`card_helper.py` runs through a narrow sudo rule for the unprivileged
Pi service account. It selects removable USB FAT/exFAT partitions, excludes the
entire operating-system disk (including USB boot), rejects ambiguous IDs and
mounts only read-only with noexec/nodev/nosuid. Mount/unmount operations have not
yet been tested on the Pi. The UI must not bypass this helper or accept arbitrary
source paths from a browser request.

```sh
python3 -m unittest discover -s services/footage-station -p 'test_*.py' -v
```

Transfer tests cover interrupted binary chunks, corrupt partials, identical reruns,
conflicting originals, checksum failure, missing completion requirements, source
and destination symlinks, path traversal and concurrent clients. Selection tests
cover normal and USB boot disks, unknown roots, existing foreign mounts and
duplicate IDs. Transfer tests pass on both macOS and the Ubuntu server. A real
Mac→home-server SSH test also resumed a deliberately truncated chunk and published
the manifest; repeating that import transferred zero media bytes. All test media
was synthetic and the SSH test's private temporary data was removed afterward.

## Tracking interface and server deployment

Open **http://ingest.lan** from a Mac or phone, on the LAN or through the existing
Tailscale split-DNS setup. Sign in as `egouda` with the existing home-services
password. NPM authenticates every request; the console has no published host port.
It shows station freshness, copy/verification phases, incomplete and verified
imports, project/session assignments, manifest paths and Codex job results.

New cards default to `Inbox`. You can set a different destination for future cards,
or assign descriptive project and shoot names after import. Assignments are
catalog metadata and do not relocate originals. An unchanged card reinserted after
reboot keeps its route, verifies existing bytes and does not repeat paid Codex work.
Adding/removing files changes the card-selection fingerprint and creates a new
batch; unchanged files in that changed batch may occupy another copy. Automatic
cross-batch deduplication and scene clustering are not implemented. Do not erase
camera originals based on a suggestion that two shots look similar.

Run on the server as its owner:

```sh
python3 scripts/configure-footage-console.py
docker compose --env-file server.conf --env-file .env build footage-console
docker compose --env-file server.conf --env-file .env up -d footage-console footage-codex
make check-server
python3 scripts/check-footage-console.py
```

Private runtime metadata is under `CREATIVE_ROOT/.footage-ingest`; never commit it.
The Codex worker has a private persistent copy of the owner's subscription login
under `HOME_SERVER_SECRETS_DIR/footage-codex-auth`, seeded only when missing so token
refresh survives restarts. No API key or separate API billing is used. Reviews
are serialized and have a 180-second timeout; failures are visible and retriable.
A retry request never overwrites a running job. CLI shell, browser, app, hooks and
multi-agent tools are disabled, originals are mounted read-only, and the current
review input contains only file names/sizes and project/session labels (up to 200
files, with truncation disclosed). This is intake advice, **not visual clustering**.
Generated notes cannot move files or execute a suggested command.

[Codex non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode)
describes saved CLI authentication and automation. This is a private home-server
worker; the public repository contains deployment code only, never account tokens,
private manifests or job output.

## Commission the booted Pi

From the Mac, first verify the OS and host identity, then install the application:

```sh
python3 scripts/check-footage-station.py
python3 scripts/commission-footage-station.py
# If mDNS is unavailable, pass --pi egouda@<DHCP-address> to commissioning.
```

The installer checks the Pi 3 B model and bootstrap completion marker. It installs
root-owned application files and a limited mount helper, creates an unprivileged
`footage-station` account, generates its private transfer key **on the Pi**, pins
the server's host public key obtained through the authenticated Mac→server SSH
connection, and registers a restricted forced command on the server. That key
cannot open a shell, forward ports or choose a destination outside Creative.
It then enables `footage-station.service` for automatic start after reboot.

The service polls every 10 seconds. A connected camera card imports without a
screen or project prompt. Failures back off from 30 seconds to five minutes;
**Retry import** resets that delay. Original file contents are never written on the
card. **Safe to remove** appears only after complete verification and successful
unmount. Keep another independent copy before reusing the camera card.

Before commissioning is considered complete, verify these on actual hardware:

- Model, expanded root filesystem, Ethernet, SSH and base packages.
- Service heartbeat on ingest.lan after installation and after a Pi reboot.
- Boot disk excluded; supported camera DCIM mounted read-only.
- Synthetic card import, SHA-256 match, manifest and safe ejection.
- Interrupted transfer resumes; no incomplete batch shown as verified.
- Reinserted unchanged card transfers zero already-verified bytes.
- Automatic Codex job completes and its notes appear on the tracking page.

Server tests cover the protocol and state machine but do not substitute for these
hardware checks. Run `make check-network` from the Mac after deployment.

## Source references

- [Official OS manifest](https://downloads.raspberrypi.com/os_list_imagingutility_v4.json)
- [Raspberry Pi OS downloads](https://www.raspberrypi.com/software/operating-systems/)
- [Cloud-init on Raspberry Pi OS](https://www.raspberrypi.com/news/cloud-init-on-raspberry-pi-os/)
- [Imager customization formats](https://github.com/raspberrypi/rpi-imager/blob/main/doc/os_customisation_formats.md)
- [Existing Creative storage and verified import](creative-storage.md)
