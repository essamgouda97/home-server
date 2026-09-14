# Domain documentation

This is a single infrastructure repository. Use README.md for the service model,
server.conf for host settings, and docs/server-operations.md for observed state,
operations, and recovery. There is currently no CONTEXT.md or docs/adr directory.

The host runs Docker media/infrastructure services. The proxy Docker network
provides stable internal service names. The router reserves the host's LAN IP.
dnsmasq serves .lan names; Nginx Proxy Manager routes them to Docker services.
Codex runs as egouda on the host. OpenClaw/Servo is intentionally disabled.
