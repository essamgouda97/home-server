# Gym Pi: Raspberry Pi 3 Model B

`gym-pi` is a separate Wi-Fi/Bluetooth node for the basement gym. The Rust program
in `services/gym-heart-rate` receives standard Fitbit Air heart-rate notifications
and drives a parallel 1602A LCD directly from six Pi GPIO pins. No Arduino is
required. A server SSH relay supplies the same live readings to Life Dashboard.
The previously tested 5461AS seven-segment display has been superseded by the LCD.

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
Physical Pi boot and Wi-Fi association subsequently passed: the Pi joined Wi-Fi at
`10.0.0.242`, Bluetooth was powered on, the base bootstrap completed, no systemd
units had failed, and `sudo vcgencmd get_throttled` returned `0x0`.

## Rust heart-rate receiver

The receiver uses btleplug/BlueZ for Bluetooth and RPPAL for the write-only LCD
interface. It consumes the standard Heart Rate Measurement characteristic
`2A37` in service `180D`. Only fields actually present in the packet are retained;
the program does not fabricate HRV, contact status or heart-rate samples.

Each notification wakes the display thread immediately. The LCD is updated only
when its text changes, overwrites the full line to erase old digits, and is never
cleared between readings. A monotonic 12-second freshness deadline replaces lost
or zero readings with `--- BPM`; disconnects blank the number immediately. The
program attempts to reconnect automatically. Fitbit controls the measurement cadence, so this
does not claim to sample faster than the tracker.

The JSON snapshot uses Life Dashboard's schema version 2 and keeps at most 90
recent samples. An atomic mode-0600 snapshot is written once per second at
`/var/lib/gym-pi/fitbit-live.json`. Health readings and device addresses are not
logged or committed. The LCD updates independently of snapshot writes or Wi-Fi.

To build and install on the Pi from this repository:

```sh
sh scripts/install-gym-heart-rate.sh
```

The installer uses the committed Cargo lockfile, runs tests, builds an optimized
binary, and enables `gym-heart-rate.service`. The first build on the Pi 3B takes
several minutes. The service runs as `egouda` with supplementary `gpio` access.
Configuration lives at `/etc/gym-pi/heart-rate.json`; existing settings survive
updates. `display` defaults to `off`, so installation does not drive unknown wiring.
After wiring is complete, change it to `lcd1602` and restart the service.

```sh
sudo systemctl restart gym-heart-rate
systemctl status gym-heart-rate --no-pager
journalctl -u gym-heart-rate -n 20 --no-pager
```

Keep Fitbit's Share heart rate enabled in Google Health. The Pi matches the
advertised name `Google Fitbit Air`; if multiple matching trackers are nearby, set the
optional `device_address` in the private Pi config. It refuses ambiguous matches.
An address can change when the tracker uses Bluetooth privacy, requiring a local
configuration update. The Pi does not change Fitbit firmware or Google account
settings and does not need a Google OAuth token for live Bluetooth capture.

**Commissioning limitation:** Google Health requested “Share heart rate with
gym-pi?” again after disconnecting/restarting the receiver. A BlueZ pairing attempt
did not create a saved bond. Do not assume unattended reconnection: approve the
Pi under Google Health → Connections → Fitbit Air → Share heart rate when asked.
The receiver preserves an intact Bluetooth connection while waiting for approval
or new readings. It checks connection health during silence instead of disconnecting
after a notification timeout. The 12-second deadline only hides stale readings on
the LCD/dashboard; it does not trigger a fresh sharing request. Genuine link loss,
power cycles and service restarts can still require Google Health approval. Google's
published Fitbit Air instructions do not document a permanent approval setting.
Normal discovery follows fresh advertisements because Fitbit rotates
its Bluetooth address; it does not select an expired address from BlueZ's cache.
Leave `device_address` unset for this tracker unless deliberately commissioning
a stable identity in a multiple-tracker environment.

Software commissioning passed ten Rust packet/formatting/connection tests, five relay tests,
and the live check below against the actual Life Dashboard API after phone
approval. Both infrastructure health checks passed. Following physical wiring,
the Pi's private configuration was changed to `lcd1602` and automatic service startup
after a power cycle was observed. The owner measured expected supply/logic voltages
at the LCD pads. Contrast adjustment made text visible. After deploying the
display-reset support and reinitializing the LCD, the owner confirmed that the
display fully works and the previously garbled text is readable. This confirms
physical display operation; fresh Bluetooth data is checked separately below.

To reinitialize a garbled LCD without restarting Bluetooth capture:

```sh
sudo systemctl kill --kill-whom=main --signal=USR1 gym-heart-rate.service
```

The display thread resets the HD44780 interface and redraws both rows while the
existing Bluetooth session continues. This cannot repair loose connections, swapped
data wires, or unsuitable signal levels. Keep power disconnected while rewiring.

```sh
# From the Mac; requires the Fitbit nearby and heart-rate sharing approved:
python3 scripts/check-gym-heart-rate.py --require-live
```

## 1602A LCD wiring

Power off the Pi before rewiring and disconnect the old seven-segment setup.
This mapping is for a normal **5 V HD44780-compatible 1602A** in four-bit mode.
Check a module explicitly marked 3.3 V before using the 5 V supply.

| LCD pin | Label | Pi connection |
|---|---|---|
| 1 | VSS | Ground, physical 6 |
| 2 | VDD | 5 V, physical 2 |
| 3 | V0 | Contrast potentiometer wiper |
| 4 | RS | Physical 11, BCM17 |
| 5 | RW | Ground permanently |
| 6 | E | Physical 13, BCM27 |
| 7–10 | D0–D3 | Unconnected |
| 11 | D4 | Physical 15, BCM22 |
| 12 | D5 | Physical 16, BCM23 |
| 13 | D6 | Physical 18, BCM24 |
| 14 | D7 | Physical 22, BCM25 |
| 15 | A | 5 V through 330 ohms; 1 kilohm works with dimmer light |
| 16 | K | Ground |

A breadboard ground rail connects VSS, RW and K to Pi ground. For adjustable
contrast, use a 10-kilohm potentiometer with its outer legs at 5 V and ground and
its wiper connected to V0. Remove any direct V0-to-ground connection. Grounding V0
gave excessive contrast on this module; adjust until the background cells fade
and characters remain legible. A fixed starting point using the available resistors
is `5V -> 1k -> 1k -> V0 -> 220 ohms -> GND`, approximately 0.50 V at V0.
This divider replaces the potentiometer and may need tuning for the module.
The extra backlight
resistor also limits current when the module has no onboard limiting resistor.

Pi GPIO outputs remain 3.3 V. A standard HD44780 accepts that logic level at a
5 V supply, but clone controllers with higher input thresholds need a suitable
unidirectional 3.3-to-5 V buffer, such as a 74HCT245. Never drive Pi GPIO with 5 V.
Grounding RW makes the LCD write-only and prevents its data bus driving back into
the Pi. Blank blocks before software initialization are normal; persistent blocks
after initialization suggest contrast, pin mapping, or logic-level problems.

The ordered `lcd_pins_bcm` config is `[RS, E, D4, D5, D6, D7]`. It must match the
physical wiring. GPIO initialization and LCD appearance require the actual wired
display; passing software tests is not proof of a physical display test.

## Life Dashboard and Mac retirement

`scripts/relay-gym-fitbit.py` runs on home-server as `gym-fitbit-relay.service` in
the operator's user systemd instance. It reads the bounded Pi snapshot over SSH,
using the already commissioned server identity and strict known-host checking.
It stores a private source copy and atomically updates Life Dashboard's existing
`data/bridge/fitbit-live.json`. There is no new public HTTP listener or port forward.
The existing application worker imports minute history; Google Health sync still
runs separately on the server and is not the live data path.

```sh
# On home-server, after establishing and checking SSH trust for gym-pi.local:
python3 scripts/install-gym-fitbit-relay.py
systemctl --user status gym-fitbit-relay --no-pager

# On the Mac, as explicitly requested by the owner:
python3 scripts/disable-mac-fitbit.py
```

The Mac bridge, watchdog and SSH Fitbit relay are disabled persistently. Their
LaunchAgent plists remain for rollback. `~/.config/home-server/gym-pi-primary`
prevents the Mac companion installer from re-enabling its old relay. The Resolve
companion and server Google Health synchronization are unaffected.

Rollback requires stopping the server gym relay first, removing that Mac marker,
and using `launchctl enable` and `launchctl bootstrap` with the three retained
Mac LaunchAgents. Run the Mac receiver only when intentionally returning live
capture to it, so two receivers do not compete for the tracker's connection.

Sources: [HD44780 controller datasheet](https://www.sparkfun.com/datasheets/LCD/HD44780.pdf),
[Google heart-rate sharing](https://support.google.com/googlehealth/answer/14236705?hl=en),
[btleplug](https://docs.rs/btleplug/0.11.8/btleplug/),
[RPPAL GPIO](https://docs.rs/rppal/0.22.1/rppal/gpio/).

References: [Raspberry Pi getting started](https://www.raspberrypi.com/documentation/computers/getting-started.html),
[Pi OS cloud-init](https://www.raspberrypi.com/news/cloud-init-on-raspberry-pi-os/),
[Netplan Wi-Fi configuration](https://netplan.readthedocs.io/en/stable/netplan-yaml/).
