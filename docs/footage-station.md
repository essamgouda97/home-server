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
3. Commission the camera-card importer: read-only source mounting, phone-accessible
   project/card selection, copy progress, retries, checksums, conflict refusal,
   manifests and safe card removal. Test unplug/retry and reboot recovery using
   synthetic footage before importing valuable originals.
4. Connect verified import manifests to the future server shot catalog, browser
   previews, transcription, proxy delivery and versioned OTIO rough cuts for
   DaVinci Resolve. This is planned follow-on work, not installed by this image.

**Current boundary:** card provisioning and base onboarding only. There is no
Pi import UI or automatic camera import yet. No camera card is mounted, erased
or imported by first boot. The goal remains active until the Pi importer has
been commissioned and exercised on the real hardware.

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

## Planned import contract

The Pi's own root/boot disk must never appear as an ingest source. Only explicitly
selected removable camera volumes are mounted read-only. Each shoot has a project
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

## Source references

- [Official OS manifest](https://downloads.raspberrypi.com/os_list_imagingutility_v4.json)
- [Raspberry Pi OS downloads](https://www.raspberrypi.com/software/operating-systems/)
- [Cloud-init on Raspberry Pi OS](https://www.raspberrypi.com/news/cloud-init-on-raspberry-pi-os/)
- [Imager customization formats](https://github.com/raspberrypi/rpi-imager/blob/main/doc/os_customisation_formats.md)
- [Existing Creative storage and verified import](creative-storage.md)
