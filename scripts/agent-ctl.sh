#!/usr/bin/env bash
set -euo pipefail

# Agent CLI wrapper — sets env vars and calls openclaw
# Usage: ./scripts/agent-ctl.sh <agent-name> <openclaw-command> [args...]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

NAME="${1:-}"
shift || true

if [ -z "$NAME" ]; then
    echo "Usage: $0 <agent-name> <command> [args...]"
    echo "Example: $0 servo auth login"
    echo "         $0 servo channels add"
    exit 1
fi

AGENT_DIR="$ROOT_DIR/agents/$NAME"

if [ ! -d "$AGENT_DIR" ]; then
    echo "Error: Agent '$NAME' not found at $AGENT_DIR"
    echo "Available: $(ls "$ROOT_DIR/agents/" 2>/dev/null | tr '\n' ' ')"
    exit 1
fi

# Load agent env
if [ -f "$AGENT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$AGENT_DIR/.env"
    set +a
fi

export OPENCLAW_STATE_DIR="/mnt/server/agents/$NAME/config"

exec openclaw "$@"
