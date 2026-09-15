#!/usr/bin/env python3
"""Install on home-server as the normal operator after SSH trust is established."""
from pathlib import Path
import subprocess

repo = Path(__file__).resolve().parents[1]
folder = Path.home()/'.config/systemd/user'
folder.mkdir(parents=True, exist_ok=True)
unit = (repo/'config/gym-pi/relay.service').read_text().replace('@@REPO@@', str(repo))
(folder/'gym-fitbit-relay.service').write_text(unit)
subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
subprocess.run(['systemctl', '--user', 'enable', '--now', 'gym-fitbit-relay.service'], check=True)
subprocess.run(['systemctl', '--user', 'restart', 'gym-fitbit-relay.service'], check=True)
print('Gym Pi SSH relay enabled.')
