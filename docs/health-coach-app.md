# Personal coach web app

The private service is at **https://coach.home.egouda.xyz**. The owner central
session opens it directly; there is no second Coach password. It serves iPhone and desktop browsers;
there is no app-store install. The coach continues using the original Google Sheet.

## Reporting workflow

- Training shows the coach's four workout groups, prescriptions, notes and video
  links. Choose a numbered coach log entry, start a session, and save actual kg
  and repetitions (or seconds for timed exercises). The sheet's log blocks do not
  contain dates: imported history retains entry numbers, while new app sessions
  have dates. Choose an empty block for a new workout rather than overwriting an
  old block. The Centr stack calculator requires an explicit pulley ratio and
  preserves the owner's supplied rounded kilogram table. Smith-bar loads are
  entered directly.
- Meals shows English translations of the ingredient alternatives, exact amounts,
  weighing rules, supplements and preparation links. Selections, completion and
  notes stay in the app. No nutrition totals are invented from ingredient text.
- Today records cardio duration/activity/notes and daily bodyweight. Live BPM reuses
  the existing gym Pi relay; no second Bluetooth receiver is started. Stale or
  disconnected readings are hidden. Actual fresh samples are retained locally.
- Progress edits the coach's existing weekly weigh-ins, diet adherence, hunger,
  sleep, training, cardio, soreness and comments. **Draft from this week's logs**
  fills empty fields using actual saved records; it never invents subjective
  ratings or an adherence percentage. Review and save to send the report.
- Coach sync shows pending changes and conflicts. Entries save to SQLite first,
  then the worker sends pending reporting cells within approximately one minute.
  Refresh status after a sync to see the read-back result.

The app translates the current source text for display. Source option values,
cell addresses, expected values and identities retain their originals; translating
labels cannot redirect a write. The private `translations.json` is a reviewed
exact-text dictionary. New or changed Arabic wording needs a new reviewed entry;
this is not an unverified automatic translation service. User-written check-in
comments are sent in the language entered. The coach's Arabic plans are unchanged.

## Sheet contract

`services/health-coach/model.py` reads explicit ranges and builds the mapping from
source exercise references and set headers. It detects the irregular spacing of
later log blocks instead of assuming every block is twelve columns wide.

Only mapped kg/repetition cells in Log book and reporting columns F:R of weekly
check-ins are writable. Plan cells, formulas, formatting and protected calculated
columns are preserved. Existing formula errors are surfaced rather than repaired
as part of reporting. Edits store an operation ID, cell identity, expected value,
desired value and status. A fresh read precedes RAW values updates; a second read
verifies them. Already-applied values are acknowledged after a lost response.
Changed identities/values become conflicts for the owner to resolve.

Google Sheets has no general atomic cell compare-and-swap. Read-before-write
checks reduce conflicts but cannot eliminate a coach edit made at exactly the
same moment. Avoid editing a reporting cell in both interfaces simultaneously.

## Deployment and private state

The isolated Compose project is `health-coach`, container `health-coach`:

```sh
rsync -az --exclude __pycache__ services/health-coach/ \
  home-server:workspace/home-server/services/health-coach/
scp compose.coach.yml home-server:workspace/home-server/
ssh home-server
cd ~/workspace/home-server
docker compose -p health-coach -f compose.coach.yml up -d --build
python3 scripts/check-coach.py --local
python3 scripts/configure-coach-proxy.py
python3 scripts/check-coach.py
make check-server
```

Run `make check-network` from the Mac. The proxy installer checks the download
service logins before/after its isolated nginx change, backs up previous config
outside Git, validates nginx and checks an actual final HTTPS coach login.
The application is published only through household HTTPS; port 18099 is loopback.

Private server files (never print or commit):

- Central identity arrives through the isolated `health-coach_auth` Docker network.
  Only Nginx and Coach join it; client-supplied identity headers are overwritten.
- `~/.config/home-server/secrets/coach-google.json`: OAuth client ID, client secret
  and refresh token, exported from the owner's authorized Google account.
- `~/.config/home-server/secrets/coach-config.json`: `spreadsheet_id`.
- `~/.config/home-server/secrets/coach-device-key`: independent random machine key.
- `/srv/mergerfs/ssd/health-coach/`: SQLite database, exact-text English dictionary,
  backups, and latest camera image. Directory 0700; private files 0600; uid 1000.

Authorize Google with the Sheets scope only. The app refreshes the access token
with OAuth and calls the supported Sheets API directly. Do not put credentials,
the coach's contents, source snapshots or translated personal plan in this public
repository. Translations must be preserved alongside database and secret backups.
The existing Life Dashboard remains separate; its Fitbit bridge is mounted read-only.

The owner-facing deterministic CLI uses the same authenticated API and field
validation as the web app. Run it on the server; keep input/output files private:

```sh
python3 scripts/coach-log.py read --file /private/path/current-plan.json
python3 scripts/coach-log.py queue --file /private/path/actual-edits.json
python3 scripts/coach-log.py sync
python3 scripts/coach-log.py status
```

An edit file contains an `id` (stable unique operation ID) and a `changes` array.
Each change has `ref`, `expected` (the value from the export) and `value` (the
actual new report). Unknown/protected refs and stale expected values are rejected.
The CLI never prints credentials or personal values and exports cannot overwrite
an existing file.

Lower-level deterministic maintenance commands run inside the container:

```sh
docker exec health-coach python sync.py read
docker exec health-coach python sync.py status
# Contains private proposed values: inspect only in a private terminal.
docker exec health-coach python sync.py preview
docker exec health-coach python sync.py apply
docker exec health-coach python sync.py backup
```

SQLite backups run daily and before sheet writes. They include the source snapshot,
projection, edit journal, user logs and BPM samples. To restore, stop the container,
retain the current database/WAL/SHM privately, copy a verified backup to
`coach.sqlite` with uid 1000 and mode 0600, ensure old WAL/SHM are not reused, then
restart and verify login and pending edits. Restore the English dictionary and
private credentials separately. Actual Sheets write permission was verified with an identical-value update and read-back, without adding health records. A backup was independently reopened and passed
SQLite integrity checking during commissioning. The JSON export contains personal
logs, edits, device observations and heart-rate samples.

## Jetson Nano and camera

Card preparation completed on 2026-09-16. The inherited DOS partition entry
extended past the physical card; its declared length was corrected without moving
or resizing the filesystem, making its partition UUID usable for boot selection.
The final NetworkManager profile, Mac/server keys, boot services, IMX219 DTB,
kernel/DTB hashes and filesystem checks passed. The reader was safely powered off.
Physical commissioning remains pending the owner's power supply.

Hardware identified from the inserted card: Seeed reComputer Nano 4 GB production
module with eMMC, L4T R32.6.1 / Ubuntu 18.04, and a custom `reComputer sdmmc` DTB.
The owner confirmed a Raspberry Pi Camera v2.1 (IMX219) and an installed Wi-Fi
module with two antennas. Preserve the vendor BSP and its SD overlay. Do not flash
a generic Nano developer-kit SD image or upgrade JetPack independently of eMMC.

The target hostname is `gym-jetson.local`, SSH user `egouda`, existing authorized
Mac/server keys, password SSH disabled. NetworkManager is preconfigured with the
same private household Wi-Fi as the gym Pi, with no interface-name/MAC lock and
Wi-Fi powersaving off. SSH and networking do not depend on installing the vision
software. First boot creates the account, new SSH host keys and host identity.
A separate retrying service installs build dependencies and compiles the staged
local TensorRT pose software. Initial compilation/model optimization can take time.

The full original card is backed up under the server's private maintenance
`jetson-card-20260916` directory. The provisioning script verifies its checksum,
filesystem, removable USB identity, size and partition UUID before formatting only
that card's root partition. It restores vendor software while excluding old home,
container and temporary data, retains the kernel/DTB byte-for-byte, points the card’s boot configuration at its stable partition UUID, installs
the gym services, checks the rebuilt filesystem and unmounts it. It never writes
to the Jetson's onboard eMMC, which is not accessible while powered off.

```sh
# Run on a Linux maintenance host. Never substitute another device blindly.
python3 scripts/backup-jetson-card.py --device /dev/disk/by-id/usb-Generic_STORAGE_DEVICE-0:0 \
  --output /private/maintenance/jetson-card
bash scripts/stage-jetson-software.sh /private/maintenance/jetson-source
python3 scripts/prepare-jetson-card.py \
  --device /dev/disk/by-id/usb-Generic_STORAGE_DEVICE-0:0 \
  --backup /private/maintenance/jetson-card \
  --bundle /private/maintenance/jetson-source/bundle \
  --secrets /home/egouda/.config/home-server/secrets \
  --keys /home/egouda/.config/home-server/secrets/gym-jetson-authorized-keys
# Repeat with --apply only for the specifically authorized card.
```

The private authorized-key bundle combines the existing Mac access keys with the server’s public SSH key. Scripts require root for block operations. The backup's original identified card
capacity and UUID are guards, not a general-purpose installer. The pinned source
revision and model checksum are in `scripts/stage-jetson-software.sh`.

### Powered commissioning — September 16

The owner reserved `10.0.0.150` for `gym-jetson`. SSH as `egouda` works
over `wlan0`; the powered system selected `/dev/mmcblk1p1` with the prepared
UUID `b861a2bb-1ebe-408a-9ea2-c261e83c4430`. L4T remains R32.6.1,
kernel 4.9.253-tegra. The IMX219 exposes `/dev/video0` and Argus is running.
The Wi-Fi module uses `iwlwifi`. A finite CSI/GStreamer capture produced a real
640×480 JPEG, visually inspected. The camera currently needs placement toward the
workout area before physical rep accuracy can be measured.

The vendor's older systemd rejects `Restart=on-failure` with `Type=oneshot`.
Bootstrap now uses `Type=simple` plus `RemainAfterExit=yes`. A minimal CUDA
compilation exposed a checksum-damaged `cicc` executable inherited from the
source image. Restoring NVIDIA's exact `cuda-nvcc-10-2` 10.2.300-1 package
made that compilation pass. `repair-cuda.py` verifies and, only when needed,
restores that package and its damaged runtime development archives from pinned,
SHA256-checked packages. No BSP upgrade is performed.
The gym service explicitly uses `/usr/bin/python3.6`, matching Ubuntu's packaged
OpenCV; the inherited system-wide `python3` points to 3.7 and lacks that module.
`patch-vision-build.py` links NumPy's static math library by its full path,
builds only the required Python 3.6 bindings, and restores upstream's distinct
`Jetson`/`jetson` package directories from pinned revisions on Linux (Mac staging
can collapse their case). The build and Python imports passed on the physical
device; `software-ready` exists and the gym agent starts successfully.
The Mac SSH alias `gym-jetson` points at the reservation above.

TensorRT generated and saved its FP16 engine. The authenticated web preview was
visually inspected, with fresh `no-person` status and approximately 12 fps local
pose processing. A real reboot then returned to the same Wi-Fi reservation and
SD root, with SSH, NetworkManager, Avahi, Argus and the enabled gym service active.
The cached model loaded and fresh authenticated camera frames returned without
rebuilding. Final owner HTTPS sign-in and device/camera checks passed after reboot.
Preview remains enabled for the owner's placement check. Physical skeleton
tracking, endpoint calibration and rep accuracy still require a person exercising
in view; no synthetic workout records were written to the coach's sheet.

The shared auth compiler supplies three exact native device routes:
`/api/device/context`, `/api/device/snapshot`, `/api/device/events`.
They require the application's machine Bearer key; all browser pages retain the
household gateway. Missing/incorrect keys and spoofed identity headers were
rejected through HTTPS. Actual gateway plus application sign-in passed, as did
the platform's full auth checks. Setup status reaches Gym monitor over HTTPS.

### Physical verification checklist

For a future reflash, verify SD root selection on the powered device. If eMMC boots
its old root instead, correct boot selection using the Seeed procedure. Repeat
these checks after hardware or boot changes:

```sh
ssh egouda@gym-jetson.local
findmnt -n -o SOURCE /
cat /etc/nv_tegra_release
nmcli -f DEVICE,TYPE,STATE device status
systemctl is-active ssh NetworkManager avahi-daemon nvargus-daemon
systemctl status gym-jetson-bootstrap --no-pager
test -f /var/lib/gym-jetson/software-ready
systemctl status gym-jetson --no-pager
ls /dev/video*
```

Use the router's device list if mDNS does not resolve. Check the Wi-Fi module's
actual driver and power stability. Check ribbon orientation with power disconnected.
Then enable preview in Gym monitor, confirm a real fresh image and skeleton, test
one-person tracking, calibrate and count an observed set, disconnect/reconnect Wi-Fi,
restart the service and finally reboot to verify recovery. Review any changed SSH
host key against the newly generated key on the device before trusting it.

On the home server, `python3 scripts/check-coach-device.py` verifies native-key
rejection and a fresh device heartbeat after actual gateway/application sign-in.
Add `--require-camera` with preview enabled to verify a fresh authenticated JPEG.

### Counting and preview behavior

Gym monitor offers an authenticated refreshed JPEG preview, current metric,
tracking state and suggested reps. Only the latest image is retained; stale frames
are hidden. Preview is off by default. The camera is idle unless preview or an
active selected exercise requests it, and pauses after server connectivity expires.
There is no cloud video processing or recording.

Five calibrated 2D movement profiles cover elbow bend, knee bend, shoulder raise,
hand separation and hip bend. Exercise names suggest a profile, but camera position
and personal endpoints require calibration. Wrist/calf movements and planks default
to manual logging. A repetition requires a complete high-low-high cycle with dwell
and timing guards. Missing keypoints, multiple people and tracking gaps reset the
incomplete movement. These observations do not assess safe form. No model confidence
score is invented when the underlying library does not provide one.

Counts and pending events are durable on the Jetson; event IDs deduplicate retries.
A device event never writes to Google Sheets directly. Select the matching session,
exercise and set, review/correct the suggested reps, then save them through the
same validated sheet outbox as manual entries.

## Validation

Run synthetic tests without real credentials or writes to the coach's sheet:

```sh
python -m unittest discover -s services/health-coach -p test_coach.py
python3 -m unittest discover -s services/health-coach/jetson -p test_counter.py
node --check services/health-coach/static/app.js
python3 scripts/test-jetson-card.py
```

Tests cover login/CSRF, protected cells, invalid values, optimistic edits, idempotent
retries, sheet conflicts and verified updates, stale BPM/camera behavior, machine
authentication, and complete/partial/interrupted movement cycles. Hardware-specific
vision is deliberately listed separately from these simulated checks.

References: [Seeed SD overlay](https://wiki.seeedstudio.com/J101_Enable_SD_Card/),
[Seeed SD boot](https://wiki.seeedstudio.com/J1010_Boot_From_SD_Card/),
[NVIDIA pose estimation](https://github.com/dusty-nv/jetson-inference/blob/master/docs/posenet.md),
[Sheets values updates](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchUpdate).

Browser commissioning also exercised cardio saving, session creation, counting
calibration, rep confirmation into the outbox, English ingredient selection and
persistence, and weekly report drafting/submission against an isolated local
snapshot with Google writes disabled. All six current production pages were
checked for English text. Production HTTPS login and a real identical-value Sheets
write/read-back passed without adding test health records to the live service.
