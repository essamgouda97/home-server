#!/bin/sh
set -eu
repo_dir=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
. "$repo_dir/server.conf"
source_dir="$SERVER_HOME/.local/share/home-server/excalidraw"
revision=a1977d86f9529276ed1b97cbf1d05de4319c59cb
if [ ! -d "$source_dir/.git" ]; then
    git clone https://github.com/sanjibdevnathlabs/mcp-excalidraw-local.git "$source_dir"
    git -C "$source_dir" checkout --detach "$revision"
fi
test "$(git -C "$source_dir" rev-parse HEAD)" = "$revision"
if git -C "$source_dir" apply --reverse --check "$repo_dir/config/excalidraw/home-server.patch" 2>/dev/null; then
    : # Already patched.
else
    git -C "$source_dir" apply --check "$repo_dir/config/excalidraw/home-server.patch"
    git -C "$source_dir" apply "$repo_dir/config/excalidraw/home-server.patch"
fi
cp "$repo_dir/config/excalidraw/Dockerfile" "$source_dir/Dockerfile.home-server"
docker run --rm --user 0 --entrypoint sh -v /srv/mergerfs/ssd:/storage pihole/pihole:2026.07.2 -c 'mkdir -p /storage/excalidraw/exports && chown 1000:1000 /storage/excalidraw /storage/excalidraw/exports && chmod 700 /storage/excalidraw /storage/excalidraw/exports'
cd "$repo_dir"
docker compose --env-file server.conf -f compose.excalidraw.yml -p home-draw build
docker compose --env-file server.conf -f compose.excalidraw.yml -p home-draw up -d
docker network connect home-canvas npm 2>/dev/null || docker inspect npm --format '{{json .NetworkSettings.Networks}}' | python3 -c 'import json,sys; assert "home-canvas" in json.load(sys.stdin)'
docker network connect home-canvas homarr 2>/dev/null || docker inspect homarr --format '{{json .NetworkSettings.Networks}}' | python3 -c 'import json,sys; assert "home-canvas" in json.load(sys.stdin)'
mkdir -p "$SERVER_HOME/.config/systemd/user"
cp "$repo_dir/templates/systemd/excalidraw-backup.service" "$repo_dir/templates/systemd/excalidraw-backup.timer" "$SERVER_HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now excalidraw-backup.timer
