#!/usr/bin/env python3
"""Title-free audit of torrent retention, ratios, demand and tracker health."""

from __future__ import annotations

import collections
import http.cookiejar
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


QBIT_URL = "http://127.0.0.1:15080"
EXPECTED = {
    "max_ratio": 2.0,
    "max_ratio_act": 0,
    "max_active_uploads": 20,
    "max_active_torrents": 50,
    "dont_count_slow_torrents": True,
}
SERVARR = {
    "radarr": ("http://127.0.0.1:7878", Path("/mnt/server/radarr/config/config.xml")),
    "sonarr": ("http://127.0.0.1:8989", Path("/mnt/server/sonarr/data/config.xml")),
}


def get_json(url, headers=None, opener=None):
    req = urllib.request.Request(url, headers=headers or {})
    open_url = opener.open if opener else urllib.request.urlopen
    with open_url(req, timeout=30) as response:
        return json.load(response)


def qbit_session():
    password_file = Path.home() / ".config/home-server/secrets/service-passwords.json"
    password = json.loads(password_file.read_text())["torrents"]
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    data = urllib.parse.urlencode({"username": "egouda", "password": password}).encode()
    req = urllib.request.Request(QBIT_URL + "/api/v2/auth/login", data=data)
    with opener.open(req, timeout=30) as response:
        if response.read() not in (b"Ok.", b""):
            raise RuntimeError("qBittorrent login failed")
    return opener


def main():
    failures = []
    opener = qbit_session()
    prefs = get_json(QBIT_URL + "/api/v2/app/preferences", opener=opener)
    for key, wanted in EXPECTED.items():
        if prefs.get(key) != wanted:
            failures.append(f"qBittorrent {key}={prefs.get(key)!r}; expected {wanted!r}")

    torrents = get_json(QBIT_URL + "/api/v2/torrents/info", opener=opener)
    states = collections.Counter(row.get("state", "unknown") for row in torrents)
    below = sum(1 for row in torrents if row.get("progress", 0) >= 1 and row.get("ratio", 0) < 2)
    uploading = sum(1 for row in torrents if row.get("upspeed", 0) > 0)
    demand = sum(1 for row in torrents if row.get("num_leechs", 0) > 0)
    categories = collections.Counter(row.get("category") or "uncategorized" for row in torrents)
    print(f"INFO torrents={len(torrents)} uploading={uploading} with_demand={demand} complete_below_ratio={below}")
    print("INFO states=" + json.dumps(states, sort_keys=True))
    print("INFO categories=" + json.dumps(categories, sort_keys=True))

    metadata = Path("/mnt/server/qbittorrent/config/qBittorrent/BT_backup")
    print(f"INFO retained_metadata={len(list(metadata.glob('*.torrent')))}")

    for name, (base, config_path) in SERVARR.items():
        api_key = ET.parse(config_path).getroot().findtext("ApiKey")
        clients = get_json(base + "/api/v3/downloadclient", {"X-Api-Key": api_key})
        torrent_clients = [
            c for c in clients
            if c.get("protocol") == "torrent" or c.get("implementation") == "QBittorrent"
        ]
        if not torrent_clients:
            failures.append(f"{name} has no torrent download client")
        for client in torrent_clients:
            if client.get("removeCompletedDownloads"):
                failures.append(f"{name} still removes completed torrent jobs")
        print(f"PASS {name}: {len(torrent_clients)} torrent client(s) retain completed jobs")

    if failures:
        for failure in failures:
            print("FAIL " + failure)
        return 1
    print("PASS seeding policy and retention settings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
