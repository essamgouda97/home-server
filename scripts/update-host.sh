#!/bin/sh
# Maintenance only: preserves configuration, never reboots or removes packages.
set -eu
[ "$(id -u)" = 0 ] || { echo "Run with sudo on home-server" >&2; exit 1; }
[ "$(hostname)" = home-server ] || { echo "Expected home-server" >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get -y -o Dpkg::Options::=--force-confold upgrade
apt-get -y install smartmontools
for disk in /dev/sda /dev/sdb /dev/sdc; do
    smartctl -H "$disk" || true
done
if [ -f /var/run/reboot-required ]; then
    cat /var/run/reboot-required
    echo 'Reboot intentionally left to the owner; check workloads first.'
fi
