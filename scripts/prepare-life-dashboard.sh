#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source server.conf
mountpoint -q "$(dirname "$LIFE_DASHBOARD_DATA")" || { echo 'Life Dashboard SSD is not mounted.' >&2; exit 1; }
if [[ ! -d "$LIFE_DASHBOARD_REPO/.git" ]]; then
  git clone git@github.com:essamgouda97/life-dashboard.git "$LIFE_DASHBOARD_REPO"
fi
docker run --rm --network none -v "$LIFE_DASHBOARD_DATA:/state" alpine:3.22 \
  sh -ec 'for d in docs data generated codex; do mkdir -p /state/$d; chown 1000:1000 /state/$d; chmod 700 /state/$d; done; chown 1000:1000 /state; chmod 700 /state'
mkdir -p "$HOME_SERVER_SECRETS_DIR/life-dashboard-health"
chmod 700 "$HOME_SERVER_SECRETS_DIR/life-dashboard-health"
test -f "$LIFE_DASHBOARD_DATA/data/finances.sqlite" || {
  echo 'Restore/migrate the private documents and a verified SQLite snapshot first.' >&2; exit 1;
}
