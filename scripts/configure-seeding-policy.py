#!/usr/bin/env python3
"""Preserve completed torrent jobs and apply the home-server seed policy.

Run on the server. Credentials and API keys are read from private runtime files and
are never printed. The script is idempotent and writes a non-secret rollback record
outside Git before changing anything.
"""

from __future__ import annotations

import datetime as dt
import http.cookiejar
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


QBIT_URL = "http://127.0.0.1:15080"
SERVARR = {
    "radarr": ("http://127.0.0.1:7878", Path("/mnt/server/radarr/config/config.xml")),
    "sonarr": ("http://127.0.0.1:8989", Path("/mnt/server/sonarr/data/config.xml")),
}
POLICY = {
    "max_ratio_enabled": True,
    "max_seeding_time_enabled": False,
    "max_inactive_seeding_time_enabled": False,
    "max_ratio": 2.0,
    "max_ratio_act": 0,  # pause; never delete content or torrent metadata
    "max_active_uploads": 20,
    "max_active_torrents": 50,
    "dont_count_slow_torrents": True,
}


def request_json(url: str, *, headers=None, data=None, method=None):
    encoded = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(
        url,
        data=encoded,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        body = response.read()
    return json.loads(body) if body else None


def qbit_session():
    secret_path = Path.home() / ".config/home-server/secrets/service-passwords.json"
    password = json.loads(secret_path.read_text())["torrents"]
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    data = urllib.parse.urlencode({"username": "egouda", "password": password}).encode()
    req = urllib.request.Request(
        QBIT_URL + "/api/v2/auth/login",
        data=data,
        headers={"Origin": QBIT_URL, "Referer": QBIT_URL + "/"},
    )
    with opener.open(req, timeout=30) as response:
        body = response.read()
        if response.status not in (200, 204) or body not in (b"Ok.", b""):
            raise RuntimeError("qBittorrent rejected the runtime recovery credential")
    return opener


def main():
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = Path.home() / ".local/state/home-server-maintenance/seeding-policy" / stamp
    backup_dir.mkdir(parents=True, mode=0o700)
    os.chmod(backup_dir, 0o700)
    rollback = {"createdAt": stamp, "qBittorrent": {}, "servarr": {}}

    opener = qbit_session()
    with opener.open(QBIT_URL + "/api/v2/app/preferences", timeout=30) as response:
        prefs = json.load(response)
    rollback["qBittorrent"] = {key: prefs.get(key) for key in POLICY}

    servarr_clients = {}
    for name, (base, config_path) in SERVARR.items():
        api_key = ET.parse(config_path).getroot().findtext("ApiKey")
        headers = {"X-Api-Key": api_key}
        clients = request_json(base + "/api/v3/downloadclient", headers=headers)
        servarr_clients[name] = (base, headers, clients)
        rollback["servarr"][name] = []
        for client in clients:
            if client.get("protocol") != "torrent" and client.get("implementation") != "QBittorrent":
                continue
            rollback["servarr"][name].append(
                {"id": client["id"], "removeCompletedDownloads": client.get("removeCompletedDownloads")}
            )

    backup = backup_dir / "rollback.json"
    backup.write_text(json.dumps(rollback, indent=2, sort_keys=True) + "\n")
    os.chmod(backup, 0o600)

    payload = urllib.parse.urlencode({"json": json.dumps(POLICY)}).encode()
    with opener.open(
        urllib.request.Request(QBIT_URL + "/api/v2/app/setPreferences", data=payload),
        timeout=30,
    ) as response:
        if response.status != 200:
            raise RuntimeError("qBittorrent policy update failed")

    for name, (base, headers, clients) in servarr_clients.items():
        changed = 0
        for client in clients:
            if client.get("protocol") != "torrent" and client.get("implementation") != "QBittorrent":
                continue
            if client.get("removeCompletedDownloads"):
                client["removeCompletedDownloads"] = False
                request_json(
                    base + f"/api/v3/downloadclient/{client['id']}",
                    headers=headers,
                    data=client,
                    method="PUT",
                )
                changed += 1
        print(f"PASS {name}: completed torrents retained ({changed} setting changes)")

    print("PASS qBittorrent: ratio 2.0 pauses completed seeds; no automatic deletion")
    print("PASS queue: up to 20 active uploads and 50 active torrents; slow seeds do not block the queue")
    print(f"Rollback metadata saved privately under {backup_dir}")


if __name__ == "__main__":
    main()
