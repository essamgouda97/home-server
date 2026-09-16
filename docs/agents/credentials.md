# 1Password integration for agents

Read this before authenticated maintenance. This is the repo's supported
integration with the installed official **1Password CLI + desktop app**.
It requires the owner's desktop authorization and has no unattended broad vault token.

## Commands on the Mac

```sh
python3 scripts/vault.py status
python3 scripts/vault.py verify metrics
python3 scripts/vault.py --with-gateway exec metrics -- python3 scripts/check-metrics-from-vault.py
```

`config/1password/catalog.json` contains only stable `op://` references and metadata.
`config/1password/<service>.refs` contains references, never resolved values.
`vault.py exec` runs official `op run`, injecting only the selected service's
username/password into the child process and preserving CLI output masking.
Scripts read `HOME_SERVICE_USERNAME` and `HOME_SERVICE_PASSWORD`; they must not
print them, include them in URLs/arguments, dump environments, or emit HTTP bodies
that contain tokens. Masking does not replace careful script design.

`--with-gateway` additionally injects `HOME_AUTH_USERNAME` and `HOME_AUTH_PASSWORD`
from the central login reference for apps behind the gateway. This is an explicit
two-credential grant, not access to every application's secret.

The helper narrows the secrets supplied to each child process; it is **not** a
vault-level permission boundary. The desktop-authorized account can access other
permitted vaults through the CLI. Do not browse unrelated items. No service-account
API token was created, and no employer shared vault is used. The owner expressly
authorized this account's Employee/PERSONAL vault for home-server use.

## New credentials and rotation

Follow [the save/read-verify/apply/test sequence](../security-hardening.md#save-before-changing-an-app).
`prepare-security-credentials.py --service NAME --url HTTPS_URL` creates or reuses
only the tagged item, reads it back and stages it privately over SSH stdin.
It also updates the reference catalog and `.refs` file using the
**non-secret item ID**. Never copy the secret itself into the repo or model conversation.
Account/vault labels and references may be versioned; recovery codes must not be.

Keep current family accounts and API integrations working. Save/verify the vault
item **before** changing an app. Test a real HTTPS login, then update the runtime
credential file and dependent consumers. Do not revert migrated services to the
legacy shared password. Add every browser-facing app to the service catalog.

Desktop access is for interactive agents on the Mac. The home server runs from
private, mode-restricted deployment secret files so a locked/offline Mac does not
stop services. A deployment secret is not a second user-managed password: it must
match the vault. Back up both state and configuration before rotating encryption keys.

## Native agentic browser integration

1Password's **Agentic Autofill/Agentic Mode** can approve browser credentials without
showing their values to supported agents. Its documented native Claude/browser
integration is distinct from this CLI workflow. This repository does not install
an unofficial credential-reading MCP server or claim native Codex support that
has not been verified. If the active browser offers the supported 1Password
approval flow, prefer it for browser sign-in; never inspect browser password stores.

Official references:

- [CLI desktop integration](https://developer.1password.com/docs/cli/app-integration/)
- [Secret references and process injection](https://www.1password.dev/cli/secrets-environment-variables)
- [1Password agentic access](https://1password.com/solutions/agentic-ai)

## Shared browser sign-in

The [central auth standard](../authentication.md) replaces proxy Basic dialogs
with one password-manager-compatible portal. It is live across all registered HTTPS browser apps.
Use the saved/read-verified `auth` vault item for that portal; keep existing
app-specific items for native forms and recovery until their identity adapters are
actually migrated. Never mark a native app as SSO just because it has a gateway.

## Unattended agent access (prepared, not activated)

The owner requested fewer authorization prompts on September 16. Official
1Password service accounts support this, with read-only access to a dedicated
**Home Server Agents** vault. Creation returned HTTP 403 with the current work
account. No vault or service account was created, and no work-account permissions
were changed. Service accounts cannot access the built-in Employee vault.

An account administrator must grant permission to create the dedicated vault and
service account, or provision them. Do not copy owner logins, recovery codes,
Cloudflare root credentials, or unrelated employer items into this vault.
Populate it with dedicated per-service API tokens: monitoring read-only by default;
request/download changes only for agents assigned those operations. An app with
only an administrator API key must be labeled explicitly as administrative.
Do not bypass the browser gateway based on a header's presence; use the private
network and each application's real API authentication, or a validated machine
identity endpoint.

Prepared command contract (currently fails closed):

```sh
python3 scripts/vault.py --agent status
python3 scripts/vault.py --agent verify SERVICE
python3 scripts/vault.py --agent exec SERVICE -- python3 scripts/APP_CHECK.py
```

After provisioning, record only vault/item IDs in `config/1password/agents.json`
and `config/1password/agents/SERVICE.refs`; API references use
`HOME_SERVICE_API_TOKEN=op://VAULT/ITEM/FIELD`. Enable the catalog only after a
positive read test and a negative test proving Employee access is denied.
Supply `OP_SERVICE_ACCOUNT_TOKEN` from an OS credential store or protected job
secret mechanism. Never put it in `.zshrc`, Git, shell arguments or chat. Save the
bootstrap token in the owner's vault for recovery; choose a finite expiry and
record renewal ownership. This setup does not require a new daemon or unofficial MCP.

The child launcher removes all `OP_*` variables before starting the workload.
`op run` retains its default output masking. This reduces accidental disclosure;
it is not a sandbox against an agent with unrestricted access to the host.
Never dump environment variables or log authenticated response bodies. Agents
must not receive personal browser sessions as a substitute for an API identity.
Use separate read-only and administrative vaults/tokens when those agent roles
must be isolated: a service account's vault permissions are the real boundary.

Routine reads use the scoped token without desktop prompts. Initial provisioning,
renewal/revocation, new privilege grants and personal MFA remain human-controlled.
Service-account creation permissions are immutable; replace the account to change
its scope. Existing interactive desktop commands remain available explicitly;
agent mode never silently falls back to broader desktop authorization.

Reference: [official service-account requirements and limitations](https://www.1password.dev/service-accounts/get-started).
