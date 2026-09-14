# Configuration boundaries and a future NixOS migration

Service definitions are separate from mutable data. This does not install
NixOS, repartition disks, change the bootloader, or claim a tested NixOS deployment.
The current Ubuntu deployment is the working reference.

| Current input | Future NixOS responsibility |
|---|---|
| `server.conf` | Host options for addresses, mounts, timezone, UID/GID |
| `docker-compose.yml` | Compose systemd unit or `virtualisation.oci-containers` |
| `config/samba/smb.conf` | Samba container or native Samba module with matching settings |
| `config/homeassistant/` | Read-only config beside writable application state |
| `config/nginx/creative-home.conf.template` | Reverse proxy with streaming uploads and HA WebSockets |
| `HOME_SERVER_SECRETS_DIR` | Runtime secrets from sops-nix/agenix or private manual provisioning |
| `prepare-creative.sh` and Compose `creative-init` | Filesystems, users/groups and tmpfiles permissions |
| `config/homeassistant/http.json` | Reconcile network settings through the HA API after startup |
| Tailscale authorization | Restore/re-authorize private state and approved route/DNS policy |
| Mac helper scripts | Remain Mac-side; update paths if the checkout moves |

Preserve UID/GID 1000 for creative files, the SSD mount, the media pool's branch
order/policy, and existing service data. Do not put passwords, `.env`, HA
`.storage`, File Browser's database, SMB passdb, or Tailscale state in Git or
the world-readable Nix store. Image digests are pinned for new upstream services
and the Samba base image; Debian package repositories are live, so the Samba
build is not fully bit-for-bit reproducible. Preserve its built image or use
a dated package snapshot if strict rebuild reproducibility becomes necessary.

Migration order:

1. Verify app-state backups and an independent footage backup. Preserve disk
   UUIDs and mount configuration privately.
2. Test the target configuration in a VM with disposable data and alternate IPs.
3. Make data mounts a prerequisite for container startup; a directory on an
   unmounted root filesystem is not evidence the correct disk is present.
4. Restore secrets and state with original permissions before starting services.
   Preserve databases with their corresponding application versions.
5. Verify SMB read/write, web uploads, media health, HA config, GPU access and
   Tailscale routing/DNS before retiring Ubuntu.

Not every Home Assistant integration or pairing is expressible as YAML. Back up
its private state alongside declarative files. Promote reusable automations to
packages/blueprints where useful. Do not hand-edit live `.storage` JSON as a
substitute for supported setup.
