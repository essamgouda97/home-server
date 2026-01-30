FROM node:22-bookworm

# Install system dependencies
RUN apt-get update && \
    apt-get install -y curl ca-certificates git && \
    rm -rf /var/lib/apt/lists/*

# Install Bun and enable corepack for pnpm
RUN curl -fsSL https://bun.sh/install | bash
RUN corepack enable

# Set working directory
WORKDIR /app

# Clone and build moltbot
RUN git clone https://github.com/openclaw/openclaw.git . && \
    pnpm install --frozen-lockfile && \
    pnpm build && \
    cd ui && pnpm install && pnpm build

# Use existing node user (UID/GID 1000) and create directories
RUN mkdir -p /home/node/.clawdbot /home/node/clawd && \
    chown -R node:node /home/node /app

# Environment defaults
ENV NODE_ENV=production \
    PUID=1000 \
    PGID=1000 \
    TZ=UTC

# Switch to non-root user
USER node

# Expose ports
EXPOSE 18789 18790 18793

# Default command (gateway mode)
CMD ["node", "dist/index.js", "gateway"]
