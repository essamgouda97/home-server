#!/usr/bin/env python3
"""Retire Mac Fitbit capture after commissioning the gym Pi; preserve definitions."""
import os
from pathlib import Path
import subprocess

for label in (
    'com.egouda.personal-finances.fitbit-air-watchdog',
    'com.egouda.personal-finances.fitbit-air-bridge',
    'com.egouda.life-dashboard.fitbit-relay',
):
    domain = f'gui/{os.getuid()}/{label}'
    subprocess.run(['launchctl', 'bootout', domain], capture_output=True)
    subprocess.run(['launchctl', 'disable', domain], capture_output=True, check=True)
folder = Path.home()/'.config/home-server'
folder.mkdir(parents=True, exist_ok=True)
(folder/'gym-pi-primary').touch()
print('Mac Fitbit capture/watchdog/relay disabled. LaunchAgent definitions retained.')
