#!/bin/sh
# Bounded status only: no environment, credentials, Wi-Fi profiles or raw journals.
set -eu
umask 077
install -d -m 0755 /var/lib/footage-station
report=$(mktemp /var/lib/footage-station/network-report.XXXXXX)
trap 'rm -f "$report"' EXIT
{
    date --iso-8601=seconds
    uptime
    ip -brief address
    ip route
    printf '\nEthernet carrier: '
    cat /sys/class/net/eth0/carrier || true
    printf '\nEthernet state: '
    cat /sys/class/net/eth0/operstate || true
    vcgencmd get_throttled || true
    nmcli -f DEVICE,TYPE,STATE,CONNECTION device status || true
    systemctl is-active NetworkManager ssh avahi-daemon footage-station-bootstrap || true
    if test -f /var/lib/footage-station/base-ready; then
        printf '\nBase packages ready\n'
    fi
} > "$report" 2>&1
mv "$report" /var/lib/footage-station/network-report.txt
