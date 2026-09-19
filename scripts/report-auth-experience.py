#!/usr/bin/env python3
"""Report second-login exceptions without reading or displaying any secret."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
services=json.loads((ROOT/'config/services.json').read_text())['services']
vault=json.loads((ROOT/'config/1password/catalog.json').read_text())['items']
seamless=[];bridge_recovery=[];managed=[];legacy=[]
for service in services:
    adapter=service['auth']['adapter'];name=service['id'];credential=service.get('credential')
    if adapter!='native':
        seamless.append(name)
        if adapter=='upstream-basic' and credential not in vault:
            bridge_recovery.append(name)
    elif credential and credential in vault:
        managed.append(name)
    else:
        legacy.append(name)
print('Seamless central browser sign-in:',', '.join(seamless))
print('Seamless bridge; recovery credential still needs 1Password migration:',', '.join(bridge_recovery) or 'none')
print('Second login, password managed in 1Password:',', '.join(managed) or 'none')
print('Second login, legacy migration still required:',', '.join(legacy) or 'none')
