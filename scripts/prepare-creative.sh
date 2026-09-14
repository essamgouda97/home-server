#!/usr/bin/env bash
# Run as the Docker operator on the server. No host sudo step is required.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo"
source server.conf
mountpoint -q "$(dirname "$CREATIVE_ROOT")" || {
  echo 'Refusing initialization: the creative SSD is not mounted.' >&2; exit 1;
}
docker compose --env-file server.conf --env-file .env build samba
docker compose --env-file server.conf --env-file .env run --rm creative-init
python3 - <<'PY'
from pathlib import Path
settings = dict(line.split('=',1) for line in Path('server.conf').read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)
p=Path(settings['SERVER_DATA_DIR'])/'homeassistant'
for name, content in [('automations.yaml','[]\n'),('scenes.yaml','[]\n'),('scripts.yaml','{}\n'),
                      ('secrets.yaml',f'internal_url: "http://{settings["SERVER_IP"]}:8123"\nexternal_url: "http://assistant.lan"\nserver_host: "{settings["SERVER_IP"]}"\n')]:
    target=p/name
    if not target.exists():
        target.write_text(content)
        target.chmod(0o600)
secret_dir=Path(settings['HOME_SERVER_SECRETS_DIR'])
secret_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
secret_dir.chmod(0o700)
print('Creative folders and private application configuration prepared.')
PY
