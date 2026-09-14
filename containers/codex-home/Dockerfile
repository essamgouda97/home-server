FROM node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @openai/codex@0.154.0 && npm cache clean --force \
    && mkdir -p /app /agent && chown node:node /agent
COPY server.mjs schema.json validation.mjs /app/
USER node
WORKDIR /agent
ENV HOME=/home/node
EXPOSE 18790
CMD ["node", "/app/server.mjs"]
