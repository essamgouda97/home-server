#!/usr/bin/env bash
set -euo pipefail

# Create a new agent from templates (host-based OpenClaw)
# Usage: ./scripts/new-agent.sh <name>

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Load server config
# shellcheck disable=SC1091
source "$ROOT_DIR/server.conf"
SERVER_DATA_DIR="${SERVER_DATA_DIR:-/mnt/server}"
REPO_DIR="${REPO_DIR:-$ROOT_DIR}"

NAME="${1:-}"

if [ -z "$NAME" ]; then
    echo "Usage: $0 <agent-name>"
    echo "Example: $0 jarvis"
    exit 1
fi

# Validate name (lowercase alphanumeric + hyphens only)
if ! echo "$NAME" | grep -qE '^[a-z][a-z0-9-]*$'; then
    echo "Error: Agent name must be lowercase alphanumeric (hyphens allowed), starting with a letter"
    echo "Example: servo, jarvis, home-bot"
    exit 1
fi

AGENT_DIR="$REPO_DIR/agents/$NAME"

if [ -d "$AGENT_DIR" ]; then
    echo "Error: Agent '$NAME' already exists at $AGENT_DIR"
    exit 1
fi

# Calculate direct port: first=18789, second=18889, third=18989, etc.
NEXT_PORT=18789
for env_file in "$REPO_DIR"/agents/*/.env 2>/dev/null; do
    [ -f "$env_file" ] || continue
    port=$(grep -E '^OPENCLAW_PORT=' "$env_file" | cut -d= -f2 || echo "0")
    # Also handle legacy AGENT_PORT_OFFSET format
    if [ "$port" = "0" ] || [ -z "$port" ]; then
        offset=$(grep -E '^AGENT_PORT_OFFSET=' "$env_file" | cut -d= -f2 || echo "0")
        port=$((18789 + offset))
    fi
    if [ "$port" -ge "$NEXT_PORT" ]; then
        NEXT_PORT=$((port + 100))
    fi
done

# Generate gateway token
GATEWAY_TOKEN=$(openssl rand -hex 32)

echo "Creating agent: $NAME"
echo "  Port: $NEXT_PORT"
echo ""

# Create agent directory and copy workspace templates
mkdir -p "$AGENT_DIR/workspace"
cp -r "$REPO_DIR/templates/workspace/"* "$AGENT_DIR/workspace/"

# Substitute placeholders in workspace files
find "$AGENT_DIR/workspace" -type f -name '*.md' -exec \
    sed -i "s|__SERVER_DATA_DIR__|$SERVER_DATA_DIR|g" {} +

# Create agent .env from template
sed \
    -e "s/__GATEWAY_TOKEN__/$GATEWAY_TOKEN/" \
    -e "s/__PORT__/$NEXT_PORT/" \
    -e "s/__NAME__/$NAME/" \
    -e "s|__SERVER_DATA_DIR__|$SERVER_DATA_DIR|g" \
    -e "s/<name>/$NAME/" \
    "$REPO_DIR/templates/env.template" > "$AGENT_DIR/.env"

# Create server-side directories and seed config
STATE_DIR="$SERVER_DATA_DIR/agents/$NAME"
if [ -d "$SERVER_DATA_DIR" ]; then
    mkdir -p "$STATE_DIR/config"

    # Seed openclaw.json from template with agent-specific values
    WORKSPACE_DIR="$AGENT_DIR/workspace"
    sed \
        -e "s|__PORT__|$NEXT_PORT|g" \
        -e "s|__WORKSPACE_DIR__|$WORKSPACE_DIR|g" \
        "$REPO_DIR/templates/openclaw.json" > "$STATE_DIR/config/openclaw.json"

    # Copy exec-approvals.json
    cp "$REPO_DIR/templates/exec-approvals.json" "$STATE_DIR/config/exec-approvals.json"

    echo "  State dir: $STATE_DIR/config"
    echo "  Config seeded: openclaw.json, exec-approvals.json"
else
    echo "  Warning: $SERVER_DATA_DIR not found — create $STATE_DIR/config manually"
fi

# Enable systemd service
if systemctl --user cat openclaw@.service &>/dev/null 2>&1; then
    systemctl --user enable "openclaw@$NAME"
    echo "  Systemd service: openclaw@$NAME enabled"
else
    echo "  Warning: systemd template not installed. Run: make install-openclaw"
fi

echo ""
echo "Agent '$NAME' created!"
echo ""
echo "Next steps:"
echo "  1. Edit agents/$NAME/.env — add your TELEGRAM_BOT_TOKEN"
echo "  2. Edit $STATE_DIR/config/openclaw.json — set __TELEGRAM_CHAT_ID__"
echo "  3. make agent-setup AGENT=$NAME     — onboard"
echo "  4. make agent-auth AGENT=$NAME      — login with Claude Pro"
echo "  5. make agent-telegram AGENT=$NAME  — connect Telegram"
echo "  6. make start-agent AGENT=$NAME     — start the agent"
echo ""
echo "Workspace files: agents/$NAME/workspace/"
echo "Customize SOUL.md, AGENTS.md, etc. before first boot for a unique personality."
echo ""
