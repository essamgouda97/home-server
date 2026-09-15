#!/bin/sh
set -eu
docker run --rm \
  -v /mnt/server/npm/letsencrypt:/etc/letsencrypt \
  -v /home/egouda/.config/home-server/secrets/cloudflare-dns.ini:/run/secrets/cloudflare.ini:ro \
  certbot/dns-cloudflare@sha256:0dbdb8667052256f5ebdd8a56bbf24cf80b6045a9520fdfb5575c087011341ee \
  renew --cert-name household --quiet "$@"
docker exec npm nginx -t >/dev/null 2>&1
docker exec npm nginx -s reload >/dev/null 2>&1
