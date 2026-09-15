#!/bin/bash
# First boot installs only the import station's base tools. No camera is erased
# or imported automatically; the application is provisioned after SSH validation.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get -o DPkg::Lock::Timeout=120 -o Acquire::Retries=3 update
apt-get -o DPkg::Lock::Timeout=120 -o Acquire::Retries=3 install -y --no-install-recommends \
  python3 python3-venv rsync exfatprogs ca-certificates avahi-daemon git
systemctl enable --now ssh avahi-daemon
install -d -m 0755 /var/lib/footage-station
date --iso-8601=seconds > /var/lib/footage-station/base-ready
