#!/bin/bash
# Run as root only after verifying key-based SSH and private recovery backups.
set -euo pipefail
[[ $EUID = 0 ]] || { echo 'Run as root'; exit 1; }
backup=/root/home-server-security-20260916
mkdir -p "$backup"
chmod 700 "$backup"
if [[ ! -e "$backup/rollback.sh" ]]; then
  cp -a /etc/ufw "$backup/ufw"
  cat > "$backup/rollback.sh" <<'ROLLBACK'
#!/bin/bash
ufw disable
rm -f /etc/ssh/sshd_config.d/00-home-server-security.conf
sshd -t && systemctl reload ssh
systemctl enable --now vsftpd
systemctl disable --now home-server-docker-firewall.service 2>/dev/null || true
iptables -D DOCKER-USER -j HOME-SERVER-INGRESS 2>/dev/null || true
ROLLBACK
  chmod 700 "$backup/rollback.sh"
fi
systemd-run --unit=home-server-security-rollback --on-active=10m "$backup/rollback.sh"
cat > /etc/ssh/sshd_config.d/00-home-server-security.conf <<'SSH'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
X11Forwarding no
SSH
sshd -t
systemctl reload ssh
systemctl disable --now vsftpd
ufw default deny incoming
ufw default allow outgoing
ufw allow from 10.0.0.0/24 comment 'Home LAN'
ufw allow in on tailscale0 comment 'Authenticated tailnet'
ufw allow from 172.16.0.0/12 comment 'Container integrations'
ufw allow 41641/udp comment 'Tailscale transport'
ufw --force enable
printf '%s\n' 'Host protection applied; rollback fires in 10 minutes unless cancelled after independent checks.'
