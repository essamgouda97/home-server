#!/bin/sh
# Run from a checkout on the Pi. Existing local display/identity config is preserved.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
test "$(cat /etc/hostname)" = gym-pi
test "$(uname -m)" = aarch64
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  cargo rustc pkg-config libdbus-1-dev build-essential
cd "$repo/services/gym-heart-rate"
CARGO_BUILD_JOBS=2 cargo test --locked
CARGO_BUILD_JOBS=2 cargo build --release --locked
sudo install -m 0755 target/release/gym-heart-rate /usr/local/bin/gym-heart-rate.new
sudo mv /usr/local/bin/gym-heart-rate.new /usr/local/bin/gym-heart-rate
sudo install -d -m 0755 /etc/gym-pi
if ! sudo test -f /etc/gym-pi/heart-rate.json; then
  sudo install -m 0600 -o egouda -g egouda "$repo/config/gym-pi/heart-rate.json" /etc/gym-pi/heart-rate.json
fi
sudo install -m 0644 "$repo/config/gym-pi/heart-rate.service" /etc/systemd/system/gym-heart-rate.service
sudo systemctl daemon-reload
sudo systemctl enable --now gym-heart-rate.service
sudo systemctl restart gym-heart-rate.service
sudo systemctl is-active gym-heart-rate.service
