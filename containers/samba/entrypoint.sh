#!/bin/sh
set -eu
test -s /run/secrets/creative_password
mkdir -p /run/samba /var/log/samba /var/lib/samba/private
chmod 755 /var/lib/samba
chmod 700 /var/lib/samba/private
# The password is read from a private Compose secret, never from an environment
# variable or command-line argument. Updating the secret takes effect on restart.
{ cat /run/secrets/creative_password; printf '\n'; cat /run/secrets/creative_password; printf '\n'; } |
  smbpasswd -s -a egouda >/dev/null
testparm -s /etc/samba/smb.conf >/dev/null
exec smbd --foreground --no-process-group --debug-stdout
