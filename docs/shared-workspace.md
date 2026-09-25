# Shared Workspace

## Implemented design — September 24, 2026

Requested: one shared document/data workspace for the owner and invited partners,
public HTTPS access without Tailscale, simple human UI, agent onboarding with a
service URL and revocable API key, and a dashboard in the existing Grafana.

Deployed on September 24, 2026. Public UI/API, local parsing, gVisor jobs,
central invitations, monitoring and verified local backups are operational.

1. Use Paperless-ngx 3.2.1 as a private document engine: original files, local OCR,
   extracted text, search and document lifecycle. Tika/Gotenberg handle Office
   documents and email files. No mailbox connection or hosted AI processing is
   implied by uploading an email file.
2. Add a small Workspace UI/API over that engine, with structured records linked
   to source documents, revision checks, an audit trail, financial summaries that
   separate currencies, and per-agent API keys.
3. Reuse Authelia, the identities catalog, People invitations, the shared Nginx
   policy compiler, Homarr registration, SSD storage and Prometheus/Grafana.
   All invited workspace users can read/write the entire workspace. Owner-only
   account administration remains separate. API keys cannot create users or keys.
4. Publish only the workspace, its login portal and invitation redemption through
   a named Cloudflare Tunnel. Host VPN/firewall protections remain in force.
   Use first-level public hostnames for Cloudflare Universal SSL coverage.
5. Provide a discovery document, agent guide, API schema and copyable connection
   instructions. Preserve original files; agents add parsed data with provenance.
6. Verify real HTTPS login, invitation boundaries, upload → parse → read → edit,
   key scopes/revocation, script sandbox boundaries, no-auth/spoof denial, dashboard queries, backup restore,
   host VPN and required Mac/server health checks before calling this complete.

## Boundaries

The Paperless engine is private and receives no public traffic directly. The
Workspace API is the authorization boundary for agent keys. Browser identity
comes from the isolated, authenticated reverse proxy and is checked against the
same central service entitlement used for machine requests. One shared content
repository is intentional. Nothing from the owner's existing private document
folders or home-knowledge index is automatically imported or indexed.

Metrics contain aggregate counts and resource usage, never document names,
content, amounts, user identifiers or API keys. Grafana remains owner-only.
Cloudflare terminates public HTTPS and can process traffic in transit; originals
and application databases remain on the home server.

## Decision rationale

Paperless supplies document ingestion/OCR/search instead of reimplementing those
systems. A small companion supplies generic structured records, scoped agent
credentials and analytics. Table-first systems such as Baserow and Directus were
considered; the requested inputs are predominantly original documents and emails.
The REST API is the primary integration contract; MCP is optional and is not
required for an agent that can make authenticated HTTP requests.

Sources: [Paperless API](https://docs.paperless-ngx.com/api/),
[configuration](https://docs.paperless-ngx.com/configuration/),
[permissions](https://docs.paperless-ngx.com/usage/),
[Cloudflare TLS coverage](https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/).

Editable architecture and flow board: [agent discovery & data flow](https://draw.home.egouda.xyz/?board=muggkm91mb1c1gre3qp), 69 persisted elements verified through the authenticated Draw API and opened in the browser. Covers system structure, onboarding, separate browser/API authentication, discovery, upload → parse → sandbox → persist → analytics, and failure boundaries. Existing boards and human edits were preserved. The earlier [overview](https://draw.home.egouda.xyz/?board=mugge7fdbuwqrg9pbrf) remains available.

The owner clarified that parsing and updates must run without human reviews.
Agent scripts run in gVisor with selected inputs only, no network or credentials,
resource limits and bounded JSON output. Agents persist results through the same
versioned record API; financial summaries update immediately.


## Use it now

- Workspace: <https://workspace.egouda.xyz/>
- Owner invitations: <https://people.home.egouda.xyz/?service=workspace>
- Grafana: <https://metrics.home.egouda.xyz/d/shared-workspace>
- Agent entry point: <https://workspace.egouda.xyz/llms.txt>
- Machine discovery: <https://workspace.egouda.xyz/.well-known/agent.json>
- API contract: <https://workspace.egouda.xyz/openapi.json>
- Agent guide: <https://workspace.egouda.xyz/agent-guide.md>

The owner opens **Invite people**, chooses a new username/name and Workspace.
The generated link uses the public Workspace host and expires after 24 hours.
Share that link privately; the invitee creates their own central password and
signs in from any ordinary browser. People administration and Grafana remain
private owner tools. Workspace-only enrollment does not create media or Homarr
accounts or depend on the media application settings.

**Recommended: agent-first setup.** Each person opens **Connect agents**, clicks
**Copy setup message**, and pastes it into the agent they already use. The agent
reads `/llms.txt`, starts a connection, and returns a sign-in link plus a matching
code. The person opens that link, signs in, recognizes the agent name, compares
the code and clicks **Connect this agent**. The agent receives its credential
automatically and confirms it can access the workspace. No API key copying,
terminal command or technical settings are required for this flow.

The confirmation page explains access in plain language. The person can reduce
access to read-only or shorten its lifetime. Credentials expire and can be
revoked under Connected agents. Removing a person's Workspace grant invalidates
their keys and stops their running scripts. The owner can disconnect any agent.
Manual API-key setup is retained inside an advanced details section.

The agent must have HTTP request tools and secure credential storage. A product
limited to web search or prebuilt connectors cannot gain those capabilities from
a prompt; the guide tells it to explain that limitation instead of claiming it
has connected. No proprietary desktop client is required by the service.

The root HTTPS response advertises discovery/OpenAPI/help through `Link` headers,
including its unauthenticated login redirect. `/api/v1/` also returns discovery.
Public discovery contains no user data. The OpenAPI contract has stable operation
IDs, request and response schemas, error descriptions, scopes and a script example.
An agent first reads the guide/schema, then calls `GET /api/v1/me` with its Bearer
key. This is an HTTP REST integration; products limited to MCP still need an MCP
adapter. Uploading `.eml` files does not connect or synchronize a mailbox.

## Data and job lifecycle

`POST /api/v1/documents/upload` accepts one file up to 50 MiB and returns a task
ID plus the uploaded SHA-256. Poll `/tasks/{id}` every three seconds; on `SUCCESS`,
use `related_document` to read the extracted content and original. Workspace
normalizes Paperless 3.2's task format for its own API contract. PDF and email
conversion run locally. OCR accuracy depends on the source; preserve uncertainty.

Records contain a title, kind, optional source document, optional financial fields
and arbitrary JSON `data` up to 200 KB. Financial amounts are decimal strings,
with explicit currency and date. PUT requires the current revision; 409 requires
fetching and reconciling the latest data. Archive/restore is reversible. Audit
history records actors, key IDs and record snapshots. All members share content.

`POST /api/v1/jobs` accepts Python plus up to 10 document IDs and 100 record IDs.
The combined selected original files are limited to 50 MiB. Read
`/inputs/manifest.json` for file paths and records. Originals and extracted text
have separate paths. The host worker runs one job at a time; at most 10 can wait
or run. Python includes pandas, pypdf, openpyxl, Pillow and the standard library.

The pinned gVisor runtime has no network, secrets, Docker socket or writable host
mounts. Inputs are read-only. Limits: 60 seconds, one CPU, 512 MiB RAM, 64 PIDs,
64 MiB temporary storage, 2 MiB JSON stdout and 128 KiB stderr. A failed job is
recorded, not silently rerun. The agent reads its JSON result, validates it and
persists it through the records API; no human review gate intervenes. Metrics and
analytics update automatically. Finished runs discard copied input files while
retaining the script, manifest, result and audit reference.

## Central authentication and public ingress

Only `workspace.egouda.xyz` and `signin.egouda.xyz` are routed through the
`home-shared-workspace` Cloudflare Tunnel. Origin TLS verifies the existing
`auth.home.egouda.xyz` certificate while retaining each public Host header.
The NPM gateway uses the shared `auth_policy.py` compiler. Browser identity needs
both a private proxy secret and the current central entitlement. API paths strip
client-supplied identity/proxy headers and independently validate hashed keys.
Public `/join/` has no owner powers and requires a one-use invitation token;
POST requests must originate from the public Workspace host.

Authelia keeps the existing `home_session` cookie and adds a distinct
`workspace_session` for `egouda.xyz`, with `signin.egouda.xyz` as its login URL.
Cloudflare's Browser Integrity Check is disabled by a hostname-scoped configuration
rule for these two hosts, so ordinary Python/agent HTTP clients can connect.
Authentication and other WAF protections remain enabled. See
[Cloudflare configuration rules](https://developers.cloudflare.com/rules/configuration-rules/create-api/).
Host VPN, fail-closed egress, IPv6 blocking and local/Tailscale exceptions remain.
Maintenance HTTP checks prefer IPv4 because public IPv6 egress is deliberately
blocked on the server. Other home services have no public tunnel route.

## Reproducible deployment

Source lives in `services/workspace`; orchestration is `compose.workspace.yml`
and `compose.workspace-tunnel.yml`. Runtime images have version and digest pins.
Python Linux wheels have exact lockfiles and SHA-256 manifests; wheel binaries
are ignored in Git and can be recreated with `scripts/stage-workspace-wheels.py`.
Both application and sandbox images build with Docker network `none`.

After the repository's credential, VPN and authentication prerequisites:

1. Stage the Linux wheels on the Mac and sync the scoped Workspace sources and
   wheels to the server. Preserve unrelated working changes on both checkouts.
2. On the server run `scripts/prepare-workspace.py`, deploy/validate the central
   auth configuration with `scripts/prepare-auth.py`, then start the Workspace
   Compose stack. Run `scripts/install-workspace-sandbox.py` to install/register
   the pinned gVisor release and enable the host worker. Its optional argument
   accepts the verified release tarball plus adjacent `.sha512` file.
3. Run `scripts/check-download-logins.py --local`, then
   `scripts/configure-workspace.py` to provision the private Paperless identity
   and publish compiled Nginx routes. Restart `home-server-people.service` after
   the People source changes. The internal Paperless identity has document
   read/change/create and task-view permissions, no admin login.
4. On the Mac run `scripts/configure-workspace-tunnel.py`; it backs up prior
   Cloudflare state outside Git, preserves existing configuration rules, checks
   DNS conflicts and publishes only the two explicit hosts. Secrets never print.
5. On the server run `scripts/install-workspace-operations.py`, the checks below,
   then `scripts/sync-service-catalog.py` to reconcile Homarr without moving tiles.
   `scripts/publish-workspace-architecture.py` preserves existing diagram edits
   and appends missing elements with IDs distinct from the overview board.

Persistent data is `/srv/mergerfs/ssd/shared-workspace`: `app`, `paperless`,
`broker` and `jobs`. Private credentials live under
`~/.config/home-server/secrets/workspace`; the web app mounts only its `app`
subdirectory, not the tunnel token or document-engine environment. The worker
and backup script refuse to proceed if the SSD is not mounted. The existing
storage guard discovers container bind mounts. Never print credential files.

## Operations, backups and verification

`home-workspace-worker.service` runs the queue. Independent
`home-workspace-metrics.timer` feeds aggregate metrics into the existing
node-exporter/Prometheus. The 24-panel Grafana dashboard includes API traffic,
errors, latency, document tasks, script outcomes, CPU/RAM, host load, storage,
key counts, telemetry freshness and backup age. Metrics contain no document
names, contents, amounts, user identifiers or credentials.

`home-workspace-backup.timer` runs nightly at 04:20 server local time. It pauses
the worker, stops Workspace and Paperless for a consistent snapshot, saves a
private tar under `~/.local/state/home-server-workspace-backups`, then restarts
them. Restored SQLite databases (including any WAL files) pass integrity checks
before the success metric advances. This causes a brief nightly interruption.
These snapshots include private credentials, are mode 600 and are on the server's
OS disk; they are **not off-server disaster recovery**. Snapshots are retained,
not automatically deleted. Monitor backup storage as the archive grows.

To restore, stop these same writers, preserve the current data outside Git,
restore the selected archive's `data` and `private` trees to their documented
locations with owner UID/GID 1000 and private permissions, then start the stack
and worker and repeat the HTTPS checks. Never extract credentials into the repo.

Verified September 24:

- Real public central login and human document/agent UI; anonymous/spoof rejection.
- Discovery links, `/llms.txt`, schema operation IDs and typed response contracts.
- Text, PDF and `.eml` uploads, local parsing and byte-identical original downloads.
- Read/write key boundaries, immediate analytics updates, revision conflicts,
  selected-input gVisor execution, containment of failures and key revocation.
- Public invitation lookup, invalid/revoked token denial, cross-origin denial;
  existing People one-use redemption regression. No real partner was enrolled.
- Actual Grafana login, 24 panels returning live samples, provisioned alert rules.
- Snapshot restored and both SQLite databases verified.
- Central auth across all registered apps, preserved family permissions and
  existing download-service login checks. Mac `make check-network`: passed.
- Host VPN egress and direct IPv4/IPv6 bypass rejection: passed.
- Agent-first setup: actual browser confirmation → automatic credential delivery
  → authenticated agent identity; cancellation, expiration, scope downgrade,
  anonymous approval denial, poll throttling and concurrent/replayed claims.
  All verification agent credentials were revoked after checking.

Checks: `scripts/check-workspace.py`, `check-workspace-formats.py`,
`check-workspace-onboarding.py`, `check-workspace-connections.py`,
`check-workspace-monitoring.py`, `check-auth.py`,
`check-download-logins.py`, `check-host-vpn.py`, plus the repository make checks.
All synthetic financial verification records were archived and verification API
keys revoked. Synthetic documents and job histories remain clearly named examples.

The first broad server check reported a transient Prowlarr indexer-proxy health
alert. After refreshing its health check, `make check-server` passed with zero
failures. No indexer configuration was changed.

## Authorized Docker space recovery

Selected unreferenced images were exported to private `/home` storage and every
archive member/config checksum verified before Docker copies were removed.
Running and stopped container references were rechecked before each removal;
volumes and application data were preserved. Old rebuildable builder cache was
also reclaimed. `/var` recovered to about 5 GiB free after installing the stack.

Image restoration uses `docker image load -i <archive>/images.tar`. Archives:
`~/.local/state/home-server-maintenance/workspace-image-archive/20260924T215409`
and `20260924T220124` (12 tagged images and 77 old dangling images respectively).
Each archive has its verification manifest. Do not delete these backups as part
of routine setup. Docker's temporary export bind mount was removed afterward.


## Agent connection protocol

This is a small JSON pairing API inspired by the separation of human and device
codes in [RFC 8628](https://www.rfc-editor.org/rfc/rfc8628); it does not advertise
itself as a general OAuth authorization server. The central Authelia login and
workspace entitlement remain the human identity boundary.

- `POST /api/v1/connections`: no existing key; submit recognizable `name`,
  requested `scope` and `days`. Returns private `device_code`, human-visible
  `user_code`, `verification_uri_complete`, a 600-second expiration and five-second
  polling interval. Only hashes of the two codes are stored. The human code goes
  in the sign-in return URL; it cannot claim a credential. The device code never
  goes in a URL or the human UI.
- The invited human uses authenticated, same-origin `/ui-api/connections/{code}`
  to inspect and confirm or cancel. API credentials cannot approve a request.
  Confirmation can only retain or reduce the requested scope/lifetime.
- `POST /api/v1/connections/token`: the agent supplies its private device code.
  Pending returns 202; too-frequent polls return 429; canceled or expired requests
  cannot claim access. After confirmation, one atomic transaction creates the
  existing kind of hashed, scoped API key and marks the request issued. Only one
  competing poll can receive the credential. A lost successful response requires
  starting a fresh connection, not repeatedly retrieving the key.
- The agent stores the returned credential securely and calls `/api/v1/me`.
  Subsequent document operations use the existing key authorization checks.
  This one-time access confirmation creates no review step for parsing or edits.

The public pairing routes have a dedicated Nginx rate limit using the actual
Cloudflare client address, trusted only from the fixed tunnel container. A small
JSON body limit, global request cap, expiry and polling throttle bound setup
state. Expired setup records older than a day are cleared during new requests;
credential and audit lifecycles remain separate.


## Onboarding and human UI follow-up — 24 September 2026

Connect agents shows approved requests immediately as “Waiting for agent to finish
setup,” with an explicit instruction to return to the agent and confirm. It refreshes
every five seconds while visible, without replacing unchanged controls. Failed refreshes
are visible. The list includes only requests owned by the signed-in member (owners
can see all owned requests), never unauthenticated unclaimed requests or code hashes.
Expired/canceled setup attempts remain visible for up to a day after expiry; issued
requests move into Connected agents. Confirmation never claims the agent's secret.

The UI defaults to dark mode; the light/dark switch persists the person's preference.
Analytics is an empty, data-agnostic page awaiting team-defined views. The existing
financial aggregation API remains available for compatibility but does not populate
the human page. Signup uses standard password-manager fields and shared strength
validation; see [People](people.md#password-strength-and-workspace-account-replacement--24-september-2026).

Pairing regression verified approved visibility, secret-free metadata, one-time
issuance, scope restrictions and revocation. Public signup rejected repeated,
sequential, common and name-based weak passwords without consuming the invitation.

On the owner's request, all five existing documents were removed using Paperless's
normal recoverable deletion after a consistent private snapshot. Active document
count was verified as zero; records were preserved. Originals remain in the
server trash and backups. The Draw flow board's pairing and Analytics boxes were
updated, plus a dated signup/security section at the bottom; persisted content
was read back through the Draw API.
