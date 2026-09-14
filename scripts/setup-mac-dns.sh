#!/bin/sh
# Route only *.lan to the home server; preserve Wi-Fi/VPN DNS for other names.
set -eu
SERVER_IP=${1:-10.0.0.182}
case "$SERVER_IP" in *[!0-9.]*|'') echo 'Expected an IPv4 address' >&2; exit 1;; esac
[ "$(uname -s)" = Darwin ] || { echo 'This script is for macOS' >&2; exit 1; }
[ "$(id -u)" = 0 ] || { echo "Run: sudo $0 $SERVER_IP" >&2; exit 1; }
mkdir -p /etc/resolver
if [ -f /etc/resolver/lan ]; then
    cp -p /etc/resolver/lan "/etc/resolver/lan.backup.$(date +%Y%m%d%H%M%S)"
fi
printf 'nameserver %s\n' "$SERVER_IP" > /etc/resolver/lan
chmod 644 /etc/resolver/lan
dscacheutil -flushcache
killall -HUP mDNSResponder
echo "Configured .lan DNS through $SERVER_IP"
