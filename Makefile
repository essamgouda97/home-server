.PHONY: help setup start stop restart status logs clean update backup
.DEFAULT_GOAL := help
.SILENT:

# Load server config (paths are configurable in server.conf)
SERVER_DATA_DIR := $(shell grep -E '^SERVER_DATA_DIR=' server.conf 2>/dev/null | cut -d= -f2 || echo /mnt/server)

# Compose command — media stack only (agents run as systemd services)
COMPOSE := docker compose -f docker-compose.yml

# Check if .env exists, create minimal one if not
.ONESHELL:
check-env:
	@if [ ! -f .env ]; then \
		echo "ANTHROPIC_API_KEY=" > .env; \
		echo "" >> .env; \
		echo "# Shared across all agents" >> .env; \
		echo "# For Claude Pro: Leave ANTHROPIC_API_KEY empty" >> .env; \
		echo "# For API: Add your API key (ANTHROPIC_API_KEY=sk-ant-...)" >> .env; \
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

# Validate AGENT= is set and exists
define check-agent
@if [ -z "$(AGENT)" ]; then \
	echo "$(RED)$(CROSS)$(NC) AGENT= is required" && \
	echo "$(BLUE)$(ARROW)$(NC) Usage: make $@ AGENT=<name>" && \
	echo "$(BLUE)$(ARROW)$(NC) Available: $$(ls agents/ 2>/dev/null | tr '\n' ' ')" && \
	exit 1; \
fi
@if [ ! -d "agents/$(AGENT)" ]; then \
	echo "$(RED)$(CROSS)$(NC) Agent '$(AGENT)' not found" && \
	echo "$(BLUE)$(ARROW)$(NC) Available: $$(ls agents/ 2>/dev/null | tr '\n' ' ')" && \
	echo "$(BLUE)$(ARROW)$(NC) Create one: make new-agent NAME=$(AGENT)" && \
	exit 1; \
fi
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
	echo "$(DIM)Tip: Use AGENT=name for agent commands, SERVICE=name for infra$(NC)"
	echo ""

status: check-env ## Show service status (Docker + agents)
	$(call section,Docker Services)
	printf "$(BOLD)%-30s %-15s %-15s$(NC)\n" "SERVICE" "STATE" "STATUS"
	echo "──────────────────────────────────────────────────────────────────────────"
	$(COMPOSE) ps --format '{{.Name}}|{{.State}}|{{.Status}}' 2>/dev/null | while IFS='|' read -r name state status; do \
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
	RUNNING=$$($(COMPOSE) ps --filter "status=running" -q 2>/dev/null | wc -l); \
	TOTAL=$$($(COMPOSE) config --services 2>/dev/null | wc -l); \
	if [ $$RUNNING -eq $$TOTAL ]; then \
		echo "$(GREEN)✓$(NC) All Docker services running ($$RUNNING/$$TOTAL)"; \
	else \
		echo "$(YELLOW)⚠$(NC)  $$RUNNING/$$TOTAL Docker services running"; \
	fi
	echo ""
	$(call section,Agent Services)
	@if [ ! -d agents ] || [ -z "$$(ls -A agents 2>/dev/null)" ]; then \
		echo "$(DIM)No agents found. Create one: make new-agent NAME=servo$(NC)"; \
	else \
		printf "$(BOLD)%-15s %-12s %-10s$(NC)\n" "AGENT" "STATUS" "PORT"; \
		echo "─────────────────────────────────────────"; \
		for dir in agents/*/; do \
			[ -d "$$dir" ] || continue; \
			name=$$(basename "$$dir"); \
			port=$$(grep -E '^OPENCLAW_PORT=' "$$dir/.env" 2>/dev/null | cut -d= -f2 || echo "?"); \
			state=$$(systemctl --user is-active "openclaw@$$name" 2>/dev/null || echo "inactive"); \
			if [ "$$state" = "active" ]; then \
				printf "$(GREEN)●$(NC) %-13s $(GREEN)%-12s$(NC) %s\n" "$$name" "$$state" "$$port"; \
			else \
				printf "$(RED)●$(NC) %-13s $(DIM)%-12s$(NC) %s\n" "$$name" "$$state" "$$port"; \
			fi; \
		done; \
	fi
	echo ""

##@ Service Management

start: check-env ## Start all services (Docker infra + agents)
	$(call section,Starting Services)
	$(call info,Starting Docker services...)
	$(COMPOSE) up -d 2>&1 | grep -v "Pulling\|Pulled\|variable is not set" || true
	sleep 2
	@if [ -d agents ] && [ -n "$$(ls -A agents 2>/dev/null)" ]; then \
		echo "$(BLUE)$(ARROW)$(NC) Starting agents..."; \
		for dir in agents/*/; do \
			[ -d "$$dir" ] || continue; \
			name=$$(basename "$$dir"); \
			systemctl --user start "openclaw@$$name" 2>/dev/null || true; \
		done; \
	fi
	$(call success,All services started!)
	$(MAKE) --no-print-directory status

stop: ## Stop all services (Docker infra + agents)
	$(call section,Stopping Services)
	@if [ -d agents ] && [ -n "$$(ls -A agents 2>/dev/null)" ]; then \
		echo "$(BLUE)$(ARROW)$(NC) Stopping agents..."; \
		for dir in agents/*/; do \
			[ -d "$$dir" ] || continue; \
			name=$$(basename "$$dir"); \
			systemctl --user stop "openclaw@$$name" 2>/dev/null || true; \
		done; \
	fi
	$(call info,Stopping Docker services...)
	$(COMPOSE) down
	$(call success,All services stopped!)

restart: ## Restart services (use SERVICE=name for specific)
	$(call section,Restarting Services)
ifdef SERVICE
	$(call info,Restarting $(SERVICE)...)
	$(COMPOSE) restart $(SERVICE)
	$(call success,$(SERVICE) restarted!)
else
	$(call info,Restarting all services...)
	$(COMPOSE) restart
	$(call success,All services restarted!)
endif
	echo ""

pull: ## Pull latest images (use SERVICE=name for specific)
	$(call section,Pulling Images)
ifdef SERVICE
	$(call info,Pulling $(SERVICE)...)
	$(COMPOSE) pull $(SERVICE)
	$(call success,$(SERVICE) image updated!)
else
	$(call info,Pulling all images...)
	$(COMPOSE) pull
	$(call success,All images updated!)
endif

update: ## Update and restart (use SERVICE=name for specific)
	$(call section,Updating Services)
ifdef SERVICE
	$(call info,Updating $(SERVICE)...)
	$(COMPOSE) pull $(SERVICE) 2>&1 | grep -E "Pulling|Downloaded|Up to date" || true
	$(COMPOSE) up -d $(SERVICE)
	$(call success,$(SERVICE) updated and restarted!)
else
	$(call info,Updating all services...)
	$(COMPOSE) pull 2>&1 | grep -E "Pulling|Downloaded|Up to date" || true
	$(COMPOSE) up -d
	$(call success,All services updated!)
endif
	echo ""

logs: ## Show logs (use SERVICE=name for specific service)
	$(call section,Service Logs)
ifdef SERVICE
	$(call info,Showing logs for $(SERVICE)... (Ctrl+C to exit))
	echo ""
	$(COMPOSE) logs -f --tail=100 $(SERVICE)
else
	$(call info,Showing all logs... (Ctrl+C to exit))
	echo ""
	$(COMPOSE) logs -f --tail=50
endif

##@ Service Groups

start-media: ## Start media stack (Sonarr, Radarr, Jellyfin)
	$(call section,Starting Media Stack)
	$(call info,Starting Sonarr...)
	$(COMPOSE) up -d sonarr
	$(call info,Starting Radarr...)
	$(COMPOSE) up -d radarr
	$(call info,Starting Jellyfin...)
	$(COMPOSE) up -d jellyfin
	$(call success,Media stack started!)
	echo ""

start-downloaders: ## Start download clients (qBittorrent, NZBGet, VPN)
	$(call section,Starting Download Clients)
	$(call info,Starting VPN gateway...)
	$(COMPOSE) up -d vpn
	sleep 3
	$(call info,Starting qBittorrent...)
	$(COMPOSE) up -d qbittorrent
	$(call info,Starting NZBGet...)
	$(COMPOSE) up -d nzbget
	$(call success,Download clients started!)
	echo ""

start-indexers: ## Start indexers (Prowlarr, Jackett, FlareSolverr)
	$(call section,Starting Indexers)
	$(call info,Starting Prowlarr...)
	$(COMPOSE) up -d prowlarr
	$(call info,Starting Jackett...)
	$(COMPOSE) up -d jackett
	$(call info,Starting FlareSolverr...)
	$(COMPOSE) up -d flaresolverr
	$(call success,Indexers started!)
	echo ""

stop-media: ## Stop media stack
	$(call section,Stopping Media Stack)
	$(COMPOSE) stop sonarr radarr jellyfin
	$(call success,Media stack stopped!)

stop-downloaders: ## Stop download clients
	$(call section,Stopping Download Clients)
	$(COMPOSE) stop qbittorrent nzbget
	$(call success,Download clients stopped!)

stop-indexers: ## Stop indexers
	$(call section,Stopping Indexers)
	$(COMPOSE) stop prowlarr jackett flaresolverr
	$(call success,Indexers stopped!)

##@ Agent Management

new-agent: ## Create a new agent (NAME=required)
	$(call section,New Agent)
	@if [ -z "$(NAME)" ]; then \
		echo "$(RED)$(CROSS)$(NC) NAME= is required" && \
		echo "$(BLUE)$(ARROW)$(NC) Usage: make new-agent NAME=jarvis" && \
		exit 1; \
	fi
	@./scripts/new-agent.sh $(NAME)

list-agents: ## List all agents and their status
	$(call section,Agents)
	@if [ ! -d agents ] || [ -z "$$(ls -A agents 2>/dev/null)" ]; then \
		echo "$(DIM)No agents found. Create one:$(NC)" && \
		echo "  $(CYAN)make new-agent NAME=servo$(NC)" && \
		echo ""; \
		exit 0; \
	fi
	@printf "$(BOLD)%-15s %-12s %-10s$(NC)\n" "AGENT" "STATUS" "PORT"
	@echo "─────────────────────────────────────────"
	@for dir in agents/*/; do \
		[ -d "$$dir" ] || continue; \
		name=$$(basename "$$dir"); \
		port=$$(grep -E '^OPENCLAW_PORT=' "$$dir/.env" 2>/dev/null | cut -d= -f2 || echo "?"); \
		state=$$(systemctl --user is-active "openclaw@$$name" 2>/dev/null || echo "inactive"); \
		if [ "$$state" = "active" ]; then \
			printf "$(GREEN)●$(NC) %-13s $(GREEN)%-12s$(NC) %s\n" "$$name" "$$state" "$$port"; \
		else \
			printf "$(RED)●$(NC) %-13s $(DIM)%-12s$(NC) %s\n" "$$name" "$$state" "$$port"; \
		fi; \
	done
	@echo ""

start-agent: ## Start an agent (AGENT=name)
	$(check-agent)
	$(call section,Starting $(AGENT))
	@echo "$(BLUE)$(ARROW)$(NC) Starting $(AGENT)..."
	@systemctl --user start "openclaw@$(AGENT)"
	@sleep 2
	@STATE=$$(systemctl --user is-active "openclaw@$(AGENT)" 2>/dev/null || echo "failed"); \
	PORT=$$(grep -E '^OPENCLAW_PORT=' agents/$(AGENT)/.env 2>/dev/null | cut -d= -f2 || echo "?"); \
	if [ "$$STATE" = "active" ]; then \
		echo "$(GREEN)$(CHECK)$(NC) $(AGENT) is running!" && \
		echo "$(BLUE)$(ARROW)$(NC) Port: $$PORT"; \
	else \
		echo "$(RED)$(CROSS)$(NC) Failed to start $(AGENT)" && \
		echo "$(YELLOW)⚠$(NC)  Check logs: make agent-logs AGENT=$(AGENT)"; \
	fi
	@echo ""

stop-agent: ## Stop an agent (AGENT=name)
	$(check-agent)
	$(call section,Stopping $(AGENT))
	systemctl --user stop "openclaw@$(AGENT)"
	$(call success,$(AGENT) stopped!)
	echo ""

restart-agent: ## Restart an agent (AGENT=name)
	$(check-agent)
	$(call section,Restarting $(AGENT))
	systemctl --user restart "openclaw@$(AGENT)"
	$(call success,$(AGENT) restarted!)
	echo ""

start-agents: ## Start all agents
	$(call section,Starting All Agents)
	@for dir in agents/*/; do \
		[ -d "$$dir" ] || continue; \
		name=$$(basename "$$dir"); \
		echo "$(BLUE)$(ARROW)$(NC) Starting $$name..."; \
		systemctl --user start "openclaw@$$name" 2>/dev/null || true; \
	done
	$(call success,All agents started!)
	echo ""

stop-agents: ## Stop all agents
	$(call section,Stopping All Agents)
	@for dir in agents/*/; do \
		[ -d "$$dir" ] || continue; \
		name=$$(basename "$$dir"); \
		echo "$(BLUE)$(ARROW)$(NC) Stopping $$name..."; \
		systemctl --user stop "openclaw@$$name" 2>/dev/null || true; \
	done
	$(call success,All agents stopped!)
	echo ""

agent-logs: ## Show agent logs (AGENT=name)
	$(check-agent)
	$(call section,$(AGENT) Logs)
	$(call info,Showing $(AGENT) logs... (Ctrl+C to exit))
	echo ""
	journalctl --user -u "openclaw@$(AGENT)" -f --no-hostname -n 100

agent-status: ## Show detailed agent status (AGENT=name)
	$(check-agent)
	$(call section,$(AGENT) Status)
	systemctl --user status "openclaw@$(AGENT)" --no-pager || true
	echo ""

##@ Agent Setup

install-openclaw: ## Install OpenClaw on host (one-time setup)
	$(call section,Installing OpenClaw)
	@./scripts/setup-host.sh

update-openclaw: ## Update OpenClaw to latest version
	$(call section,Updating OpenClaw)
	$(call info,Updating OpenClaw...)
	npm install -g openclaw@latest
	$(call success,OpenClaw updated!)
	echo ""

agent-setup: ## Onboard an agent (AGENT=name)
	$(check-agent)
	$(call section,Setting Up $(AGENT))
	@echo "$(BLUE)$(ARROW)$(NC) Running onboarding for $(AGENT)..."
	@./scripts/agent-ctl.sh $(AGENT) onboard
	@echo "$(GREEN)$(CHECK)$(NC) Setup complete!"
	@echo ""
	@echo "$(BLUE)$(ARROW)$(NC) Next steps:"
	@echo "  1. $(CYAN)make agent-auth AGENT=$(AGENT)$(NC)      - Login with Claude Pro"
	@echo "  2. $(CYAN)make agent-telegram AGENT=$(AGENT)$(NC)  - Setup Telegram"
	@echo "  3. $(CYAN)make start-agent AGENT=$(AGENT)$(NC)     - Start the agent"
	@echo ""

agent-auth: ## Login agent with Claude Pro (AGENT=name)
	$(check-agent)
	$(call section,Claude Pro Authentication — $(AGENT))
	$(call info,Starting Claude Pro login for $(AGENT)...)
	echo ""
	./scripts/agent-ctl.sh $(AGENT) auth login
	echo ""
	$(call success,Authentication complete!)
	echo ""

agent-auth-status: ## Check agent auth status (AGENT=name)
	$(check-agent)
	$(call section,Auth Status — $(AGENT))
	./scripts/agent-ctl.sh $(AGENT) auth status || \
		($(call error,Not authenticated); \
		$(call info,Run: make agent-auth AGENT=$(AGENT)))
	echo ""

agent-auth-refresh: ## Refresh agent Claude Pro session (AGENT=name)
	$(check-agent)
	$(call section,Refreshing Session — $(AGENT))
	$(call info,Refreshing Claude Pro session...)
	./scripts/agent-ctl.sh $(AGENT) auth refresh
	$(call success,Session refreshed!)
	echo ""

agent-telegram: ## Setup Telegram for an agent (AGENT=name)
	$(check-agent)
	$(call section,Telegram Setup — $(AGENT))
	$(call info,Starting Telegram setup for $(AGENT)...)
	@TOKEN=$$(grep -E '^TELEGRAM_BOT_TOKEN=' agents/$(AGENT)/.env | cut -d= -f2); \
	if [ -z "$$TOKEN" ]; then \
		echo "$(RED)$(CROSS)$(NC) No TELEGRAM_BOT_TOKEN in agents/$(AGENT)/.env" && \
		echo "$(BLUE)$(ARROW)$(NC) Get one from @BotFather on Telegram, then add it to agents/$(AGENT)/.env" && \
		exit 1; \
	fi
	echo ""
	./scripts/agent-ctl.sh $(AGENT) channels add
	echo ""
	$(call success,Telegram connected for $(AGENT)!)
	echo ""

##@ Initial Setup

setup-dirs: ## Create directory structure
	$(call section,Directory Setup)
	$(call info,Creating base directories...)
	mkdir -p $(SERVER_DATA_DIR)/agents
	mkdir -p agents
	$(call success,Directories created!)
	echo ""

setup-vpn: ## Display VPN setup instructions
	$(call section,VPN Setup)
	$(call info,VPN configuration required)
	echo ""
	echo "  $(BOLD)Steps:$(NC)"
	echo "  1. Get VPN config from your provider"
	echo "  2. Place at: $(CYAN)$(SERVER_DATA_DIR)/vpn/vpn.conf$(NC)"
	echo "  3. Restart VPN: $(CYAN)make restart SERVICE=vpn$(NC)"
	echo ""
	echo "  $(BOLD)Guide:$(NC) $(BLUE)https://greenfrognest.com/LMDSVPN.php#vpncontainer$(NC)"
	echo ""

setup: setup-dirs ## Initial server setup
	$(call section,Initial Setup Complete)
	$(call success,Basic setup done!)
	echo ""
	$(call info,Next steps:)
	echo "  1. $(CYAN)make setup-vpn$(NC)                    - Configure VPN"
	echo "  2. $(CYAN)make start$(NC)                        - Start all services"
	echo "  3. $(CYAN)make urls$(NC)                         - View service URLs"
	echo ""
	$(call info,For Agents:)
	echo "  1. $(CYAN)make install-openclaw$(NC)             - Install OpenClaw (one-time)"
	echo "  2. $(CYAN)make new-agent NAME=servo$(NC)         - Create an agent"
	echo "  3. $(CYAN)make agent-setup AGENT=servo$(NC)      - Onboard the agent"
	echo "  4. $(CYAN)make agent-auth AGENT=servo$(NC)       - Login with Claude Pro"
	echo "  5. $(CYAN)make agent-telegram AGENT=servo$(NC)   - Setup Telegram"
	echo "  6. $(CYAN)make start-agent AGENT=servo$(NC)      - Start the agent"
	echo ""

##@ Maintenance

backup: ## Backup all configurations
	$(call section,Creating Backup)
	@$(call info,Creating backup...)
	@mkdir -p backups
	@BACKUP_FILE=backups/home-server-backup-$$(date +%Y%m%d-%H%M%S).tar.gz; \
	tar -czf $$BACKUP_FILE \
		$(SERVER_DATA_DIR)/*/config \
		$(SERVER_DATA_DIR)/*/data \
		docker-compose.yml \
		.env 2>/dev/null || true; \
	$(call success,Backup created: $$BACKUP_FILE)
	@echo ""

backup-agents: ## Backup all agent configs and workspaces
	$(call section,Agent Backup)
	@$(call info,Creating agent backup...)
	@mkdir -p backups
	@BACKUP_FILE=backups/agents-backup-$$(date +%Y%m%d-%H%M%S).tar.gz; \
	tar -czf $$BACKUP_FILE \
		agents/ \
		$(SERVER_DATA_DIR)/agents/ 2>/dev/null || true; \
	$(call success,Backup created: $$BACKUP_FILE)
	@echo ""

clean: ## Stop and remove all containers (DESTRUCTIVE!)
	$(call section,Clean Everything)
	@echo "$(YELLOW)⚠$(NC)  This will stop and remove ALL containers and volumes!"
	@printf "$(RED)$(BOLD)Are you sure? [y/N] $(NC)"; \
	read confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		echo "$(BLUE)$(ARROW)$(NC) Removing everything..." && \
		$(COMPOSE) down -v && \
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
	$(COMPOSE) ps --format '{{.Name}}|{{.State}}|{{.Status}}' 2>/dev/null | while IFS='|' read -r name state status; do \
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
	@VPN_IP=$$($(COMPOSE) exec qbittorrent curl -s ifconfig.me 2>/dev/null || echo "Not running"); \
	if [ "$$VPN_IP" = "Not running" ]; then \
		echo "$(RED)$(CROSS)$(NC) VPN container not running"; \
	else \
		echo "$(GREEN)$(CHECK)$(NC) VPN is active" && \
		echo "  $(BOLD)IP Address:$(NC) $$VPN_IP"; \
	fi
	@echo ""

disk-usage: ## Show disk usage
	$(call section,Disk Usage)
	df -h $(SERVER_DATA_DIR) 2>/dev/null | grep -v tmpfs || echo "$(YELLOW)⚠$(NC)  $(SERVER_DATA_DIR) not found"
	echo ""

##@ Quick Actions

sonarr-restart: ## Restart Sonarr
	$(call info,Restarting Sonarr...)
	$(COMPOSE) restart sonarr
	$(call success,Sonarr restarted!)

radarr-restart: ## Restart Radarr
	$(call info,Restarting Radarr...)
	$(COMPOSE) restart radarr
	$(call success,Radarr restarted!)

jellyfin-restart: ## Restart Jellyfin
	$(call info,Restarting Jellyfin...)
	$(COMPOSE) restart jellyfin
	$(call success,Jellyfin restarted!)

qbittorrent-restart: ## Restart qBittorrent
	$(call info,Restarting qBittorrent...)
	$(COMPOSE) restart qbittorrent
	$(call success,qBittorrent restarted!)

prowlarr-restart: ## Restart Prowlarr
	$(call info,Restarting Prowlarr...)
	$(COMPOSE) restart prowlarr
	$(call success,Prowlarr restarted!)

sonarr-logs: ## Show Sonarr logs
	$(call info,Sonarr logs... (Ctrl+C to exit))
	echo ""
	$(COMPOSE) logs -f --tail=100 sonarr

radarr-logs: ## Show Radarr logs
	$(call info,Radarr logs... (Ctrl+C to exit))
	echo ""
	$(COMPOSE) logs -f --tail=100 radarr

jellyfin-logs: ## Show Jellyfin logs
	$(call info,Jellyfin logs... (Ctrl+C to exit))
	echo ""
	$(COMPOSE) logs -f --tail=100 jellyfin

qbittorrent-logs: ## Show qBittorrent logs
	$(call info,qBittorrent logs... (Ctrl+C to exit))
	echo ""
	$(COMPOSE) logs -f --tail=100 qbittorrent

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
	echo ""
	@if [ -d agents ] && [ -n "$$(ls -A agents 2>/dev/null)" ]; then \
		echo "$(BOLD)$(GREEN)Agents$(NC)"; \
		for dir in agents/*/; do \
			[ -d "$$dir" ] || continue; \
			name=$$(basename "$$dir"); \
			port=$$(grep -E '^OPENCLAW_PORT=' "$$dir/.env" 2>/dev/null | cut -d= -f2 || echo "?"); \
			printf "  %-12s $(CYAN)→$(NC) http://localhost:%s\n" "$$name" "$$port"; \
		done; \
		echo ""; \
	fi
	echo "$(DIM)Remote access: ssh -L <port>:localhost:<port> egouda@<server-ip>$(NC)"
	echo ""

dashboard: ## Quick overview dashboard
	$(HEADER)
	$(call section,System Overview)
	@echo "$(BOLD)Docker Services:$(NC)"
	@RUNNING=$$($(COMPOSE) ps --filter "status=running" -q 2>/dev/null | wc -l); \
	TOTAL=$$($(COMPOSE) config --services 2>/dev/null | wc -l); \
	if [ $$RUNNING -eq $$TOTAL ]; then \
		echo "  $(GREEN)●$(NC) $$RUNNING/$$TOTAL running $(GREEN)$(CHECK)$(NC)"; \
	else \
		echo "  $(YELLOW)●$(NC) $$RUNNING/$$TOTAL running $(YELLOW)⚠$(NC)"; \
	fi && echo ""
	@echo "$(BOLD)Agents:$(NC)"
	@if [ -d agents ] && [ -n "$$(ls -A agents 2>/dev/null)" ]; then \
		for dir in agents/*/; do \
			[ -d "$$dir" ] || continue; \
			name=$$(basename "$$dir"); \
			state=$$(systemctl --user is-active "openclaw@$$name" 2>/dev/null || echo "inactive"); \
			if [ "$$state" = "active" ]; then \
				echo "  $(GREEN)●$(NC) $$name — active"; \
			else \
				echo "  $(RED)●$(NC) $$name — $$state"; \
			fi; \
		done; \
	else \
		echo "  $(DIM)No agents configured$(NC)"; \
	fi && echo ""
	@echo "$(BOLD)Resource Usage:$(NC)"
	@docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemPerc}}" 2>/dev/null | head -6 | tail -5 | \
	while read name cpu mem; do \
		echo "  $$name: CPU $$cpu | MEM $$mem"; \
	done || echo "  No stats available" && echo ""
	@echo "$(BOLD)Disk Usage:$(NC)"
	@df -h $(SERVER_DATA_DIR) 2>/dev/null | tail -1 | awk '{print "  " $$3 " used / " $$2 " total (" $$5 " used)"}' || echo "  N/A" && echo ""
	@echo "$(BOLD)Quick Actions:$(NC)"
	@echo "  $(CYAN)make status$(NC)        - Detailed service status"
	@echo "  $(CYAN)make list-agents$(NC)   - Show all agents"
	@echo "  $(CYAN)make logs$(NC)          - View all logs"
	@echo "  $(CYAN)make urls$(NC)          - Show service URLs"
	@echo "  $(CYAN)make health$(NC)        - Check health status"
	@echo ""
