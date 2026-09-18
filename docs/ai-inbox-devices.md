# Send photos, screenshots and scans to AI Inbox

AI Inbox is a top-level folder in [Local Drive](https://files.home.egouda.xyz/files/AI%20Inbox/), next to Creative and Scans. Its SSD backing directory is `/srv/mergerfs/ssd/drive/AI Inbox`, beside the Creative directory. The web folder and SMB share are two views of the same files. No sync copy or public link is involved. Owner access only.

## iPhone

**Fewest setup steps:** Open the AI Inbox link in Safari, sign in with the normal home gateway, then use Safari's Share menu → **Add to Home Screen**. Open that icon and use Local Drive's upload action to choose a photo or screenshot. This works on home Wi-Fi; away from home, connect Tailscale first.

**Native Files/share-sheet path:** In Files, tap Browse → More → Connect to Server and enter `smb://home-server.lan` (or `smb://10.0.0.182` if local DNS is unavailable). Choose Registered User `egouda` with the existing Samba credential, then open the **AI Inbox** share. In Photos or the screenshot thumbnail, use Share → Save to Files → Shared → AI Inbox. The SMB credential is separate from the browser gateway login and can be saved by iOS after the first connection. Keep Tailscale connected when away from home. Apple Files can also scan documents from within a folder; the Brother printer's [Scan to PDF](https://print.home.egouda.xyz/documents/) is already integrated and saves to top-level Scans in the web drive.

## Mac

Open Finder → Go → Connect to Server and connect to `smb://home-server.lan/AI%20Inbox`. Drag a file or the floating screenshot thumbnail into that Finder window when you want to share it with an agent. For a dedicated screenshot workflow, press Shift-Command-5, choose **Options → Other Location**, and pick the mounted AI Inbox; this changes where subsequent screenshots are saved, so use it only if you want every capture sent there. The browser upload link works without an SMB mount.

## Agent use and limits

In a new Codex session, say “open my latest AI Inbox photo” or provide the file name. The owner-only `home-knowledge` MCP lists new files immediately and can preview JPEG, PNG, WebP, HEIC/HEIF and PDF pages. Text search refreshes on the scheduled index run. Other LLM apps need their own connector; placing a file in AI Inbox does not insert it into an existing chat automatically. See [home knowledge](home-knowledge.md).

The web route uses central sign-in. The native SMB route uses the existing Samba account and SMB3 encryption; it is never exposed through a public share or router port forwarding. If a mobile file picker does not offer the connected SMB share, use the Safari Home Screen shortcut instead.
