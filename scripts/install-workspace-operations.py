#!/usr/bin/env python3
"""Install independent Workspace timers and existing-stack Grafana dashboard."""
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
units=Path.home()/'.config/systemd/user'
for name in ['home-workspace-metrics.service','home-workspace-metrics.timer','home-workspace-backup.service','home-workspace-backup.timer']:
    (units/name).write_bytes((ROOT/'templates/systemd'/name).read_bytes())
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
subprocess.run(['systemctl','--user','enable','--now','home-workspace-metrics.timer','home-workspace-backup.timer'],check=True)
subprocess.run(['systemctl','--user','start','home-workspace-metrics.service'],check=True)
subprocess.run(['docker','compose','-f','compose.monitoring.yml','up','-d','prometheus'],cwd=ROOT,check=True)
print('Workspace metrics, backup schedule and Grafana provisioning installed.')
