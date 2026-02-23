# Home Server - Docker Media Stack + AI Agents

A complete media server with automated downloading, streaming, and AI agent support via OpenClaw.

**Inspired by:** https://github.com/GreenFrogSB/LMDS

---

## Table of Contents

- [Quick Start](#quick-start)
- [Services Overview](#services-overview)
- [Agents (AI Assistants)](#agents-ai-assistants)
- [Using the Makefile](#using-the-makefile)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Backup & Maintenance](#backup--maintenance)

---

## Quick Start

### Initial Setup

```bash
# 1. Clone and navigate to directory
cd home-server

# 2. Edit server.conf — set SERVER_DATA_DIR to your data path
nano server.conf

# 3. Create required directories
make setup

# 4. Setup VPN (place your vpn.conf in $SERVER_DATA_DIR/vpn/)
make setup-vpn

# 5. Start all services
make start

# 6. Check status
make status
```

### Access Services

```bash
make urls    # Show all service URLs
```

Key services (use `*.lan` URLs after setting DNS — see below):
- **Dashboard**: http://home.lan - Everything at a glance
- **Jellyfin Vue**: http://vue.lan - Media streaming (modern UI)
- **Jellyfin**: http://jellyfin.lan - Media streaming (classic UI)
- **Sonarr**: http://sonarr.lan - TV show management
- **Radarr**: http://radarr.lan - Movie management
- **Portainer**: http://portainer.lan - Docker management

> **DNS Setup:** Set your router's DNS to `192.168.0.124` so all devices resolve `*.lan` URLs automatically. Or manually set DNS per device.

---

## Services Overview

### Media Management
| Service | Port | Purpose |
|---------|------|---------|
| **Sonarr** | 8989 | TV show automation and management |
| **Radarr** | 7878 | Movie automation and management |
| **Bazarr** | 6767 | Subtitle management |

### Media Streaming
| Service | Port | URL | Purpose |
|---------|------|-----|---------|
| **Jellyfin** | 8096 | `jellyfin.lan` | Media streaming server (backend) |
| **Jellyfin Vue** | 8097 | `vue.lan` | Modern web client for Jellyfin |
| **Jellyseerr** | 5055 | `requests.lan` | Request management for Jellyfin |

### Download Clients
| Service | Port | URL | Purpose |
|---------|------|-----|---------|
| **qBittorrent** | 15080 | `torrents.lan` | Torrent client (via VPN) |
| **NZBGet** | 6789 | `nzbget.lan` | Usenet downloader |

### Indexers
| Service | Port | URL | Purpose |
|---------|------|-----|---------|
| **Prowlarr** | 9696 | `prowlarr.lan` | Indexer manager |
| **FlareSolverr** | 8191 | - | Cloudflare bypass |

### Infrastructure
| Service | Port | URL | Purpose |
|---------|------|-----|---------|
| **Nginx Proxy Manager** | 80/443/81 | - | Reverse proxy (clean .lan URLs) |
| **Homepage** | 3000 | `home.lan` | Dashboard with live service stats |
| **Uptime Kuma** | 3001 | `status.lan` | Service monitoring |
| **Watchtower** | - | - | Docker image update notifications |
| **Recyclarr** | - | - | TRaSH Guides quality profile sync |
| **dnsmasq** | 53 | - | Local DNS (*.lan → 192.168.0.124) |
| **VPN Gateway** | - | - | OpenVPN client for qBittorrent |
| **Portainer** | 9000 | `portainer.lan` | Docker container management |

---

## Agents (AI Assistants)

Agents are independent AI assistant instances powered by Claude via [OpenClaw](https://github.com/openclaw/openclaw). Each agent has its own identity, personality, Telegram bot, workspace, and memory — and runs as a systemd user service on the host.

### Architecture

```
Docker (docker-compose.yml)          Host (systemd user services)
┌──────────────────────────┐        ┌──────────────────────────┐
│ sonarr, radarr, jellyfin │        │ openclaw@servo           │
│ qbittorrent, prowlarr    │        │ openclaw@jarvis          │
│ vpn, portainer, ...      │        │ openclaw@<next>          │
└──────────────────────────┘        └──────────────────────────┘
      Media stack                      AI agents (OpenClaw)
```

```
server.conf                     # Path configuration (SERVER_DATA_DIR, etc.)
templates/                      # Git-tracked starter files
  workspace/                    # SOUL.md, AGENTS.md, BOOTSTRAP.md, etc.
  env.template                  # .env skeleton
  openclaw.json                 # Base OpenClaw config
  exec-approvals.json           # Command allowlist
  systemd/openclaw@.service     # Systemd unit template

agents/                         # .gitignored — personal data stays local
  servo/
    .env                        # Agent-specific tokens + port
    workspace/                  # Personality files, memories, tools
  jarvis/
    .env
    workspace/
```

### Creating a New Agent

```bash
# 1. Install OpenClaw on host (one-time)
make install-openclaw

# 2. Scaffold a new agent from templates
make new-agent NAME=jarvis

# 3. Add Telegram bot token (get one from @BotFather)
nano agents/jarvis/.env

# 4. Set your Telegram chat ID in the config
nano $SERVER_DATA_DIR/agents/jarvis/config/openclaw.json  # see server.conf

# 5. Onboard the agent
make agent-setup AGENT=jarvis

# 6. Authenticate with Claude Pro
make agent-auth AGENT=jarvis

# 7. Connect Telegram
make agent-telegram AGENT=jarvis

# 8. Start it
make start-agent AGENT=jarvis
```

On first boot, the agent reads `BOOTSTRAP.md`, starts a conversation with you, discovers its name and personality, and fills in its `IDENTITY.md` and `USER.md`.

### Agent Commands

```bash
# Lifecycle
make new-agent NAME=jarvis       # Create a new agent
make start-agent AGENT=jarvis    # Start an agent
make stop-agent AGENT=jarvis     # Stop an agent
make restart-agent AGENT=jarvis  # Restart an agent
make start-agents                # Start all agents
make stop-agents                 # Stop all agents

# Setup & Auth
make install-openclaw            # Install OpenClaw (one-time)
make update-openclaw             # Update to latest version
make agent-setup AGENT=jarvis    # Run onboarding
make agent-auth AGENT=jarvis     # Login with Claude Pro
make agent-auth-status AGENT=x   # Check auth status
make agent-auth-refresh AGENT=x  # Refresh session
make agent-telegram AGENT=jarvis # Setup Telegram channel

# Monitoring
make list-agents                 # List all agents + status + ports
make agent-logs AGENT=jarvis     # View agent logs (journalctl)
make agent-status AGENT=jarvis   # Detailed systemd status
make backup-agents               # Backup all agent data
```

### Port Allocation

Each agent gets a unique gateway port:

| Agent | Port |
|-------|------|
| servo | 18789 |
| jarvis | 18889 |
| next | 18989 |

### Security

Agents are sandboxed using an exec allowlist (`exec-approvals.json`):

**Allowed:** `docker` (all subcommands), `make`, `git`, `curl`, `wget`, `systemctl`, `journalctl`, `npm`, `npx`, `python3`, plus read-only safeBins (`ls`, `cat`, `df`, `free`, `ps`, `jq`, etc.)

**Blocked:** `rm`, `sudo`, `mkfs`, `dd`, `fdisk`, `chmod`, `chown`, `reboot`, `shutdown`, `iptables`, shell chaining with unallowed binaries

Systemd hardening: `NoNewPrivileges=true`, `ProtectSystem=strict`, `ProtectHome=read-only`, `PrivateTmp=true`

### Privacy

- `agents/` is **gitignored** — personal data, tokens, and memories never leave your machine
- `templates/` is **git-tracked** — safe generic starter files
- Root `.env` holds only `ANTHROPIC_API_KEY` (shared across all agents)
- Each agent's `.env` holds its own `TELEGRAM_BOT_TOKEN` and `OPENCLAW_GATEWAY_TOKEN`
- Agent state lives in `$SERVER_DATA_DIR/agents/<name>/config/` (see `server.conf`)

### Customizing an Agent

Before first boot, edit the workspace files in `agents/<name>/workspace/`:

- **SOUL.md** — Core personality and values
- **AGENTS.md** — Operational behavior and memory rules
- **BOOTSTRAP.md** — First-run onboarding script (deleted after use)
- **TOOLS.md** — Environment-specific notes (APIs, paths, safety rules)
- **HEARTBEAT.md** — Periodic task checklist

After onboarding, the agent maintains:
- **IDENTITY.md** — Name, creature type, vibe, emoji
- **USER.md** — Info about its human
- **MEMORY.md** — Long-term curated memory
- **memory/** — Daily logs

---

## Using the Makefile

The Makefile provides convenient commands for managing your entire server. Run `make help` for the full list.

### Basic Commands

```bash
make help              # Show all available commands
make status            # Show status of all services + agents
make start             # Start all services (Docker infra + agents)
make stop              # Stop all services
make restart           # Restart all services
make logs              # View logs (all services)
make logs SERVICE=sonarr  # View specific service logs
```

### Service Groups

```bash
make start-media       # Start Sonarr, Radarr, Jellyfin
make start-downloaders # Start qBittorrent, NZBGet
make start-indexers    # Start Prowlarr, Jackett
make start-agents      # Start all AI agents
```

### Individual Services

```bash
make restart SERVICE=sonarr  # Restart specific service
make update SERVICE=radarr   # Update and restart service
make sonarr-logs             # View Sonarr logs
make radarr-restart          # Restart Radarr
```

### Maintenance

```bash
make update            # Update all services
make backup            # Backup all configurations
make backup-agents     # Backup all agent data
make stats             # Show resource usage
make health            # Check container health
make vpn-check         # Verify VPN connection
make disk-usage        # Show disk usage
```

---

## Configuration

### Directory Structure

```
home-server/
├── server.conf                     # Path configuration (SERVER_DATA_DIR)
├── docker-compose.yml              # Media stack services (Docker)
├── .env                            # Shared secrets (ANTHROPIC_API_KEY)
├── Makefile                        # All management commands
├── templates/
│   ├── workspace/                  # Starter personality files
│   ├── env.template                # Agent .env skeleton
│   ├── openclaw.json               # Base OpenClaw config
│   ├── exec-approvals.json         # Command allowlist
│   └── systemd/openclaw@.service   # Systemd unit template
├── agents/                         # Per-agent config + workspace (gitignored)
│   └── servo/
│       ├── .env                    # Agent tokens + port
│       └── workspace/              # Personality, memory, tools
└── scripts/
    ├── setup-host.sh               # First-time host setup
    ├── new-agent.sh                # Scaffold a new agent
    └── agent-ctl.sh                # Agent CLI wrapper

$SERVER_DATA_DIR/                   # Configured in server.conf (default: /mnt/server)
├── agents/
│   └── servo/config/               # Agent state (credentials, sessions, openclaw.json)
├── media/                          # Media library
├── downloads/                      # Download client output
└── [service]/                      # Other service configs
```

### VPN Setup

1. Get VPN config file from your provider
2. Place at: `$SERVER_DATA_DIR/vpn/vpn.conf`
3. Restart VPN container: `make restart SERVICE=vpn`

See: https://greenfrognest.com/LMDSVPN.php#vpncontainer

### Environment Variables

**Root `.env`** (shared across all agents):
```env
# Anthropic authentication (choose one):
# Option 1: Claude Pro account (leave empty, use: make agent-auth AGENT=name)
# Option 2: API key
ANTHROPIC_API_KEY=
```

**Agent `.env`** (`agents/<name>/.env`):
```env
OPENCLAW_GATEWAY_TOKEN=<auto-generated>
TELEGRAM_BOT_TOKEN=<from @BotFather>
OPENCLAW_PORT=18789
OPENCLAW_STATE_DIR=$SERVER_DATA_DIR/agents/<name>/config
```

### Authentication

| Method | Cost | Setup | Best For |
|--------|------|-------|----------|
| **Claude Pro/Max** | $20-100/month (existing sub) | `make agent-auth AGENT=name` | Personal use |
| **API Key** | Pay-per-token | Add to root `.env` | High volume |

OpenClaw works with Claude Pro/Max via OAuth — no API key needed for personal use.

---

## Troubleshooting

### General Issues

**Service won't start:**
```bash
make logs SERVICE=servicename
sudo netstat -tlnp | grep PORT
make restart SERVICE=servicename
```

**All services down:**
```bash
sudo systemctl restart docker
make start
```

### VPN Issues

```bash
make vpn-check          # Should show VPN IP, not your real IP
make logs SERVICE=vpn   # Check VPN logs
make restart SERVICE=vpn
```

### Agent Issues

**Agent won't start:**
```bash
make agent-logs AGENT=name        # Check journalctl logs
make agent-status AGENT=name      # Detailed systemd status
make agent-auth-status AGENT=name # Check auth
```

**Telegram not connecting:**
```bash
# Verify token is set
grep TELEGRAM_BOT_TOKEN agents/<name>/.env

# Re-add channel
make agent-telegram AGENT=name
```

**Claude Pro auth expired:**
```bash
make agent-auth-status AGENT=name
make agent-auth-refresh AGENT=name   # Try refresh first
make agent-auth AGENT=name           # Full re-login if needed
```

**Bot not responding to messages:**
```bash
# Check allowlist in agent config (path from server.conf)
cat $SERVER_DATA_DIR/agents/<name>/config/openclaw.json | grep allowFrom

# Check logs
make agent-logs AGENT=name

# Restart
make restart-agent AGENT=name
```

### Permission Errors

```bash
# Fix ownership (services use PUID=1000)
sudo chown -R 1000:1000 $SERVER_DATA_DIR/agents/<name>/

# Fix agent config permissions
chmod 700 $SERVER_DATA_DIR/agents/<name>/config
chmod 600 $SERVER_DATA_DIR/agents/<name>/config/openclaw.json
```

---

## Backup & Maintenance

### Backups

```bash
make backup            # Backup all service configs
make backup-agents     # Backup all agent data + workspaces
```

Backups are stored in `backups/` directory.

### Monitoring

```bash
make stats             # Resource usage
make health            # Container health
make disk-usage        # Show disk usage
make vpn-check         # Check VPN connection
make dashboard         # Quick overview
```

### Cleanup

```bash
make prune             # Remove unused Docker resources
make clean-logs        # Clean Docker logs
make clean             # Stop and remove everything (DESTRUCTIVE)
```

### Updates

```bash
make update                    # Update all service images
make update SERVICE=sonarr     # Update specific service
make update-openclaw           # Update OpenClaw to latest
```

---

## Quick Reference

```bash
# Infrastructure
make start                       # Start everything
make stop                        # Stop everything
make status                      # Service status (Docker + agents)
make urls                        # All service URLs

# Agents
make install-openclaw            # Install OpenClaw (one-time)
make new-agent NAME=jarvis       # Create agent
make start-agent AGENT=jarvis    # Start agent
make stop-agent AGENT=jarvis     # Stop agent
make list-agents                 # List all agents
make agent-logs AGENT=jarvis     # View logs

# Maintenance
make update                      # Update services
make backup                      # Backup configs
make backup-agents               # Backup agents
make health                      # Health check
```

---

## Network Architecture

- **proxy network** (172.18.0.0/24) — All Docker services communicate here
- **VPN gateway** — qBittorrent traffic routed through VPN
- **Agent loopback** — Agent gateway UIs only accessible via 127.0.0.1
- **Localhost binding** — SSH tunnel required for remote access

---

## Security Notes

- qBittorrent bound to VPN (traffic stops if VPN disconnects)
- Agent UIs only on localhost (SSH tunnel required for remote)
- All Docker services use non-root users (PUID/PGID)
- Agent secrets in per-agent `.env` files (gitignored)
- Root `.env` excluded from version control
- Agents run with systemd hardening (NoNewPrivileges, ProtectSystem, ProtectHome)
- Agent exec sandboxed via allowlist — only approved binaries can run
- Media directories accessible but destructive commands blocked

---

## Reproducibility

Clone the repo and go:

```bash
git clone <repo-url> && cd home-server
make install-openclaw              # Install OpenClaw on host
make setup                         # Create directories
make new-agent NAME=servo          # Scaffold an agent
# Edit agents/servo/.env with TELEGRAM_BOT_TOKEN
# Edit $SERVER_DATA_DIR/agents/servo/config/openclaw.json with TELEGRAM_CHAT_ID
make agent-setup AGENT=servo       # Onboard
make agent-auth AGENT=servo        # Login with Claude Pro
make agent-telegram AGENT=servo    # Connect Telegram
make start                         # Start everything
```

---

## Resources

- **Docker Compose**: https://docs.docker.com/compose/
- **Sonarr**: https://wiki.servarr.com/sonarr
- **Radarr**: https://wiki.servarr.com/radarr
- **Jellyfin**: https://jellyfin.org/docs/
- **Jellyfin Vue**: https://github.com/jellyfin/jellyfin-vue
- **Prowlarr**: https://wiki.servarr.com/prowlarr
- **OpenClaw**: https://github.com/openclaw/openclaw
