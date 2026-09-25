# Metrics

Open **https://metrics.home.egouda.xyz/**. Username `egouda`; password in the
1Password item **Home Server — metrics**. At home use ordinary Wi-Fi. Away from
home connect Tailscale first and use the same URL. No public endpoint was created.

Grafana opens the provisioned **Home Server · Health & Metrics** dashboard:

- CPU, available RAM, GPU utilization/temperature;
- disk usage and available bytes for OS, home, var, SSD and HDD;
- running/healthy containers, per-container CPU/RAM/network and restarts;
- every catalog app's HTTPS availability and response time;
- aggregate torrent count, active uploads, peer demand, outstanding ratio count,
  upload rate and retention-policy health, without titles, hashes or tracker data;
- active Prometheus alert counts/details for low disk, memory pressure, stopped or
  unhealthy containers, unavailable services, and stale metrics collection.

A reachable login page (including HTTP 401) means the service is responding; it
is not proof that media playback, requests, or app-specific workflows succeed.
No notification destination has been configured: alerts are visible in Grafana.
Internal databases/worker containers appear in metrics but do not receive fake
browser links in Homarr. Expected one-shot initialization containers are excluded.
Torrent alerts report telemetry failure, ratio/retention policy drift, or peer
demand with no upload for six hours. The last condition is a diagnostic signal,
not proof that a tracker or an individual torrent is broken.

## Reproduce and maintain

1. Save a unique `metrics` credential using the [password workflow](security-hardening.md).
2. Sync this repository and run `python3 scripts/prepare-monitoring.py` on the server.
3. Run `python3 scripts/check-monitoring.py` after the first minute of collection.
4. Run `python3 scripts/sync-service-catalog.py` to reconcile the Homarr tile.

`compose.monitoring.yml` runs digest-pinned Grafana, Prometheus and Node Exporter.
Prometheus/exporter have no host-published ports and use an internal-only Docker
network. Grafana also joins the existing proxy network; its only browser entry is
NPM HTTPS. No monitoring container receives the Docker socket. A user systemd timer
runs `collect-home-metrics.py` once a minute, publishing selected Docker/host values
to Node Exporter's read-only textfile input. Node Exporter reads host proc/sys/root
read-only and drops all capabilities. Exported values contain no passwords or logs.

Prometheus stores at most **30 days / 2 GB** (whichever limit is reached first) on
SSD `/srv/mergerfs/ssd/monitoring/prometheus`. Grafana state lives alongside it.
Container memory limits total 1.6 GiB; actual usage is normally lower. Grafana state
is included in configuration backups; historical metric samples are excluded.

Use `systemctl --user status home-server-metrics.timer` and
`docker compose -f compose.monitoring.yml ps` for status. Dashboard JSON, datasource,
alerts and collector are versioned under `config/monitoring` and `scripts`.

Browser access first uses the shared [sign-in gateway](authentication.md), then
Grafana's native login. Both sessions are exercised by `check-monitoring.py`.
The Mac vault check uses `vault.py --with-gateway exec metrics -- python3
scripts/check-metrics-from-vault.py`, explicitly injecting the two required
credentials. Desktop authorization is required by 1Password.


## Shared Workspace — 24 September 2026

[Shared Workspace dashboard](https://metrics.home.egouda.xyz/d/shared-workspace)
uses the existing `home-prometheus` datasource. All 24 panels were verified with
an actual Grafana HTTPS login and live queries. Independent
`home-workspace-metrics.timer` publishes aggregate application, document, key,
script, storage and freshness metrics through the existing textfile collector.
Existing host/container metrics provide CPU, memory, load and restart information.
The collector prefers IPv4 for the deliberately IPv6-blocked host's public probes.

`workspace-alerts.yml` adds availability, telemetry, script failure and backup-age
alerts without replacing existing rules. Nightly consistent backups expose their
last verified success; they are local snapshots, not off-server disaster recovery.
No document titles/content, monetary values, usernames or credentials enter these
metrics. See [Workspace operations](shared-workspace.md) and its
[architecture/flow board](https://draw.home.egouda.xyz/?board=muggkm91mb1c1gre3qp).
