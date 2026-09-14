#!/usr/bin/env bash
# Install the official signed Ubuntu package and enable unattended startup.
# Run as root; then authenticate with `tailscale up` as the operator.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_CODENAME" == jammy ]] || {
  echo 'This installer is for Ubuntu 22.04 (jammy).' >&2; exit 1;
}
operator=${1:-${SUDO_USER:-egouda}}
id "$operator" >/dev/null

install -d -m 755 /usr/share/keyrings
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/jammy.noarmor.gpg \
  -o /usr/share/keyrings/tailscale-archive-keyring.gpg
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/jammy.tailscale-keyring.list \
  -o /etc/apt/sources.list.d/tailscale.list
chmod 644 /usr/share/keyrings/tailscale-archive-keyring.gpg \
  /etc/apt/sources.list.d/tailscale.list
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-remove tailscale
systemctl enable --now tailscaled
tailscale set --operator="$operator" --hostname=home-server --accept-dns=false
echo 'Installed. As the operator, run:'
echo 'tailscale up --accept-dns=false --hostname=home-server --operator='"$operator"' --advertise-routes=10.0.0.182/32'
echo 'Complete browser sign-in, approve the host route, and configure split DNS (see docs/server-operations.md).'
