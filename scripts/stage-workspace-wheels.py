#!/usr/bin/env python3
"""Stage pinned Linux wheels on the Mac for offline, reproducible server builds."""
from pathlib import Path
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
base=ROOT/'services/workspace'
common=[sys.executable,'-m','pip','download','--platform','manylinux2014_x86_64','--platform','manylinux_2_28_x86_64','--platform','manylinux_2_27_x86_64','--python-version','312','--implementation','cp','--abi','cp312','--only-binary=:all:']
for folder in [base,base/'sandbox']:
    wheels=folder/'wheelhouse';wheels.mkdir(exist_ok=True)
    subprocess.run(common+['--dest',str(wheels),'-r',str(folder/'requirements.lock')],check=True)
    expected=json.loads((folder/'wheels.sha256.json').read_text())
    for name,digest in expected.items():
        assert hashlib.sha256((wheels/name).read_bytes()).hexdigest()==digest,'Wheel checksum changed: '+name
print('Linux wheels staged; wheel binaries are ignored by Git. Checksum manifests are versioned.')
