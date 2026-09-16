"""Reproducible private OIDC configuration; secrets never enter the repository."""
import hashlib
import json
import secrets
import subprocess


def configure(config, private):
    path=private/'oidc.json'
    if not path.exists():
        result=subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072'],capture_output=True,text=True,check=True)
        path.write_text(json.dumps({'hmac':secrets.token_urlsafe(64),'key':result.stdout,'clients':{}}))
        path.chmod(0o600)
    data=json.loads(path.read_text())
    clients=[]
    for name,callback,policy in [('homarr','https://home.egouda.xyz/api/auth/callback/oidc','household'), ('metrics','https://metrics.home.egouda.xyz/login/generic_oauth','owner'), ('jellyfin','https://jellyfin.home.egouda.xyz/sso/OID/redirect/authelia','household')]:
        if name not in data['clients']:
            data['clients'][name]={'id':secrets.token_urlsafe(48),'secret':secrets.token_urlsafe(48)}
        credential=data['clients'][name]
        if 'digest' not in credential:
            import importlib.util
            spec=importlib.util.spec_from_file_location('prepare_auth',__import__('pathlib').Path(__file__).with_name('prepare-auth.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            credential['digest']=module.pbkdf2(credential['secret'])
        clients.append({'client_id':credential['id'],'client_name':name.title(),'client_secret':credential['digest'],
            'public':False,'claims_policy':'home_identity','authorization_policy':name,'consent_mode':'implicit',
            'redirect_uris':[callback],'scopes':['openid','profile','email','groups'],
            'response_types':['code'],'grant_types':['authorization_code'],
            'require_pkce':True,'pkce_challenge_method':'S256','token_endpoint_auth_method':'client_secret_post' if name=='jellyfin' else 'client_secret_basic'})
    path.write_text(json.dumps(data))
    config['identity_providers']={'oidc':{'hmac_secret':data['hmac'],
        'jwks':[{'key_id':'home-2026','algorithm':'RS256','use':'sig','key':data['key']}],
        'authorization_policies':{name:{'default_policy':'deny','rules':[{'policy':'one_factor','subject':['group:owners','group:service:'+name]}]} for name in [client['client_name'].lower() for client in clients]},
        'claims_policies':{'home_identity':{'id_token':['email','email_verified','preferred_username','name','groups']}},
        'clients':clients}}
    env=private/'homarr-oidc.env'
    env.write_text('\n'.join([
        'AUTH_PROVIDERS=oidc',
        'AUTH_OIDC_ISSUER=https://auth.home.egouda.xyz',
        'AUTH_OIDC_CLIENT_ID='+data['clients']['homarr']['id'],
        'AUTH_OIDC_CLIENT_SECRET='+data['clients']['homarr']['secret'],
        'AUTH_OIDC_CLIENT_NAME=Home',
        'AUTH_OIDC_AUTO_LOGIN=true',
        'AUTH_OIDC_FORCE_USERINFO=true',
        'AUTH_OIDC_ENABLE_DANGEROUS_CREDENTIALS_LINKING=false',
        'AUTH_OIDC_SCOPE_OVERWRITE=openid email profile groups',
        'AUTH_OIDC_GROUPS_ATTRIBUTE=groups',
        'AUTH_LOGOUT_REDIRECT_URL=https://auth.home.egouda.xyz/logout',
        'AUTH_SESSION_EXPIRY_TIME=12h','']))
    env.chmod(0o600)

    grafana=private/'grafana-oidc.env'
    grafana.write_text('\n'.join([
        'GF_AUTH_GENERIC_OAUTH_ENABLED=true',
        'GF_AUTH_OAUTH_ALLOW_INSECURE_EMAIL_LOOKUP=false',
        'GF_AUTH_GENERIC_OAUTH_NAME=Home',
        'GF_AUTH_GENERIC_OAUTH_AUTO_LOGIN=true',
        'GF_AUTH_GENERIC_OAUTH_ALLOW_SIGN_UP=true',
        'GF_AUTH_GENERIC_OAUTH_CLIENT_ID='+data['clients']['metrics']['id'],
        'GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET='+data['clients']['metrics']['secret'],
        'GF_AUTH_GENERIC_OAUTH_SCOPES=openid profile email groups',
        'GF_AUTH_GENERIC_OAUTH_AUTH_URL=https://auth.home.egouda.xyz/api/oidc/authorization',
        'GF_AUTH_GENERIC_OAUTH_TOKEN_URL=https://auth.home.egouda.xyz/api/oidc/token',
        'GF_AUTH_GENERIC_OAUTH_API_URL=https://auth.home.egouda.xyz/api/oidc/userinfo',
        'GF_AUTH_GENERIC_OAUTH_LOGIN_ATTRIBUTE_PATH=preferred_username',
        'GF_AUTH_GENERIC_OAUTH_GROUPS_ATTRIBUTE_PATH=groups',
        "GF_AUTH_GENERIC_OAUTH_ROLE_ATTRIBUTE_PATH=contains(groups[*], 'owners') && 'GrafanaAdmin' || 'Viewer'",
        'GF_AUTH_GENERIC_OAUTH_ALLOW_ASSIGN_GRAFANA_ADMIN=true',
        'GF_AUTH_GENERIC_OAUTH_USE_PKCE=true',
        'GF_AUTH_SIGNOUT_REDIRECT_URL=https://auth.home.egouda.xyz/logout','']))
    grafana.chmod(0o600)
