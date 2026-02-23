#!/usr/bin/env bash
set -euo pipefail

# First-time host setup for OpenClaw agents
# Installs OpenClaw, enables lingering, installs systemd template

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Load server config
# shellcheck disable=SC1091
source "$ROOT_DIR/server.conf"
SERVER_DATA_DIR="${SERVER_DATA_DIR:-/mnt/server}"
REPO_DIR="${REPO_DIR:-$ROOT_DIR}"

echo "=== OpenClaw Host Setup ==="
echo ""
echo "  Repo:       $REPO_DIR"
echo "  Data dir:   $SERVER_DATA_DIR"
echo ""

# Check Node.js version (22+ required)
if ! command -v node &>/dev/null; then
    echo "Error: Node.js not found. Install Node.js 22+ first."
    echo "  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -"
    echo "  sudo apt-get install -y nodejs"
    exit 1
fi

NODE_MAJOR=$(node -v | sed 's/v//' | cut -d. -f1)
if [ "$NODE_MAJOR" -lt 22 ]; then
    echo "Error: Node.js 22+ required (found $(node -v))"
    echo "  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -"
    echo "  sudo apt-get install -y nodejs"
    exit 1
fi
echo "Node.js $(node -v) — OK"

# Install OpenClaw globally
echo ""
echo "Installing OpenClaw..."
npm install -g openclaw@latest
echo "OpenClaw $(openclaw --version 2>/dev/null || echo 'installed') — OK"

# Enable lingering so user services persist after logout
echo ""
echo "Enabling systemd lingering for $(whoami)..."
LINGER_OK=false
if loginctl show-user "$(whoami)" 2>/dev/null | grep -q "Linger=yes"; then
    LINGER_OK=true
    echo "Lingering already enabled — OK"
elif loginctl enable-linger "$(whoami)" 2>/dev/null; then
    LINGER_OK=true
    echo "Lingering enabled — OK"
elif sudo loginctl enable-linger "$(whoami)" 2>/dev/null; then
    LINGER_OK=true
    echo "Lingering enabled (via sudo) — OK"
fi

if [ "$LINGER_OK" = false ]; then
    echo ""
    echo "WARNING: Could not enable lingering automatically."
    echo "Agent services will stop when you log out unless you run:"
    echo ""
    echo "  sudo loginctl enable-linger $(whoami)"
    echo ""
    echo "Run that command now, then continue with the next steps."
fi

# Create base directories
echo ""
echo "Creating directories..."
mkdir -p "$SERVER_DATA_DIR/agents"
mkdir -p "$REPO_DIR/agents"
echo "Directories created — OK"

# Install systemd user unit template
echo ""
echo "Installing systemd unit template..."
SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"

# Resolve actual openclaw binary path (handles nvm, volta, etc.)
OPENCLAW_BIN=$(command -v openclaw 2>/dev/null || echo "")
if [ -z "$OPENCLAW_BIN" ]; then
    # Check common npm global locations
    for candidate in \
        "$(npm config get prefix 2>/dev/null)/bin/openclaw" \
        "$HOME/.npm-global/bin/openclaw" \
        "/usr/local/bin/openclaw" \
        "/usr/bin/openclaw"; do
        if [ -x "$candidate" ]; then
            OPENCLAW_BIN="$candidate"
            break
        fi
    done
fi

if [ -z "$OPENCLAW_BIN" ]; then
    echo "Error: Cannot find openclaw binary after installation"
    exit 1
fi

NODE_BIN_DIR=$(dirname "$(command -v node)")
echo "  Binary: $OPENCLAW_BIN"
echo "  Node bin: $NODE_BIN_DIR"

# Substitute all paths into the template
sed -e "s|__OPENCLAW_BIN__|$OPENCLAW_BIN|g" \
    -e "s|__NODE_BIN_DIR__|$NODE_BIN_DIR|g" \
    -e "s|__REPO_DIR__|$REPO_DIR|g" \
    -e "s|__SERVER_DATA_DIR__|$SERVER_DATA_DIR|g" \
    "$REPO_DIR/templates/systemd/openclaw@.service" > "$SYSTEMD_DIR/openclaw@.service"

systemctl --user daemon-reload
echo "Systemd template installed — OK"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. make new-agent NAME=servo       — create an agent"
echo "  2. Edit agents/servo/.env           — add TELEGRAM_BOT_TOKEN"
echo "  3. make agent-setup AGENT=servo     — onboard"
echo "  4. make agent-auth AGENT=servo      — login with Claude Pro"
echo "  5. make agent-telegram AGENT=servo  — connect Telegram"
echo "  6. make start-agent AGENT=servo     — start the agent"
echo ""
