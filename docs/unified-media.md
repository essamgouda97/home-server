# Unified household media

For step-by-step family and device setup, use the
[household onboarding runbook](household-onboarding.md).

## Target experience

Moonfin is the selected additive client trial: search/discover, request, monitor
request downloads and play the existing Jellyfin library in one app. Keep Sonarr,
Radarr and qBittorrent for automation and advanced owner maintenance. Fine-grained
release/torrent selection inside the TV app has not been verified.

Official sources: [Moonfin](https://moonfin.io/),
[Google Play](https://play.google.com/store/apps/details?id=org.moonfin.androidtv),
[Moonbase 2.2.0 source](https://github.com/Moonfin-Client/Plugin/tree/2.2.0),
[client 2.5.1 request-progress release](https://github.com/Moonfin-Client/Moonfin-Core/releases/tag/2.5.1).
This preserves media files, watch history and existing household profiles rather
than migrating the entire media stack. Alternative SeerrTV hands playback to a
separate player, so it does not meet the single-app goal as directly.

## Deployment state — September 16, 2026

- Jellyfin 10.11.11 active; stopped full configuration backup verified before patch.
- Moonbase plugin 2.2.0.0 active; fixed release ZIP SHA-256 checked by
  `scripts/configure-moonfin.py` before extraction.
- Settings sync enabled; Seerr URL is internal `http://jellyseerr:5055`.
- WebRTC LAN scanning disabled. No new public port or external tunnel.
- Owner request session connected to existing Jellyseerr profile ID 1; verified
  `/Moonfin/Seerr/Api/auth/me` through a real user session. Test Jellyfin token revoked.
- Jellyseerr 2.7.3 does not support the plugin's passwordless Quick Connect bridge:
  returned `sso_unsupported`. Initial native request sign-in currently remains.
  The session is retained server-side per Jellyfin user. Do not claim passwordless
  household request enrollment until a compatible Seerr migration is tested.
- Mariam's existing ID, password verifier and request permissions checked unchanged.
  Her Moonfin request session and interactive TV playback are not yet verified.
- Moonfin on the basement Google TV Streamer was installed by the owner and its
  Quick Connect code was redeemed for `egouda`. Jellyfin reported one active
  Moonfin TV session for that existing profile.

## Basement TV

Discovery: Google TV Streamer named **Basement TV**, mDNS ID
`568bcdda8c703201efebf50702dfe95f`, current DHCP IP `10.0.0.173`.
No authorized ADB connection or wireless-debugging discovery; port 5555 closed.
The owner installed Moonfin from Google TV Apps. ADB was not enabled. The TV
connected with Quick Connect as `egouda`; `mgouda` remains a separate future
profile on this shared device.

Native client server URL: `http://10.0.0.182:8096` on household LAN.
The HTTPS browser route has a separate browser gateway that a native TV client
cannot necessarily negotiate. Prefer Jellyfin Quick Connect for TV enrollment;
any code approval must be bound to the intended TV and household profile.
Do not sign Mariam into the owner's administrative media profile.

## Private access from either phone, anywhere

Use `https://home-server.tail9bfb3e.ts.net` as Moonfin's server address on both
phones. Keep Tailscale connected on each phone; the same address works at home and
away. Tailscale Serve proxies private HTTPS port 443 to Jellyfin's loopback port
8096. Funnel is **off**, and no router forwarding or public Jellyfin record was
added. On September 16 the Mac received HTTP 200 at `/health` over this address,
and an owner login through the exact HTTPS endpoint minted the existing Jellyfin
identity; its test session was immediately revoked.

The owner phone already appears in the tailnet as `iphone171`. Mariam needs her
own Tailscale account and the *single-use machine share invitation*, not the
owner's account. A machine share exposes only the home server to her separate
tailnet. The live tailnet grant permits shared users to reach only
`100.120.82.22:443`; existing owner grants and SSH policy remain intact. The
share does not export the server's `10.0.0.182/32` subnet route, so Mariam must
use the `*.ts.net` URL above. Her Moonfin user must be `mgouda`; Tailscale device
access and Jellyfin media identity are separate checks.

On iOS, keep Tailscale enabled or enable its VPN On Demand option for cellular and
non-home Wi-Fi. Other VPNs may conflict. For Android, use Android's Always-on VPN
setting if needed. Test each phone with Wi-Fi disabled, open the HTTPS address in
a browser, then connect Moonfin and verify the intended user. Streaming and
requesting must be tested per user; a `/health` response alone is insufficient.

Reproduce the server-side Serve endpoint with `tailscale serve --bg --yes
http://127.0.0.1:8096` after enabling tailnet HTTPS certificates, keeping the
optional public Funnel checkbox **off**. See
[`config/tailscale/media-access.hujson`](../config/tailscale/media-access.hujson)
for the applied tailnet policy. `tailscale serve status --json` should show the
proxy and no Funnel entry. To roll back this remote endpoint without affecting
Jellyfin's LAN clients, run `tailscale serve --https=443 off`. Revoke Mariam's
machine share independently from the Tailscale Machines page when needed.

## Completion checks

Verify TV installed version, intended identity, real playback/audio/subtitles,
request permission, live progress and separate Mariam profile. Verify browser
Moonfin sign-in before promoting it to the primary Homarr media tile. Retain
stock Jellyfin and Requests links during the trial. Add actual deployed paths to
the architecture board and service catalog after those checks.

## Recovery

Moonbase is additive. If it fails, stop Jellyfin, move its plugin directory to
private maintenance storage and restart; keep the existing library and users.
For patch rollback, stop Jellyfin and restore the complete pre-patch config plus
its matching pre-patch image from the maintenance backup. Never run an older
binary against a database migrated by a newer version without its matching backup.
