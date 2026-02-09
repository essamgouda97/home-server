.PHONY: help setup start stop restart status logs clean update backup
.DEFAULT_GOAL := help
.SILENT:

# Check if .env exists, create minimal one if not
.ONESHELL:
check-env:
	@if [ ! -f .env ]; then \
		echo "# Minimal .env - run 'make moltbot-env' for full setup" > .env; \
		echo "MOLTBOT_GATEWAY_TOKEN=" >> .env; \
		echo "ANTHROPIC_API_KEY=" >> .env; \
	fi

# Colors and formatting
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
CYAN := \033[0;36m
MAGENTA := \033[0;35m
BOLD := \033[1m
DIM := \033[2m
NC := \033[0m

# Icons
CHECK := ✓
CROSS := ✗
ARROW := ➜
STAR := ★
ROCKET := 🚀
GEAR := ⚙
BOOK := 📚
LOCK := 🔒
CLOUD := ☁
FIRE := 🔥
PACKAGE := 📦

# Header
define HEADER
echo ""
echo "$(CYAN)╔════════════════════════════════════════════════════════════╗$(NC)"
echo "$(CYAN)║$(NC)  $(BOLD)$(MAGENTA)Home Server Management$(NC)                                  $(CYAN)║$(NC)"
echo "$(CYAN)╚════════════════════════════════════════════════════════════╝$(NC)"
echo ""
endef

# Success message
define success
echo "$(GREEN)$(CHECK)$(NC) $(1)"
endef

# Error message
define error
echo "$(RED)$(CROSS)$(NC) $(1)"
endef

# Info message
define info
echo "$(BLUE)$(ARROW)$(NC) $(1)"
endef

# Warning message
define warn
echo "$(YELLOW)⚠$(NC)  $(1)"
endef

# Section header
define section
echo ""
echo "$(BOLD)$(CYAN)━━━ $(1) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
echo ""
endef

# Progress spinner
define spinner
printf "$(BLUE)$(ARROW)$(NC) $(1) "
for i in 1 2 3; do printf "."; sleep 0.3; done
echo " $(GREEN)Done!$(NC)"
endef

##@ General

help: ## Show this help menu with style
	$(HEADER)
	awk 'BEGIN {FS = ":.*##"; printf "$(BOLD)Usage:$(NC)\n  make $(CYAN)<target>$(NC)\n\n"} \
		/^##@/ { \
			printf "\n$(BOLD)$(YELLOW)%s$(NC)\n", substr($$0, 5); \
			next; \
		} \
		/^[a-zA-Z_-]+:.*?##/ { \
			printf "  $(GREEN)%-28s$(NC) %s\n", $$1, $$2 \
		}' $(MAKEFILE_LIST)
	echo ""
	echo "$(DIM)Tip: Use SERVICE=name with restart/logs/update for specific services$(NC)"
	echo ""

status: check-env ## Show beautiful service status
	$(call section,Service Status)
	printf "$(BOLD)%-30s %-15s %-15s$(NC)\n" "SERVICE" "STATE" "STATUS"
	echo "──────────────────────────────────────────────────────────────────────────"
	docker compose ps --format '{{.Name}}|{{.State}}|{{.Status}}' 2>/dev/null | while IFS='|' read -r name state status; do \
		if [ "$$state" = "running" ]; then \
			printf "$(GREEN)●$(NC) %-28s $(GREEN)%-15s$(NC) " "$$name" "$$state"; \
		elif [ "$$state" = "exited" ]; then \
			printf "$(RED)●$(NC) %-28s $(RED)%-15s$(NC) " "$$name" "$$state"; \
		else \
			printf "$(YELLOW)●$(NC) %-28s $(YELLOW)%-15s$(NC) " "$$name" "$$state"; \
		fi; \
		if echo "$$status" | grep -qi "healthy"; then \
			echo "$(GREEN)$$status$(NC)"; \
		elif echo "$$status" | grep -qi "unhealthy"; then \
			echo "$(RED)$$status$(NC)"; \
		elif echo "$$status" | grep -qi "starting"; then \
			echo "$(YELLOW)$$status$(NC)"; \
		else \
			echo "$$status"; \
		fi; \
	done
	echo ""
	RUNNING=$$(docker compose ps --filter "status=running" -q 2>/dev/null | wc -l); \
	TOTAL=$$(docker compose config --services 2>/dev/null | wc -l); \
	if [ $$RUNNING -eq $$TOTAL ]; then \
		echo "$(GREEN)✓$(NC) All services running ($$RUNNING/$$TOTAL)"; \
	else \
		echo "$(YELLOW)⚠$(NC)  $$RUNNING/$$TOTAL services running"; \
	fi
	echo ""

##@ Service Management

start: check-env ## Start all services
	$(call section,Starting Services)
	$(call info,Starting all services...)
	docker compose up -d 2>&1 | grep -v "Pulling\|Pulled\|variable is not set" || true
	sleep 2
	$(call success,All services started!)
	$(MAKE) --no-print-directory status

stop: ## Stop all services
	$(call section,Stopping Services)
	$(call info,Stopping all services...)
	docker compose down
	$(call success,All services stopped!)

restart: ## Restart services (use SERVICE=name for specific)
	$(call section,Restarting Services)
ifdef SERVICE
	$(call info,Restarting $(SERVICE)...)
	docker compose restart $(SERVICE)
	$(call success,$(SERVICE) restarted!)
else
	$(call info,Restarting all services...)
	docker compose restart
	$(call success,All services restarted!)
endif
	echo ""

pull: ## Pull latest images (use SERVICE=name for specific)
	$(call section,Pulling Images)
ifdef SERVICE
	$(call info,Pulling $(SERVICE)...)
	docker compose pull $(SERVICE)
	$(call success,$(SERVICE) image updated!)
else
	$(call info,Pulling all images...)
	docker compose pull
	$(call success,All images updated!)
endif

update: ## Update and restart (use SERVICE=name for specific)
	$(call section,Updating Services)
ifdef SERVICE
	$(call info,Updating $(SERVICE)...)
	docker compose pull $(SERVICE) 2>&1 | grep -E "Pulling|Downloaded|Up to date" || true
	docker compose up -d $(SERVICE)
	$(call success,$(SERVICE) updated and restarted!)
else
	$(call info,Updating all services...)
	docker compose pull 2>&1 | grep -E "Pulling|Downloaded|Up to date" || true
	docker compose up -d
	$(call success,All services updated!)
endif
	echo ""

logs: ## Show logs (use SERVICE=name for specific service)
	$(call section,Service Logs)
ifdef SERVICE
	$(call info,Showing logs for $(SERVICE)... (Ctrl+C to exit))
	echo ""
	docker compose logs -f --tail=100 $(SERVICE)
else
	$(call info,Showing all logs... (Ctrl+C to exit))
	echo ""
	docker compose logs -f --tail=50
endif

##@ Service Groups

start-media: ## Start media stack (Sonarr, Radarr, Jellyfin)
	$(call section,Starting Media Stack)
	$(call info,Starting Sonarr...)
	docker compose up -d sonarr
	$(call info,Starting Radarr...)
	docker compose up -d radarr
	$(call info,Starting Jellyfin...)
	docker compose up -d jellyfin
	$(call success,Media stack started!)
	echo ""

start-downloaders: ## Start download clients (qBittorrent, NZBGet, VPN)
	$(call section,Starting Download Clients)
	$(call info,Starting VPN gateway...)
	docker compose up -d vpn
	sleep 3
	$(call info,Starting qBittorrent...)
	docker compose up -d qbittorrent
	$(call info,Starting NZBGet...)
	docker compose up -d nzbget
	$(call success,Download clients started!)
	echo ""

start-indexers: ## Start indexers (Prowlarr, Jackett, FlareSolverr)
	$(call section,Starting Indexers)
	$(call info,Starting Prowlarr...)
	docker compose up -d prowlarr
	$(call info,Starting Jackett...)
	docker compose up -d jackett
	$(call info,Starting FlareSolverr...)
	docker compose up -d flaresolverr
	$(call success,Indexers started!)
	echo ""

start-moltbot: ## Start AI assistant
	$(call section,Starting Moltbot)
	@echo "$(BLUE)$(ARROW)$(NC) Starting moltbot gateway..."
	@docker compose up -d moltbot-gateway
	@sleep 2
	@if docker compose ps moltbot-gateway | grep -q "Up"; then \
		echo "$(GREEN)$(CHECK)$(NC) Moltbot is running!" && \
		echo "$(BLUE)$(ARROW)$(NC) Access at: http://localhost:18789"; \
	else \
		echo "$(RED)$(CROSS)$(NC) Failed to start moltbot" && \
		echo "$(YELLOW)⚠$(NC)  Check logs: make moltbot-logs"; \
	fi
	@echo ""

stop-media: ## Stop media stack
	$(call section,Stopping Media Stack)
	docker compose stop sonarr radarr jellyfin
	$(call success,Media stack stopped!)

stop-downloaders: ## Stop download clients
	$(call section,Stopping Download Clients)
	docker compose stop qbittorrent nzbget
	$(call success,Download clients stopped!)

stop-indexers: ## Stop indexers
	$(call section,Stopping Indexers)
	docker compose stop prowlarr jackett flaresolverr
	$(call success,Indexers stopped!)

stop-moltbot: ## Stop AI assistant
	$(call section,Stopping Moltbot)
	docker compose stop moltbot-gateway
	$(call success,Moltbot stopped!)

##@ Moltbot Management

moltbot-setup: ## Build image and run onboarding
	$(call section,Moltbot Setup)
	@if [ ! -f .env ]; then \
		echo "$(RED)$(CROSS)$(NC) .env file not found!" && \
		echo "$(BLUE)$(ARROW)$(NC) Run: make moltbot-env" && \
		exit 1; \
	fi
	@echo "$(BLUE)$(ARROW)$(NC) Building moltbot image... (this may take 5-10 minutes)"
	@echo ""
	@docker compose build --progress=plain moltbot-gateway
	@echo ""
	@echo "$(GREEN)$(CHECK)$(NC) Image built successfully!"
	@echo ""
	@echo "$(BLUE)$(ARROW)$(NC) Running onboarding..."
	@docker compose run --rm moltbot-cli onboard
	@echo "$(GREEN)$(CHECK)$(NC) Setup complete!"
	@echo ""
	@echo "$(BLUE)$(ARROW)$(NC) Next steps:"
	@echo "  1. $(CYAN)make moltbot-auth-claude$(NC) - Login with Claude Pro"
	@echo "  2. $(CYAN)make moltbot-telegram$(NC)   - Setup Telegram"
	@echo "  3. $(CYAN)make start-moltbot$(NC)       - Start the bot"
	@echo ""

moltbot-env: ## Create .env with auto-generated token
	$(call section,Environment Setup)
	@if [ -f .env ]; then \
		echo "$(YELLOW)⚠$(NC)  .env already exists - not overwriting"; \
	else \
		echo "$(BLUE)$(ARROW)$(NC) Generating secure gateway token..." && \
		TOKEN=$$(openssl rand -hex 32) && \
		echo "MOLTBOT_GATEWAY_TOKEN=$$TOKEN" > .env && \
		echo "ANTHROPIC_API_KEY=" >> .env && \
		echo "" >> .env && \
		echo "# For Claude Pro: Leave ANTHROPIC_API_KEY empty" >> .env && \
		echo "# For API: Add your API key above (ANTHROPIC_API_KEY=sk-ant-...)" >> .env && \
		echo "$(GREEN)$(CHECK)$(NC) .env created with auto-generated token!" && \
		echo "" && \
		echo "$(BOLD)Your gateway token:$(NC) $(GREEN)$$TOKEN$(NC)" && \
		echo "" && \
		echo "$(BLUE)$(ARROW)$(NC) Next: $(CYAN)make moltbot-setup$(NC) to build and configure"; \
	fi
	@echo ""

moltbot-token: ## Show current gateway token (for reference)
	$(call section,Gateway Token)
	@if [ -f .env ]; then \
		TOKEN=$$(grep MOLTBOT_GATEWAY_TOKEN .env | cut -d'=' -f2) && \
		if [ -n "$$TOKEN" ]; then \
			echo "$(GREEN)Current token:$(NC) $$TOKEN"; \
		else \
			echo "$(YELLOW)⚠$(NC)  No token set in .env" && \
			echo "$(BLUE)$(ARROW)$(NC) Run: $(CYAN)make moltbot-env$(NC) to generate one"; \
		fi; \
	else \
		echo "$(RED)✗$(NC) .env file not found" && \
		echo "$(BLUE)$(ARROW)$(NC) Run: $(CYAN)make moltbot-env$(NC) to create it"; \
	fi
	@echo ""

moltbot-onboard: ## Run moltbot onboarding
	$(call section,Moltbot Onboarding)
	@echo "$(BLUE)$(ARROW)$(NC) Starting onboarding wizard..."
	@docker compose run --rm moltbot-cli onboard
	@echo ""
	@echo "$(GREEN)$(CHECK)$(NC) Onboarding complete!"
	@echo ""
	@echo "$(BLUE)$(ARROW)$(NC) Next: $(CYAN)make moltbot-auth-claude$(NC) to login with Claude Pro"
	@echo ""

moltbot-auth-claude: ## Login with Claude Pro account
	$(call section,Claude Pro Authentication)
	$(call info,Starting Claude Pro login...)
	echo ""
	docker compose run --rm moltbot-cli auth login
	echo ""
	$(call success,Authentication complete!)
	$(call info,Verifying...)
	$(MAKE) --no-print-directory moltbot-auth-status

moltbot-auth-status: ## Check authentication status
	$(call section,Authentication Status)
	docker compose run --rm moltbot-cli auth status || \
		($(call error,Not authenticated); \
		$(call info,Run: make moltbot-auth-claude))
	echo ""

moltbot-auth-refresh: ## Refresh Claude Pro session
	$(call section,Refreshing Session)
	$(call info,Refreshing Claude Pro session...)
	docker compose run --rm moltbot-cli auth refresh
	$(call success,Session refreshed!)
	echo ""

moltbot-auth-logout: ## Logout from Claude
	$(call section,Logout)
	$(call warn,Logging out from Claude Pro...)
	docker compose run --rm moltbot-cli auth logout
	$(call success,Logged out successfully!)
	echo ""

moltbot-telegram: ## Setup Telegram channel
	$(call section,Telegram Setup)
	$(call info,Starting Telegram setup...)
	echo ""
	$(call info,Ensure TELEGRAM_BOT_TOKEN is set in .env)
	echo ""
	docker compose run --rm moltbot-cli channels add
	echo ""
	$(call success,Telegram connected!)
	echo ""

moltbot-telegram-login: ## Re-login to Telegram
	$(call section,Telegram Re-login)
	$(call info,Re-connecting to Telegram...)
	docker compose run --rm moltbot-cli channels login
	$(call success,Telegram reconnected!)
	echo ""

moltbot-build: ## Build moltbot image (included in setup)
	$(call section,Building Moltbot)
	@echo "$(BLUE)$(ARROW)$(NC) Building image... (5-10 minutes)"
	@echo ""
	docker compose build --progress=plain moltbot-gateway
	@echo ""
	@echo "$(GREEN)$(CHECK)$(NC) Build complete!"
	@echo ""

moltbot-rebuild: ## Rebuild from scratch (no cache)
	$(call section,Rebuilding Moltbot)
	@echo "$(YELLOW)⚠$(NC)  Rebuilding from scratch... (10-15 minutes)"
	@echo ""
	docker compose build --no-cache --progress=plain moltbot-gateway
	@echo ""
	@echo "$(GREEN)$(CHECK)$(NC) Rebuild complete!"
	@echo ""

moltbot-logs: ## Show moltbot logs
	$(call section,Moltbot Logs)
	$(call info,Showing moltbot logs... (Ctrl+C to exit))
	echo ""
	docker compose logs -f --tail=100 moltbot-gateway

moltbot-verify: ## Verify moltbot installation
	$(call section,Moltbot Verification)
	./verify-moltbot.sh
	echo ""

##@ Initial Setup

setup-dirs: ## Create directory structure
	$(call section,Directory Setup)
	$(call info,Creating moltbot directories...)
	mkdir -p /mnt/server/moltbot/{config,workspace,data}
	mkdir -p /mnt/server/moltbot/config/{credentials,sessions,logs}
	$(call success,Directories created!)
	$(call info,Created:)
	echo "  • /mnt/server/moltbot/config"
	echo "  • /mnt/server/moltbot/workspace"
	echo "  • /mnt/server/moltbot/data"
	echo ""

setup-vpn: ## Display VPN setup instructions
	$(call section,VPN Setup)
	$(call info,VPN configuration required)
	echo ""
	echo "  $(BOLD)Steps:$(NC)"
	echo "  1. Get VPN config from your provider"
	echo "  2. Place at: $(CYAN)/mnt/server/vpn/vpn.conf$(NC)"
	echo "  3. Restart VPN: $(CYAN)make restart SERVICE=vpn$(NC)"
	echo ""
	echo "  $(BOLD)Guide:$(NC) $(BLUE)https://greenfrognest.com/LMDSVPN.php#vpncontainer$(NC)"
	echo ""

setup: setup-dirs ## Initial server setup
	$(call section,Initial Setup Complete)
	$(call success,Basic setup done!)
	echo ""
	$(call info,Next steps:)
	echo "  1. $(CYAN)make setup-vpn$(NC)        - Configure VPN"
	echo "  2. $(CYAN)make start$(NC)            - Start all services"
	echo "  3. $(CYAN)make urls$(NC)             - View service URLs"
	echo ""
	$(call info,For Moltbot:)
	echo "  1. $(CYAN)make moltbot-env$(NC)      - Create .env"
	echo "  2. $(CYAN)make moltbot-setup$(NC)    - Build & configure"
	echo "  3. $(CYAN)make moltbot-auth-claude$(NC) - Login"
	echo "  4. $(CYAN)make moltbot-telegram$(NC) - Setup Telegram"
	echo "  5. $(CYAN)make start-moltbot$(NC)    - Start bot"
	echo ""

##@ Maintenance

backup: ## Backup all configurations
	$(call section,Creating Backup)
	@$(call info,Creating backup...)
	@mkdir -p backups
	@BACKUP_FILE=backups/home-server-backup-$$(date +%Y%m%d-%H%M%S).tar.gz; \
	tar -czf $$BACKUP_FILE \
		/mnt/server/*/config \
		/mnt/server/*/data \
		docker-compose.yml \
		.env 2>/dev/null || true; \
	$(call success,Backup created: $$BACKUP_FILE)
	@echo ""

backup-moltbot: ## Backup moltbot only
	$(call section,Moltbot Backup)
	@$(call info,Creating moltbot backup...)
	@mkdir -p backups
	@BACKUP_FILE=backups/moltbot-backup-$$(date +%Y%m%d-%H%M%S).tar.gz; \
	tar -czf $$BACKUP_FILE /mnt/server/moltbot/config; \
	$(call success,Backup created: $$BACKUP_FILE)
	@echo ""

clean: ## Stop and remove all containers (DESTRUCTIVE!)
	$(call section,Clean Everything)
	@echo "$(YELLOW)⚠$(NC)  This will stop and remove ALL containers and volumes!"
	@printf "$(RED)$(BOLD)Are you sure? [y/N] $(NC)"; \
	read confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		echo "$(BLUE)$(ARROW)$(NC) Removing everything..." && \
		docker compose down -v && \
		echo "$(GREEN)$(CHECK)$(NC) Everything removed!"; \
	else \
		echo "$(BLUE)$(ARROW)$(NC) Cancelled"; \
	fi
	@echo ""

clean-logs: ## Clean Docker logs
	$(call section,Cleaning Logs)
	$(call info,Cleaning Docker logs...)
	truncate -s 0 /var/lib/docker/containers/*/*-json.log 2>/dev/null || true
	$(call success,Logs cleaned!)
	echo ""

prune: ## Remove unused Docker resources
	$(call section,Docker Cleanup)
	$(call info,Removing unused resources...)
	docker system prune -f
	$(call success,Cleanup complete!)
	echo ""

##@ Monitoring

stats: ## Show resource usage
	$(call section,Resource Usage)
	docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"
	echo ""

health: ## Check container health
	$(call section,Health Status)
	printf "$(BOLD)%-30s %-15s %-50s$(NC)\n" "CONTAINER" "STATE" "STATUS"
	echo "────────────────────────────────────────────────────────────────────────────────────"
	docker compose ps --format '{{.Name}}|{{.State}}|{{.Status}}' 2>/dev/null | while IFS='|' read -r name state status; do \
		if [ "$$state" = "running" ]; then \
			printf "$(GREEN)%-30s$(NC) " "$$name"; \
		else \
			printf "$(RED)%-30s$(NC) " "$$name"; \
		fi; \
		printf "%-15s " "$$state"; \
		if echo "$$status" | grep -qi "healthy"; then \
			printf "$(GREEN)%s$(NC)\n" "$$status"; \
		elif echo "$$status" | grep -qi "unhealthy"; then \
			printf "$(RED)%s$(NC)\n" "$$status"; \
		elif echo "$$status" | grep -qi "starting"; then \
			printf "$(YELLOW)%s$(NC)\n" "$$status"; \
		else \
			printf "%s\n" "$$status"; \
		fi; \
	done
	echo ""

vpn-check: ## Verify VPN connection
	$(call section,VPN Status)
	@echo "$(BLUE)$(ARROW)$(NC) Checking VPN IP address..."
	@VPN_IP=$$(docker compose exec qbittorrent curl -s ifconfig.me 2>/dev/null || echo "Not running"); \
	if [ "$$VPN_IP" = "Not running" ]; then \
		echo "$(RED)$(CROSS)$(NC) VPN container not running"; \
	else \
		echo "$(GREEN)$(CHECK)$(NC) VPN is active" && \
		echo "  $(BOLD)IP Address:$(NC) $$VPN_IP"; \
	fi
	@echo ""

disk-usage: ## Show disk usage
	$(call section,Disk Usage)
	df -h /mnt/server 2>/dev/null | grep -v tmpfs || echo "$(YELLOW)⚠$(NC)  /mnt/server not found"
	echo ""

##@ Quick Actions

sonarr-restart: ## Restart Sonarr
	$(call info,Restarting Sonarr...)
	docker compose restart sonarr
	$(call success,Sonarr restarted!)

radarr-restart: ## Restart Radarr
	$(call info,Restarting Radarr...)
	docker compose restart radarr
	$(call success,Radarr restarted!)

jellyfin-restart: ## Restart Jellyfin
	$(call info,Restarting Jellyfin...)
	docker compose restart jellyfin
	$(call success,Jellyfin restarted!)

qbittorrent-restart: ## Restart qBittorrent
	$(call info,Restarting qBittorrent...)
	docker compose restart qbittorrent
	$(call success,qBittorrent restarted!)

prowlarr-restart: ## Restart Prowlarr
	$(call info,Restarting Prowlarr...)
	docker compose restart prowlarr
	$(call success,Prowlarr restarted!)

sonarr-logs: ## Show Sonarr logs
	$(call info,Sonarr logs... (Ctrl+C to exit))
	echo ""
	docker compose logs -f --tail=100 sonarr

radarr-logs: ## Show Radarr logs
	$(call info,Radarr logs... (Ctrl+C to exit))
	echo ""
	docker compose logs -f --tail=100 radarr

jellyfin-logs: ## Show Jellyfin logs
	$(call info,Jellyfin logs... (Ctrl+C to exit))
	echo ""
	docker compose logs -f --tail=100 jellyfin

qbittorrent-logs: ## Show qBittorrent logs
	$(call info,qBittorrent logs... (Ctrl+C to exit))
	echo ""
	docker compose logs -f --tail=100 qbittorrent

##@ Information

urls: ## Show all service URLs
	$(call section,Service URLs)
	echo "$(BOLD)$(GREEN)Media Management$(NC)"
	echo "  Sonarr      $(CYAN)→$(NC) http://localhost:8989"
	echo "  Radarr      $(CYAN)→$(NC) http://localhost:7878"
	echo "  Bazarr      $(CYAN)→$(NC) http://localhost:6767"
	echo ""
	echo "$(BOLD)$(GREEN)Media Streaming$(NC)"
	echo "  Jellyfin    $(CYAN)→$(NC) http://localhost:8096"
	echo "  Jellyseerr  $(CYAN)→$(NC) http://localhost:5055"
	echo ""
	echo "$(BOLD)$(GREEN)Download Clients$(NC)"
	echo "  qBittorrent $(CYAN)→$(NC) http://localhost:15080"
	echo "  NZBGet      $(CYAN)→$(NC) http://localhost:6789"
	echo ""
	echo "$(BOLD)$(GREEN)Indexers$(NC)"
	echo "  Prowlarr    $(CYAN)→$(NC) http://localhost:9696"
	echo "  Jackett     $(CYAN)→$(NC) http://localhost:9117"
	echo ""
	echo "$(BOLD)$(GREEN)Infrastructure$(NC)"
	echo "  Portainer   $(CYAN)→$(NC) http://localhost:9000"
	echo "  Moltbot     $(CYAN)→$(NC) http://localhost:18789 $(DIM)(SSH tunnel for remote)$(NC)"
	echo ""
	echo "$(DIM)Remote access: ssh -L 18789:localhost:18789 egouda@<server-ip>$(NC)"
	echo ""

dashboard: ## Quick overview dashboard
	$(HEADER)
	$(call section,System Overview)
	@echo "$(BOLD)Services:$(NC)"
	@RUNNING=$$(docker compose ps --filter "status=running" -q 2>/dev/null | wc -l); \
	TOTAL=$$(docker compose config --services 2>/dev/null | wc -l); \
	if [ $$RUNNING -eq $$TOTAL ]; then \
		echo "  $(GREEN)●$(NC) $$RUNNING/$$TOTAL running $(GREEN)$(CHECK)$(NC)"; \
	else \
		echo "  $(YELLOW)●$(NC) $$RUNNING/$$TOTAL running $(YELLOW)⚠$(NC)"; \
	fi && echo ""
	@echo "$(BOLD)Resource Usage:$(NC)"
	@docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemPerc}}" 2>/dev/null | head -6 | tail -5 | \
	while read name cpu mem; do \
		echo "  $$name: CPU $$cpu | MEM $$mem"; \
	done || echo "  No stats available" && echo ""
	@echo "$(BOLD)Disk Usage:$(NC)"
	@df -h /mnt/server 2>/dev/null | tail -1 | awk '{print "  " $$3 " used / " $$2 " total (" $$5 " used)"}' || echo "  N/A" && echo ""
	@echo "$(BOLD)Quick Actions:$(NC)"
	@echo "  $(CYAN)make status$(NC)      - Detailed service status"
	@echo "  $(CYAN)make logs$(NC)        - View all logs"
	@echo "  $(CYAN)make urls$(NC)        - Show service URLs"
	@echo "  $(CYAN)make health$(NC)      - Check health status"
	@echo ""
