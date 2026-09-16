# 1Password integration for agents

Read this before authenticated maintenance. This is the repo's supported
integration with the installed official **1Password CLI + desktop app**.
It requires the owner's desktop authorization and has no unattended broad vault token.

## Commands on the Mac

```sh
python3 scripts/vault.py status
python3 scripts/vault.py verify metrics
python3 scripts/vault.py exec metrics -- python3 scripts/check-metrics-from-vault.py
```

`config/1password/catalog.json` contains only stable `op://` references and metadata.
`config/1password/<service>.refs` contains references, never resolved values.
`vault.py exec` runs official `op run`, injecting only the selected service's
username/password into the child process and preserving CLI output masking.
Scripts read `HOME_SERVICE_USERNAME` and `HOME_SERVICE_PASSWORD`; they must not
print them, include them in URLs/arguments, dump environments, or emit HTTP bodies
that contain tokens. Masking does not replace careful script design.

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
with one password-manager-compatible portal. It is prepared but not yet enabled.
Use the `auth` vault item for that portal once saved/read-verified; keep existing
app-specific items for native forms and recovery until their identity adapters are
actually migrated. Never mark a native app as SSO just because it has a gateway.
