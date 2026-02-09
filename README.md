# Home Server - Docker Media Stack

A complete media server with automated downloading, streaming, and AI assistant integration.

**Inspired by:** https://github.com/GreenFrogSB/LMDS

---

## Table of Contents

- [Quick Start](#quick-start)
- [Services Overview](#services-overview)
- [Using the Makefile](#using-the-makefile)
- [Moltbot AI Assistant](#moltbot-ai-assistant)
- [Service Management](#service-management)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Backup & Maintenance](#backup--maintenance)

---

## Quick Start

### Initial Setup

```bash
# 1. Clone and navigate to directory
cd /home/egouda/workspace/home-server

# 2. Create required directories
make setup-dirs

# 3. Setup VPN (place your vpn.conf in /mnt/server/vpn/)
make setup-vpn

# 4. Start all services
make start

# 5. Check status
make status
```

### Access Services

```bash
# Show all service URLs
make urls
```

Key services:
- **Jellyfin**: http://localhost:8096 - Media streaming
- **Sonarr**: http://localhost:8989 - TV show management
- **Radarr**: http://localhost:7878 - Movie management
- **Portainer**: http://localhost:9000 - Docker management

---

## Services Overview

### Media Management
| Service | Port | Purpose |
|---------|------|---------|
| **Sonarr** | 8989 | TV show automation and management |
| **Radarr** | 7878 | Movie automation and management |
| **Bazarr** | 6767 | Subtitle management |

### Media Streaming
| Service | Port | Purpose |
|---------|------|---------|
| **Jellyfin** | 8096 | Media streaming server |
| **Jellyseerr** | 5055 | Request management for Jellyfin |

### Download Clients
| Service | Port | Purpose |
|---------|------|---------|
| **qBittorrent** | 15080 | Torrent client (via VPN) |
| **NZBGet** | 6789 | Usenet downloader |

### Indexers
| Service | Port | Purpose |
|---------|------|---------|
| **Prowlarr** | 9696 | Indexer manager |
| **Jackett** | 9117 | Torrent indexer proxy |
| **FlareSolverr** | 8191 | Cloudflare bypass |

### Infrastructure
| Service | Port | Purpose |
|---------|------|---------|
| **VPN Gateway** | - | OpenVPN client for qBittorrent |
| **Portainer** | 9000 | Docker container management |
| **Moltbot** | 18789 | AI assistant (localhost only) |

---

## Using the Makefile

The Makefile provides convenient commands for managing your entire server.

### Basic Commands

```bash
make help              # Show all available commands
make status            # Show status of all services
make start             # Start all services
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
make start-moltbot     # Start moltbot AI assistant
```

### Individual Services

```bash
make restart SERVICE=sonarr  # Restart specific service
make update SERVICE=radarr   # Update and restart service
make sonarr-logs            # View Sonarr logs
make radarr-restart         # Restart Radarr
```

### Maintenance

```bash
make update            # Update all services
make backup            # Backup all configurations
make backup-moltbot    # Backup moltbot only
make stats             # Show resource usage
make health            # Check container health
make vpn-check         # Verify VPN connection
make disk-usage        # Show disk usage
```

### Moltbot Commands

```bash
# Setup & Configuration
make moltbot-env             # Create .env with auto-generated token
make moltbot-setup           # Build image and run onboarding
make moltbot-onboard         # Re-run onboarding wizard

# Authentication (Claude Pro)
make moltbot-auth-claude     # Login with Claude Pro account
make moltbot-auth-status     # Check authentication status
make moltbot-auth-refresh    # Refresh session (every 30 days)

# Telegram
make moltbot-telegram        # Setup Telegram channel
make moltbot-telegram-login  # Re-login to Telegram

# Management
make start-moltbot           # Start moltbot gateway
make moltbot-logs            # View logs
make moltbot-verify          # Run verification script
make moltbot-rebuild         # Rebuild from scratch
```

---

## Moltbot AI Assistant

Control your media server via Telegram using Claude AI.

### Features

- 🤖 **AI-Powered** - Powered by Anthropic Claude
- 💬 **Telegram Integration** - Control via Telegram messages
- 🎬 **Media Server Access** - Full API access to Sonarr/Radarr/Jellyfin
- 🔐 **Secure** - Local-only UI, encrypted sessions
- 📁 **File Operations** - Workspace for file management

### Authentication Options

| Method | Cost | Setup Complexity | Best For |
|--------|------|------------------|----------|
| **Claude Pro Account** | $20/month (existing sub) | Easy (browser login) | Personal use |
| **API Key** | Pay-per-token (~$3-15/M tokens) | Easy (copy key) | High volume |

**Recommendation:** Use Claude Pro if you already have a subscription.

### Quick Setup (Claude Pro Account)

```bash
# 1. Create .env with auto-generated token
make moltbot-env

# 2. Add your Telegram bot token to .env
nano .env
# Add your token: TELEGRAM_BOT_TOKEN=123456:ABC-DEF...

# 3. Build and configure (includes Claude + Telegram setup)
make moltbot-setup

# 4. Start gateway
make start-moltbot

# 5. Message the bot on Telegram — it will walk you through
#    providing API keys for Sonarr/Radarr/Jellyfin
```

### Quick Setup (API Key)

```bash
# 1. Create .env with auto-generated token
make moltbot-env

# 2. Add your Anthropic API key to .env
nano .env
# Add your API key: ANTHROPIC_API_KEY=sk-ant-...

# 3. Add your Telegram bot token to .env (if not already done)
# TELEGRAM_BOT_TOKEN=123456:ABC-DEF...

# 4. Build and configure
make moltbot-setup

# 5. Setup Telegram
make moltbot-telegram

# 6. Start gateway
make start-moltbot

# 7. Message the bot on Telegram — provide API keys when asked
```

### Configuration

The bot uses two config locations:

- **Main config**: `/mnt/server/moltbot/config/openclaw.json` — gateway settings, channels, auth
- **Workspace `.env`**: `/mnt/server/moltbot/workspace/.env` — API keys for media services

API keys are provided to the bot via Telegram during the initial conversation. The bot saves them to its workspace `.env` file and uses them to make HTTP calls to your services via the Docker bridge gateway (`172.18.0.1`).

**To provide API keys**, message the bot on Telegram with your keys:
- **Sonarr**: http://localhost:8989 → Settings → General → API Key
- **Radarr**: http://localhost:7878 → Settings → General → API Key
- **Jellyfin**: http://localhost:8096 → Dashboard → API Keys → New

Or manually create the workspace `.env`:
```bash
cat > /mnt/server/moltbot/workspace/.env << 'EOF'
SONARR_API_KEY=your_key_here
SONARR_URL=http://172.18.0.1:8989
RADARR_API_KEY=your_key_here
RADARR_URL=http://172.18.0.1:7878
JELLYFIN_API_KEY=your_key_here
JELLYFIN_URL=http://172.18.0.1:8096
EOF
```

The Telegram allowlist is configured in `openclaw.json`:
```json
{
  "channels": {
    "telegram": {
      "dmPolicy": "allowlist",
      "allowFrom": ["YOUR_TELEGRAM_USER_ID"]
    }
  }
}
```

Secure permissions and restart:
```bash
chmod 700 /mnt/server/moltbot/config
chmod 600 /mnt/server/moltbot/config/openclaw.json
chmod 600 /mnt/server/moltbot/workspace/.env
make restart SERVICE=moltbot-gateway
```

### Using Moltbot via Telegram

**Media Management:**
```
Add Breaking Bad to Sonarr
List all shows in Sonarr
What's downloading right now?
Add The Matrix to Radarr
What movies are downloading?
Check qBittorrent download progress
```

**System Commands:**
```
help
status
workspace
```

**Natural Language:**
```
Add The Wire to my TV show collection
How much storage am I using?
What's the status of my Jellyfin library?
```

### Access Control UI

**From server:**
```bash
http://localhost:18789/
```

**From remote machine:**
```bash
# Create SSH tunnel
ssh -L 18789:localhost:18789 egouda@<server-ip>

# Then browse to: http://localhost:18789/
# Enter gateway token from .env
```

### Moltbot Maintenance

**Check authentication (Claude Pro):**
```bash
make moltbot-auth-status
```

**Refresh session (every 30 days):**
```bash
make moltbot-auth-refresh
```

**Re-login if expired:**
```bash
make moltbot-auth-claude
```

**View logs:**
```bash
make moltbot-logs
```

**Verify installation:**
```bash
make moltbot-verify
```

---

## Service Management

### Starting Services

```bash
# All services
make start

# Service groups
make start-media       # Sonarr, Radarr, Jellyfin
make start-downloaders # qBittorrent, NZBGet
make start-indexers    # Prowlarr, Jackett

# Individual service
make restart SERVICE=sonarr
docker compose up -d sonarr  # Alternative
```

### Stopping Services

```bash
# All services
make stop

# Service groups
make stop-media
make stop-downloaders

# Individual service
make stop SERVICE=sonarr
docker compose stop sonarr  # Alternative
```

### Updating Services

```bash
# Update all services
make update

# Update specific service
make update SERVICE=sonarr

# Manual update
docker compose pull sonarr
docker compose up -d sonarr
```

### Viewing Logs

```bash
# All services
make logs

# Specific service
make logs SERVICE=sonarr
make sonarr-logs  # Shorthand

# Follow logs
docker compose logs -f sonarr
```

---

## Configuration

### Directory Structure

```
/mnt/server/
├── downloads/          # Download client output
│   ├── complete/
│   └── incomplete/
├── media/              # Media library
│   ├── movies/
│   ├── tvshows/
│   └── m3u/
├── sonarr/data/        # Sonarr config
├── radarr/config/      # Radarr config
├── jellyfin/config/    # Jellyfin config
├── qbittorrent/config/ # qBittorrent config
├── moltbot/            # Moltbot
│   ├── config/         # State dir (openclaw.json, credentials, sessions)
│   └── workspace/      # Bot workspace (.env with API keys, memory files)
└── [service]/          # Other service configs
```

### VPN Setup

1. Get VPN config file from your provider
2. Place at: `/mnt/server/vpn/vpn.conf`
3. Restart VPN container: `make restart SERVICE=vpn`

See: https://greenfrognest.com/LMDSVPN.php#vpncontainer

### First-Time Configuration

1. **Configure Prowlarr** with indexers
2. **Connect Sonarr** and **Radarr** to Prowlarr
3. **Add download clients** (qBittorrent, NZBGet) to Sonarr/Radarr
4. **Configure Jellyfin** media libraries
5. **Connect Jellyseerr** to Jellyfin

### Environment Variables

Located in `.env` (not tracked in git):

```env
# Moltbot gateway token
MOLTBOT_GATEWAY_TOKEN=<generate with: openssl rand -hex 32>

# Anthropic authentication (choose one):
# Option 1: Claude Pro account (leave empty, use: make moltbot-auth-claude)
# Option 2: API key
ANTHROPIC_API_KEY=sk-ant-...

# Telegram bot token (from @BotFather)
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
```

---

## Troubleshooting

### General Issues

**Service won't start:**
```bash
# Check logs
make logs SERVICE=servicename

# Check port conflicts
sudo netstat -tlnp | grep PORT

# Restart service
make restart SERVICE=servicename
```

**All services down:**
```bash
# Check Docker status
systemctl status docker

# Restart Docker
sudo systemctl restart docker

# Start services
make start
```

### VPN Issues

**Check VPN connection:**
```bash
make vpn-check
# Should show your VPN IP, not your real IP
```

**VPN not connecting:**
```bash
# Check logs
make logs SERVICE=vpn

# Verify config file
ls -la /mnt/server/vpn/

# Restart VPN
make restart SERVICE=vpn
```

### Moltbot Issues

**Container won't start:**
```bash
# Check logs
make moltbot-logs

# Verify .env exists
cat .env

# Rebuild image
make moltbot-rebuild
```

**Telegram not connecting:**
```bash
# Re-login to Telegram
make moltbot-telegram-login

# Verify bot token is set
grep TELEGRAM_BOT_TOKEN .env

# Check credentials
ls -la /mnt/server/moltbot/config/credentials/

# Re-add channel
make moltbot-telegram
```

**Claude Pro authentication failed:**
```bash
# Check status
make moltbot-auth-status

# Re-login
make moltbot-auth-claude

# If session expired (after 30 days)
make moltbot-auth-refresh
```

**Bot not responding:**
```bash
# Check allowlist
cat /mnt/server/moltbot/config/openclaw.json | grep allowFrom
# Verify your Telegram user ID is there

# Check logs
make moltbot-logs

# Restart
make restart SERVICE=moltbot-gateway
```

**Media commands not working:**
```bash
# Test API connectivity (bot uses Docker bridge gateway IP)
docker compose exec moltbot-gateway curl "http://172.18.0.1:8989/api/v3/system/status?apikey=YOUR_KEY"

# Verify API keys
cat /mnt/server/moltbot/workspace/.env

# Restart after config changes
make restart SERVICE=moltbot-gateway
```

### Permission Errors

```bash
# Fix ownership (services use PUID=1000)
sudo chown -R 1000:1000 /mnt/server/servicename/

# Fix moltbot permissions
chmod 700 /mnt/server/moltbot/config
chmod 600 /mnt/server/moltbot/config/moltbot.json
chmod 600 /mnt/server/moltbot/config/credentials/*.json
```

### Network Issues

```bash
# Check network exists
docker network ls | grep proxy

# Inspect network
docker network inspect home-server_proxy

# Recreate network
make stop
make start
```

---

## Backup & Maintenance

### Backups

```bash
# Backup everything
make backup

# Backup moltbot only
make backup-moltbot

# Manual backup
tar -czf backup-$(date +%Y%m%d).tar.gz \
  /mnt/server/*/config \
  /mnt/server/*/data \
  docker-compose.yml \
  .env
```

Backups are stored in `backups/` directory.

### Monitoring

```bash
# Resource usage
make stats

# Health status
make health

# Disk usage
make disk-usage

# VPN status
make vpn-check
```

### Cleanup

```bash
# Remove unused Docker resources
make prune

# Clean Docker logs
make clean-logs

# Stop and remove everything (⚠️ DESTRUCTIVE)
make clean
```

### Updates

```bash
# Update all services
make update

# Update specific service
make update SERVICE=sonarr

# Update moltbot
make moltbot-rebuild
make start-moltbot
```

---

## Network Architecture

- **proxy network** (172.18.0.0/24) - All services communicate here
- **VPN gateway** - qBittorrent traffic routed through VPN
- **Localhost binding** - Moltbot UI only accessible via 127.0.0.1

---

## Security Notes

- ✅ qBittorrent bound to VPN (traffic stops if VPN disconnects)
- ✅ Moltbot control UI only on localhost (SSH tunnel required)
- ✅ All services use non-root users (PUID/PGID)
- ✅ Credentials stored in /mnt/server/ (not in git)
- ✅ .env file excluded from version control
- ✅ Moltbot: no-new-privileges, minimal capabilities
- ✅ Media directories mounted read-only (except workspace)

---

## Common Commands Quick Reference

```bash
# Service Management
make start                    # Start all services
make stop                     # Stop all services
make restart SERVICE=name     # Restart specific service
make status                   # Show service status
make logs SERVICE=name        # View logs

# Moltbot
make moltbot-setup           # Initial setup
make moltbot-auth-claude     # Login with Claude Pro
make moltbot-telegram        # Setup Telegram
make moltbot-logs            # View logs
make start-moltbot           # Start moltbot

# Maintenance
make update                  # Update all services
make backup                  # Backup configurations
make stats                   # Resource usage
make health                  # Container health
make vpn-check              # Check VPN connection

# Monitoring
make urls                    # Show all service URLs
make disk-usage             # Show disk usage
docker compose ps           # List containers
```

---

## Resources

- **Docker Compose**: https://docs.docker.com/compose/
- **Sonarr**: https://wiki.servarr.com/sonarr
- **Radarr**: https://wiki.servarr.com/radarr
- **Jellyfin**: https://jellyfin.org/docs/
- **Prowlarr**: https://wiki.servarr.com/prowlarr
- **Moltbot**: https://github.com/openclaw/openclaw

---

## Support

**For issues:**
1. Check logs: `make logs SERVICE=name`
2. Review troubleshooting section above
3. Check service-specific documentation

**VPN Setup:**
- https://greenfrognest.com/LMDSVPN.php#vpncontainer

**Moltbot Issues:**
- Run verification: `make moltbot-verify`
- Check auth: `make moltbot-auth-status`
- View logs: `make moltbot-logs`

---

**Made with ❤️ for home media enthusiasts**
