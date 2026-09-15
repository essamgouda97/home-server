# Gym Pi: Raspberry Pi 3 Model B

`gym-pi` is a separate Wi-Fi/Bluetooth node for the basement gym. Its intended
next role is receiving live Bluetooth heart-rate measurements and sending them
over USB serial to an Arduino driving the 5461AS display. Heart-rate receiver and
display firmware still need commissioning; this setup prepares the OS and radios.

## Card and network

- Raspberry Pi OS Lite 64 bit, Debian Trixie, installed release 2026-06-18.
- Existing 63,864,569,856-byte removable SD card, USB reader stable link
  `/dev/disk/by-id/usb-Generic_STORAGE_DEVICE-0:0` on home-server.
- Existing initialized OS is retained; no formatting or reflashing is needed.
- Hostname `gym-pi`, SSH user `egouda`, existing authorized Mac/server keys.
- Wi-Fi DHCP and automatic connection on `wlan0`, 2.4 GHz, country Canada.
- SSH password login disabled; existing local console password is preserved.
- Avahi advertises `gym-pi.local`; Bluetooth starts at boot.
- Old footage bootstrap is disabled, and cloud-init is disabled after initial
  provisioning so its old seed cannot restore `footage-pi` or Ethernet settings.
- Wi-Fi powersaving is disabled, saved radio blocks are cleared, and a startup
  service sets the country and unblocks Wi-Fi/Bluetooth before NetworkManager.
- First networked boot installs BlueZ, Python Bleak, serial/venv tools and Git.
  The bootstrap retries if the network or package mirrors are initially unavailable.
- Persistent journal is capped at 64 MB for troubleshooting.

The Pi 4 footage station is a separate device with a separate card. Do not apply
this configuration to it. The Pi 3's previous boot recorded undervoltage: use a
reliable 5 V / 2.5 A supply and a good Micro-USB cable.

## Reproduce the offline configuration

Mount the card's ext4 root and FAT boot partitions on a Linux maintenance host.
Inspect `lsblk` first: the stable USB name identifies the reader, so the exact
capacity and mounted partition checks also matter.

Store Wi-Fi credentials in a mode-0600 JSON file outside the repository, with
`ssid` and `password` fields. Use a password manager or a hidden input prompt;
do not put credentials in a command argument or shell history. The current private
input lives at `~/.config/home-server/secrets/gym-pi-wifi.json` on home-server.

```sh
python3 scripts/test-prepare-gym-pi.py
sudo python3 scripts/prepare-gym-pi.py \
  --device /dev/disk/by-id/usb-Generic_STORAGE_DEVICE-0:0 \
  --expected-size 63864569856 \
  --root /media/egouda/rootfs \
  --boot /media/egouda/bootfs \
  --wifi-json /home/egouda/.config/home-server/secrets/gym-pi-wifi.json \
  --backup-dir /home/egouda/.local/state/home-server-maintenance/gym-pi
```

The default performs validation only, including actual Netplan generation in a
temporary isolated directory. Repeat with `--apply` to write the card. The script
requires an initialized Raspberry Pi OS card with the expected hostname and SSH
keys; it is intentionally not a generic installer for arbitrary disks. To prepare
a replacement blank card, first install Raspberry Pi OS Lite 64 bit and seed the
`egouda` account with authorized SSH keys, using `gym-pi` as the hostname.

Configuration backups are stored privately on the maintenance host before any
card writes. They contain the old `/etc`, radio state and cloud-init boot seeds
and may contain credentials. Keep them out of Git. The new Wi-Fi configuration
exists only in the private input and the card's root-only
`/etc/netplan/90-gym-pi.yaml`; no Wi-Fi password is placed on the FAT boot volume.

After provisioning, sync, unmount both partitions and safely eject the reader
before moving the SD card to the Pi 3B. Ethernet is unnecessary.

## First physical boot and checks

Allow a few minutes for Wi-Fi startup and the initial package install, then:

```sh
ssh egouda@gym-pi.local
hostnamectl
nmcli -f DEVICE,TYPE,STATE device status
ip -4 address show wlan0
iw reg get
rfkill list
systemctl is-active ssh NetworkManager avahi-daemon bluetooth
systemctl status gym-pi-bootstrap --no-pager
test -f /var/lib/gym-pi/base-ready && echo 'Development tools ready'
bluetoothctl list
vcgencmd get_throttled
```

An inactive successful oneshot bootstrap with `base-ready` present is normal.
For failures use `journalctl -b -u NetworkManager -u gym-pi-radio` and
`journalctl -b -u gym-pi-bootstrap`. Avoid publishing logs that expose network names.
If `.local` discovery fails, find `gym-pi` in the Rogers connected-device list and
SSH to its DHCP address. The router must offer the configured network on 2.4 GHz
with WPA2-Personal compatibility (a combined WPA2/WPA3 network is suitable).

Offline validation proves the configuration renders; Wi-Fi association, Bluetooth
reception, actual power stability and reboot recovery must be checked on the Pi.
The card is prepared for these checks; no physical boot is claimed by provisioning.

## Provisioning record: 2026-09-15

The card was configured and read back from freshly mounted read-only filesystems.
The saved Wi-Fi configuration matched the private input, the current Mac SSH key
was present, and the hostname, radio state and startup service links were verified.
Both partitions were unmounted after verification.

The ext4 check passed using e2fsck 1.47.2 in a disposable Debian Trixie container
with read-only access to the partition. Ubuntu 22.04's e2fsck 1.46.5 cannot check
this filesystem's newer features; its unsupported-feature error is not evidence
of filesystem corruption. The FAT partition had an old dirty flag, which was
cleared after a full private boot-partition backup; the subsequent FAT check passed.
The backup is under
`~/.local/state/home-server-maintenance/gym-pi/20260915T182205Z/` on home-server.

Six provisioning tests passed. `make check-server` passed; the Mac's
`make check-network` passed on retry after one transient UDP DNS timeout.
Physical Pi boot and Wi-Fi association remain pending.

References: [Raspberry Pi getting started](https://www.raspberrypi.com/documentation/computers/getting-started.html),
[Pi OS cloud-init](https://www.raspberrypi.com/news/cloud-init-on-raspberry-pi-os/),
[Netplan Wi-Fi configuration](https://netplan.readthedocs.io/en/stable/netplan-yaml/).
