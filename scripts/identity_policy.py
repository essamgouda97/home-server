"""Non-secret household entitlements shared by IdP, dashboards and provisioning."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def identities():
    data=json.loads((ROOT/'config/identities.json').read_text())['users']
    services={x['id'] for x in json.loads((ROOT/'config/services.json').read_text())['services'] if x['auth']['access']=='household'}
    for name,entry in data.items():
        assert name.isalnum() and name.islower(),'Invalid username'
        assert isinstance(entry['owner'],bool)
        assert (entry['owner'] and entry['services']==['*']) or (not entry['owner'] and set(entry['services'])<=services),'Invalid service grant'
    return data

def groups(username):
    user=identities()[username]
    return ['owners','household'] if user['owner'] else ['household']+['service:'+s for s in user['services']]

def allowed(username,service):
    u=identities()[username]
    return u['owner'] or service in u['services']

def subjects(service):
    return ['group:owners','group:service:'+service]
