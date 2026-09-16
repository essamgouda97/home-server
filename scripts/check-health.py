#!/usr/bin/env python3
"""Read-only network checks; --local adds container and authenticated app health."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

SERVICES = {
    "life": (None, "/", {401}),
    "files": (8082, "/", {200}),
    "assistant": (8123, "/", {200, 302}),
    "home": (3000, "/", {200, 302, 307}),
    "jellyfin": (8096, "/System/Info/Public", {200}),
    "vue": (8097, "/", {200}),
    "sonarr": (8989, "/", {200, 302, 401}),
    "radarr": (7878, "/", {200, 302, 401}),
    "requests": (5055, "/", {200, 302, 307}),
    "torrents": (15080, "/", {200, 401}),
    "prowlarr": (9696, "/", {200, 302}),
    "status": (3001, "/", {200, 302}),
    "portainer": (9000, "/", {200}),
    "nzbget": (6789, "/", {200, 401}),
    "speedtest": (8765, "/", {200, 302}),
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


PRIVATE_PORTS = {8082, 3000, 8097, 8989, 7878, 5055, 15080, 9696, 3001, 9000, 6789, 8765}


def http_check(item, host, local=False):
    name, (port, path, expected) = item
    result = []
    opener = urllib.request.build_opener(NoRedirect)
    checks = [(f"{name}: proxy", f"http://{host}{path}", {"Host": f"{name}.lan"})]
    if port in PRIVATE_PORTS and not local:
        try:
            with socket.create_connection((host, port), timeout=2):
                result.append((False, f"{name}: private backend", "direct LAN port is exposed"))
        except (OSError, TimeoutError):
            result.append((True, f"{name}: private backend", "direct LAN port closed"))
    elif port is not None:
        direct_host = "127.0.0.1" if port in PRIVATE_PORTS else host
        checks.insert(0, (f"{name}: direct", f"http://{direct_host}:{port}{path}", {}))
    for label, url, headers in checks:
        try:
            try:
                with opener.open(urllib.request.Request(url, headers=headers), timeout=8) as response:
                    code = response.status
            except urllib.error.HTTPError as error:
                code = error.code
            result.append((code in expected, label, f"HTTP {code}"))
        except (OSError, urllib.error.URLError) as error:
            result.append((False, label, str(error)))
    return result


def dns_check(host, tcp=False):
    ident = os.urandom(2)
    query = ident + struct.pack("!5H", 0x100, 1, 0, 0, 0) + b"\x04home\x03lan\0\0\x01\0\x01"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM) as sock:
        sock.settimeout(5)
        sock.connect((host, 53))
        if tcp:
            sock.sendall(struct.pack("!H", len(query)) + query)
            def receive(size):
                chunks = b""
                while len(chunks) < size:
                    chunk = sock.recv(size - len(chunks))
                    if not chunk:
                        raise OSError("Incomplete DNS response")
                    chunks += chunk
                return chunks
            data = receive(struct.unpack("!H", receive(2))[0])
        else:
            sock.send(query)
            data = sock.recv(4096)
    valid = len(data) >= 12 and data[:2] == ident and data[3] & 15 == 0
    valid = valid and struct.unpack("!H", data[6:8])[0] > 0 and socket.inet_aton(host) in data[12:]
    return valid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("SERVER_IP", "10.0.0.182"))
    parser.add_argument("--local", action="store_true", help="Run on the server to inspect local state")
    args = parser.parse_args()
    failures = 0
    def report(ok, name, detail):
        nonlocal failures
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")
    for tcp in [False, True]:
        try:
            report(dns_check(args.host, tcp), f"DNS {'TCP' if tcp else 'UDP'}", f"home.lan -> {args.host}")
        except OSError as error:
            report(False, "DNS", str(error))
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        for rows in pool.map(lambda item: http_check(item, args.host, args.local), SERVICES.items()):
            for row in rows:
                report(*row)
    if args.local:
        ids = subprocess.check_output(["docker", "compose", "--env-file", "server.conf", "--env-file", ".env", "ps", "-aq"], text=True).split()
        report(bool(ids), "Compose inventory", f"{len(ids)} containers")
        if ids:
            for container in json.loads(subprocess.check_output(["docker", "inspect", *ids])):
                state = container["State"]
                health = state.get("Health", {}).get("Status", "no healthcheck")
                report(state["Running"] and health not in ["unhealthy", "starting"], container["Name"], f"{state['Status']}; {health}")
        data_root = Path(os.environ.get("SERVER_DATA_DIR", "/mnt/server"))
        for name, folder, port, version in [("sonarr", "sonarr/data", 8989, 3), ("radarr", "radarr/config", 7878, 3), ("prowlarr", "prowlarr/data", 9696, 1)]:
            try:
                key = ET.parse(data_root / folder / "config.xml").findtext("ApiKey")
                request = urllib.request.Request(f"http://127.0.0.1:{port}/api/v{version}/health", headers={"X-Api-Key": key})
                with urllib.request.urlopen(request, timeout=8) as response:
                    issues = json.load(response)
                for issue in issues:
                    if issue["type"] == "error":
                        report(False, f"{name} app health", issue["message"])
                    else:
                        print(f"WARN {name}: {issue['message']}")
                if not issues:
                    report(True, f"{name} app health", "no warnings")
            except (OSError, ET.ParseError, urllib.error.URLError) as error:
                report(False, f"{name} app health", str(error))
        for mount in ["/", "/home", "/var", "/srv/mergerfs/hdd", "/srv/mergerfs/ssd"]:
            usage = shutil.disk_usage(mount)
            percent = usage.used / usage.total * 100
            report(percent < 95, f"disk {mount}", f"{percent:.0f}% used")
        result = subprocess.run(["codex", "login", "status"], capture_output=True, text=True)
        report(result.returncode == 0, "Codex login", (result.stdout + result.stderr).strip())
        result = subprocess.run(["docker", "exec", "codex-home", "codex", "login", "status"], capture_output=True, text=True)
        report(result.returncode == 0, "Codex Assist login", (result.stdout + result.stderr).strip())
    print(f"\n{failures} failing checks. HTTP 401 means authentication is required; endpoint checks do not verify playback or downloads.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
