#!/usr/bin/env bash
# Install Ubuntu's matching HWE kernel and NVIDIA 580 modules. Reboot is opt-in.
set -euo pipefail
[[ $(id -u) == 0 && $(hostname) == home-server ]] || {
    echo 'Run as root on home-server' >&2; exit 1;
}
[[ $# == 0 || ( $# == 1 && $1 == --reboot ) ]] || {
    echo "Usage: $0 [--reboot]" >&2; exit 1;
}
exec > >(tee -a /var/log/home-server-kernel-upgrade.log) 2>&1
trap 'echo "Upgrade failed at line $LINENO; automatic reboot cancelled."' ERR
export DEBIAN_FRONTEND=noninteractive
printf 'Starting kernel/GPU maintenance: %s\n' "$(date --iso-8601=seconds)"
printf 'Previous kernel: %s\n' "$(uname -r)"
apt-get update
apt-get -y --no-remove -o Dpkg::Options::=--force-confold install \
    linux-generic-hwe-22.04 \
    linux-modules-nvidia-580-generic-hwe-22.04 \
    nvidia-driver-580

audit=$(dpkg --audit)
[[ -z $audit ]] || { printf '%s\n' "$audit"; exit 1; }
kernel=$(dpkg-query -W -f='${Depends}' linux-image-generic-hwe-22.04 |
    grep -oE 'linux-image-[0-9][^ ,()]+' | head -1)
kernel=${kernel#linux-image-}
[[ -n $kernel && -s /boot/vmlinuz-$kernel && -s /boot/initrd.img-$kernel ]]
driver=$(modinfo -k "$kernel" -F version nvidia)
utils=$(dpkg-query -W -f='${Version}' nvidia-utils-580)
[[ $utils == "$driver"-* ]] || {
    echo "NVIDIA module/userspace mismatch: $driver / $utils"; exit 1;
}
update-grub
printf 'Verified boot files and matching NVIDIA modules: kernel=%s driver=%s\n' "$kernel" "$driver"
sync
if [[ ${1:-} == --reboot ]]; then
    echo 'Upgrade verified; rebooting now.'
    systemctl reboot
else
    echo 'Upgrade verified. Reboot before using GPU workloads.'
fi
