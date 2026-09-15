#!/bin/sh
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends bluez python3-bleak python3-serial python3-venv avahi-daemon git
systemctl enable --now bluetooth avahi-daemon ssh
install -d -m 0755 /var/lib/gym-pi
touch /var/lib/gym-pi/base-ready
