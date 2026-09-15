FROM node:22-bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends python3 make g++ && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build && mkdir -p dist/frontend/excalidraw-assets && cp -r node_modules/@excalidraw/excalidraw/dist/prod/fonts dist/frontend/excalidraw-assets/ && npm prune --omit=dev

FROM node:22-bookworm-slim
WORKDIR /app
COPY --from=build /app/package.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY --from=build /app/LICENSE ./LICENSE
RUN mkdir /data && chown node:node /data
USER node
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000 EXCALIDRAW_DB_PATH=/data/excalidraw.db EXCALIDRAW_EXPORT_DIR=/data/exports LOG_FILE_PATH=/data/excalidraw.log HOME_CANVAS=1
CMD ["node", "dist/server.js"]
