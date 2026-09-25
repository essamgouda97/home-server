#!/usr/bin/env python3
"""Add a dated, editable Workspace board; preserve all existing human edits."""
import importlib.util
from pathlib import Path
p=Path(__file__).with_name('publish-home-server-lifecycle-board.py')
spec=importlib.util.spec_from_file_location('lifecycle_board',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.TITLE='Shared Workspace — agent discovery & data flow — 24 Sep 2026'
m.PREFIX='shared-workspace-flow-'
m.APPEND_TO_EXISTING=True
def design():
    return [m.heading('Shared Workspace · public collaboration',0,0,36),
      m.heading('Deployed state and verification: 24 September 2026. One shared repository for explicitly invited members.',0,65,18),
      m.box('client','Partners + agents\nOrdinary public HTTPS\nBrowser central account\nAgent: URL + per-agent key',0,145,400,170,m.BLUE),
      m.box('edge','Cloudflare Tunnel\nOnly workspace + signin hosts\nTLS at public edge, verified origin\nOther home apps stay private',450,145,440,170,m.GREEN),
      m.box('auth','Shared authentication\nAuthelia + identity catalog\nPeople single-use invitations\nWorkspace grant required',940,145,440,170,m.VIOLET),
      m.box('app','Workspace UI + API\nDocuments / Records / Analytics\nHashed, scoped, expiring API keys\nAudit + revision conflict checks',1430,145,480,170,m.GREEN),
      m.arrow('client','edge'),m.arrow('edge','auth'),m.arrow('auth','app'),
      m.box('documents','Private Paperless engine\nLocal OCR / text extraction\nTika + Gotenberg conversion\nOriginal files retained',0,400,440,185,m.BLUE),
      m.box('storage','SSD persistent data\nPaperless SQLite + originals\nWorkspace SQLite records/audit\nSnapshots outside Git on OS disk',490,400,440,185,m.GREEN),
      m.box('worker','Host job worker\nNo Docker socket in the web app\nOnly selected inputs per run\nOne run at a time',980,400,440,185,m.VIOLET),
      m.box('sandbox','gVisor Python sandbox\nNo network / secrets / host writes\nRead-only inputs + bounded JSON\n60s / 1 CPU / 512 MiB / 64 PIDs',1470,400,440,185,m.AMBER),
      m.arrow('app','documents'),m.arrow('documents','storage'),m.arrow('app','storage'),m.arrow('app','worker'),m.arrow('worker','sandbox'),
      m.box('results','Automatic data workflow\nAgent uploads → OCR → sandbox parse\nAgent saves results through API\nAnalytics update without human review',0,700,580,180,m.GREEN),
      m.box('metrics','Existing Prometheus + Grafana\n24-panel owner dashboard\nAPI / jobs / storage / CPU / RAM\nNo document names or content in metrics',640,700,600,180,m.BLUE),
      m.box('boundaries','Data / auth boundaries\nEvery member can read/write shared content\nNo import from private home-knowledge\nHost VPN + fail-closed egress preserved',1300,700,610,180,m.AMBER),
      m.arrow('sandbox','results'),m.arrow('app','metrics'),
      m.heading('Rationale: reuse mature document parsing and central identity/monitoring; add a small records and agent API layer.',0,950,18),
      m.heading('Sources: docs/shared-workspace.md · compose.workspace.yml · config/services.json · scripts/workspace-worker.py',0,990,18),
      m.heading('1 · Onboard a person, then an agent',0,1100,30),
      m.box('invite','Owner: Invite people\nPrivate People console\nChoose Workspace only\n24-hour single-use public link',0,1190,440,175,m.VIOLET),
      m.box('join','Partner: public /join/\nCreate personal central password\nAuthelia + workspace entitlement\nNo Tailscale or client install',490,1190,440,175,m.VIOLET),
      m.box('key','Partner: paste setup message\nAgent reads /llms.txt\nPOST /api/v1/connections\nReturns link + matching code',980,1190,440,175,m.GREEN,18),
      m.box('agentconfig','Partner: Connect this agent\nCentral login + name/code check\nAgent polls /connections/token\nCredential delivered to the agent',1470,1190,440,175,m.GREEN,18),
      m.arrow('invite','join'),m.arrow('join','key'),m.arrow('key','agentconfig'),
      m.heading('2 · Public discovery, authenticated operations',0,1450,30),
      m.box('discover','GET service URL\nHTTP Link headers → /llms.txt\n/.well-known/agent.json\nNo credential needed for discovery',0,1540,440,190,m.BLUE),
      m.box('contract','Read /openapi.json\nStable operation IDs + schemas\n/agent-guide.md explains workflow\nREST HTTP; no MCP dependency',490,1540,440,190,m.BLUE),
      m.box('apigateway','GET /api/v1/me\nPublic tunnel → API boundary\nHash, expiry, revocation, scope\nCheck central entitlement each time',980,1540,440,190,m.GREEN),
      m.box('authsplit','Two authentication paths\nBrowser: Authelia → trusted identity\nAgent: Workspace validates API key\nAPI requests need no browser cookie',1470,1540,440,190,m.AMBER),
      m.arrow('discover','contract'),m.arrow('contract','apigateway'),m.arrow('agentconfig','apigateway'),
      m.heading('3 · Upload → parse → persist → analyze (fully agent-operated)',0,1820,30),
      m.box('uploadflow','POST /documents/upload\nAuthorized original, max 50 MiB\nReturns 202 + task ID + SHA-256\nOriginal saved in private Paperless',0,1910,440,195,m.BLUE),
      m.box('taskflow','GET /tasks/{id}\nPoll until SUCCESS or FAILURE\nSUCCESS → related_document ID\nRead text + download original',490,1910,440,195,m.BLUE),
      m.box('jobflow','POST /jobs\nPython + explicit input IDs\nWorker → isolated gVisor run\nGET /jobs/{id} → JSON result',980,1910,440,195,m.VIOLET),
      m.box('saveflow','POST /records or PUT /records/{id}\nAgent validates and persists result\nSource document + parser provenance\nNo human review gate',1470,1910,440,195,m.GREEN,18),
      m.arrow('uploadflow','taskflow'),m.arrow('taskflow','jobflow'),m.arrow('jobflow','saveflow'),
      m.box('conflicts','Concurrent edits\nPUT includes current revision\n409 → fetch + reconcile + retry\nArchive/restore preserves history',0,2210,440,180,m.AMBER),
      m.box('analyticsflow','Analytics UI: team-defined views\nData-agnostic placeholder for now\nCharts populated later by the team\nExisting financial API retained',490,2210,440,180,m.GREEN),
      m.box('operationalflow','Aggregate telemetry only\nApp + host + containers → Prometheus\nExisting Grafana, 24 panels\nNightly verified local snapshots',980,2210,440,180,m.BLUE,18),
      m.box('failureflow','Failure and trust boundaries\n401: key/grant invalid; 403: scope\n429: throttle; failed jobs stay failed\nDocuments and script output are data',1470,2210,440,180,m.AMBER,18),
      m.arrow('saveflow','analyticsflow'),m.arrow('saveflow','conflicts'),m.arrow('jobflow','operationalflow'),
      m.heading('Public base: https://workspace.egouda.xyz · /api/v1 prefixes all operation paths shown above.',0,2490,20),
      m.heading('Discovery is public; content is authenticated. Sandboxes cannot write databases directly: agents explicitly save JSON results through the API.',0,2540,18),
      m.heading('4 · Agent-first setup for nontechnical people — deployed 24 September',0,2670,30),
      m.box('pair-start','1. Paste one message into the agent\nConnect agents page → Copy setup message\nNo API settings or key copying\nAgent discovers its own setup protocol',0,2760,600,190,m.GREEN,18),
      m.box('pair-request','2. Agent requests a connection\nPOST /api/v1/connections (no key needed)\nPrivate device_code stays with the agent\nHuman gets only a link + matching code',655,2760,600,190,m.BLUE,18),
      m.box('pair-confirm','3. Person opens the agent’s link\nCentral sign-in; invited members only\nRecognize agent name + compare code\nChoose access → Connect this agent',1310,2760,600,190,m.VIOLET,18),
      m.arrow('pair-start','pair-request'),m.arrow('pair-request','pair-confirm'),
      m.box('pair-token','4. Return and confirm to the agent\nAgent polls /connections/token every 5s\nUI shows waiting / expired / connected\nSuccess → credential delivered once',0,3050,600,190,m.BLUE,18),
      m.box('pair-ready','5. Ready to work\nAgent stores credential securely\nGET /api/v1/me confirms identity\nPerson asks for uploads, parsing or analysis',655,3050,600,190,m.GREEN,18),
      m.box('pair-boundary','Access confirmation, not data review\nSetup expires after 10 minutes\nScoped, expiring, revocable credentials\nFuture parsing and updates need no review',1310,3050,600,190,m.AMBER,18),
      m.arrow('pair-token','pair-ready'),
      m.heading('Manual API keys remain an advanced fallback. Browser-only/search-only agents may need their application’s connector support.',0,3330,18),
      m.box('onboarding-hardening','Deployed follow-up · 24 September 2026\nSignup: standard username + new-password fields; local zxcvbn score 4, 16–72 characters; no passwords sent externally.\nAccount replacement: private backup → revoke identity, sessions, agent keys and invites → fresh one-use invitation. Shared data preserved.\nUI: dark by default; waiting-agent status refreshes every 5s. Analytics awaits team-defined, data-agnostic views.',0,3470,1910,180,m.BLUE,20),
      m.box('groups-expiry','Shared groups + credential expiry notices · deployed 24 September 2026\nUI and agent /groups API → existing Paperless tags: create, rename, add/remove documents, filter by group_id. Multiple groups; one original.\nWrite scope + audit required for mutations. Groups organize shared content; they do not change access. One app worker serializes membership edits.\nAll pages show in-app key warnings 7 days before expiry and recently expired keys. Reconnect through approved pairing; keys never auto-extend.',0,3730,1910,180,m.GREEN,20),
      m.box('query-limits','Bounded document reads · deployed 24 September 2026\nMetadata-only document lists; explicit document/group pages of 1–30 items (page 1–1000). Plain search: 200 characters / 12 words; no wildcards.\nTwo reads at once; 60/minute per user across API keys + browser. Fail-fast 429; 10s deadline; 1 MiB lists / 8 MiB document JSON.\nTimeout → 30s global cooldown: client cancellation cannot guarantee upstream cancellation. Workspace 1 CPU / 384 MiB; Paperless 2 CPU / 2 GiB.\nUI replaces pages, cancels stale searches, and retains the current page on failure. Isolated synthetic pagination, capacity and recovery checks passed.',0,3990,1910,190,m.AMBER,20)]
def persisted_design():
    # The initial two headings were saved before Draw rejected IDs reused from
    # the overview board. Preserve those headings and append distinct elements.
    elements=design()[2:]
    for index,element in enumerate(elements):
        element.setdefault('id',m.PREFIX+'element-'+str(index))
    return elements
m.design=persisted_design
if __name__=='__main__':m.main()
