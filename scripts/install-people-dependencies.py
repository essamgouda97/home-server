#!/usr/bin/env python3
"""Install the pinned, local-only password estimator outside the system Python."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
target = Path.home()/'.local/share/home-server/people-python/4.5.0'
subprocess.run(['uv', 'pip', 'install', '--python', sys.executable,
                '--target', str(target), '--no-deps', '--require-hashes',
                '--only-binary', ':all:', '-r', str(root/'services/people/requirements.lock')], check=True)
