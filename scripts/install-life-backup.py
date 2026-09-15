#!/usr/bin/env python3
"""Install a persistent daily user timer; requires the existing Docker operator."""
from pathlib import Path
import subprocess
repo=Path(__file__).resolve().parents[1]
units=Path.home()/'.config/systemd/user';units.mkdir(parents=True,exist_ok=True)
(units/'life-dashboard-backup.service').write_text(f'''[Unit]
Description=Private Life Dashboard backup

[Service]
Type=oneshot
UMask=0077
WorkingDirectory={repo}
ExecStart=/usr/bin/python3 {repo}/scripts/backup-life-dashboard.py
TimeoutStartSec=1800
''')
(units/'life-dashboard-backup.timer').write_text('''[Unit]
Description=Back up Life Dashboard daily

[Timer]
OnCalendar=*-*-* 04:15:00
Persistent=true

[Install]
WantedBy=timers.target
''')
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
subprocess.run(['systemctl','--user','enable','--now','life-dashboard-backup.timer'],check=True)
print('Daily 04:15 Life Dashboard backup timer enabled.')
