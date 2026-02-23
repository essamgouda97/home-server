# TOOLS.md - Local Notes

Skills define *how* tools work. This file is for *your* specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:
- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

## Home Server Management

You have access to a home media server managed via Docker Compose and a Makefile. You can monitor services, restart containers, check logs, and manage downloads.

### Docker Commands

```bash
# Container management
docker ps                              # List running containers
docker compose -f docker-compose.yml ps  # Service status
docker compose -f docker-compose.yml logs -f --tail=100 <service>  # Service logs
docker compose -f docker-compose.yml restart <service>  # Restart a service
docker stats --no-stream               # Resource usage

# Or use the Makefile (preferred)
make status                            # All services status
make logs SERVICE=sonarr               # Specific service logs
make restart SERVICE=radarr            # Restart specific service
make health                            # Container health check
```

### Media Stack API Endpoints

All services are on localhost. Use `curl` to interact with their APIs.

| Service | Port | API Base | Notes |
|---------|------|----------|-------|
| Sonarr | 8989 | `/api/v3/` | Needs `X-Api-Key` header |
| Radarr | 7878 | `/api/v3/` | Needs `X-Api-Key` header |
| Prowlarr | 9696 | `/api/v1/` | Needs `X-Api-Key` header |
| Jellyfin | 8096 | `/` | Auth via API key or session |
| qBittorrent | 15080 | `/api/v2/` | Login first at `/api/v2/auth/login` |
| Bazarr | 6767 | `/api/` | Needs API key |
| Jellyseerr | 5055 | `/api/v1/` | Needs API key |

API keys are in each service's web UI under Settings.

### System Monitoring

```bash
df -h /mnt/server                     # Disk usage
free -h                                # Memory usage
uptime                                 # System uptime and load
top -bn1 | head -20                    # Process overview
sensors                                # Temperature readings (if available)
```

### Media & Download Paths

```
/mnt/server/media/movies/              # Movie library
/mnt/server/media/tvshows/             # TV show library
/mnt/server/downloads/                 # Active downloads
/mnt/server/downloads/complete/        # Completed downloads
```

### Safety Rules

**Never do:**
- `rm -rf` anything under `/mnt/server/media/` — that's the library
- Stop the VPN while qBittorrent is running — exposes real IP
- Modify Docker volumes directly — use the service APIs
- Change port bindings without checking for conflicts
- Delete `/mnt/server/*/config/` directories — those are service databases

**Always:**
- Use `make` targets when available (safer than raw docker commands)
- Check `make status` before restarting services
- Use the service web UIs for configuration changes
- Back up before major changes: `make backup`

---

Add whatever helps you do your job. This is your cheat sheet.
