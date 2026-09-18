# Home knowledge search

`home-knowledge.py` gives the owner one read-only retrieval tool for agents. It runs
on `home-server`, stores a private SQLite full-text and local-embedding index under
`~/.local/share/home-server/knowledge/index.sqlite3`, and uses the existing ODS
`BAAI/bge-base-en-v1.5` embedding server bound to loopback. It does not call a
hosted embedding API or need an LLM to index content. Codex generates answers from
retrieved excerpts and should cite the original link, not the index as authority.

This is the first working slice of cross-app search. It indexes repository README
and docs, registered service names/URLs/access class, and text from active Draw
boards, owner-selected AI Inbox uploads, and completed Brother scans. It does
**not** yet index other Creative/Local Drive files, Life Dashboard, Jellyfin,
Requests, Home Assistant, mail, chats, video, or other app databases.
Do not describe it as a complete memory of the owner. In particular, a missed
result is not evidence that the information is absent from the original app.

## Privacy boundary

The index is owner-only: mode 700 directory and mode 600 database, accessed via
owner SSH and a stdio MCP process. There is no HTTP endpoint or household grant.
Do not mount or expose this database through a browser service. Never index
`~/.config/home-server/secrets`, 1Password, auth caches, `.env`, backups, agent
memory, private user homes, or a household member's content by default. The repo
crawler uses an explicit README/docs allowlist and drops lines that look like
secrets. Draw is currently an owner-only app; preserve that entitlement before
expanding its source. A regex filter is not a data-loss-prevention guarantee:
review new connectors and their sample output before enabling them.

Source IDs and URLs accompany each result. Deleted boards/elements or documents
are removed on the next sync; changed text is re-embedded. Source databases remain
authoritative. The index can be deleted and rebuilt without deleting originals.

## Send a photo or scan from any device

See the [device setup guide](ai-inbox-devices.md) for iPhone Files, a Home Screen
shortcut, and Mac screenshot options.

- On a phone or computer, open [Local Drive → AI Inbox](https://files.home.egouda.xyz/files/AI%20Inbox/) and upload a photo, PDF or text file. The owner sign-in is required. This is an ordinary SSD folder, not a public share.
- For a paper document, use [Brother · Documents](https://print.home.egouda.xyz/documents/) → **Scan to PDF**. Completed scans appear in Local Drive → Scans; partial scans are excluded.
- In a Codex session, ask for the latest AI Inbox item or scan. The agent can call `list_home_attachments` immediately and `open_home_attachment` to view a photo or PDF page. Searchable text arrives on the next index sync. Image-only PDFs can be viewed page by page but do not yet have OCR text.

AI Inbox and Scans are top-level Local Drive folders. Their backing directories
are `/srv/mergerfs/ssd/drive/AI Inbox` and `/srv/mergerfs/ssd/drive/Scans`,
alongside `Creative` in the drive. `drive/Creative` points to the existing SSD
Creative directory so established app mounts keep working. The old
`Creative/Scans` path is a temporary scanner compatibility symlink. The file
stays in Local Drive and is available from every device through the same
private HTTPS address. Each LLM application needs its own MCP integration or a
supported file picker; uploading here does not automatically inject the image
into every existing chat session. The current Codex integration is the tested
path. No public share link is created.

## Install and operate

### Existing server migration

When upgrading from the earlier `Creative/AI Inbox` and `Creative/Scans` layout,
create the drive root with
`sudo install -d -m 700 -o egouda -g egouda /srv/mergerfs/ssd/drive`.
Run `python3 scripts/move-drive-inbox.py` as a preflight. Then stop File Browser,
Samba and `home-print-documents`; run
`python3 scripts/move-drive-inbox.py --apply` on the server before recreating
those containers. The script makes a verified private backup outside Git and
keeps `Creative/Scans` as a scanner compatibility symlink. It refuses an active
scan or an occupied destination. The direct top-level Local Drive folders use
the new SSD paths. Restart only the three affected containers and verify the
HTTPS folder, an SMB upload, and a completed scan listing.

On the server, after updating the repository:

The host needs Python SQLite FTS5, Pillow (`python3-pil`), and Poppler
(`poppler-utils`). The current server has all three. HEIC/HEIF previews use a
small, isolated Python environment with pinned dependencies.

```sh
cd ~/workspace/home-server
install -d -m 700 '/srv/mergerfs/ssd/drive/AI Inbox'
install -d -m 700 '/srv/mergerfs/ssd/drive/Scans'
install -d -m 700 ~/.local/share/home-server/knowledge
python3 -m venv ~/.local/share/home-server/knowledge/venv
~/.local/share/home-server/knowledge/venv/bin/python -m pip install -r config/knowledge/requirements.txt
python3 scripts/test-home-knowledge.py
python3 scripts/home-knowledge.py sync
python3 scripts/home-knowledge.py search 'where are Draw boards stored' --limit 3
install -m 644 templates/systemd/home-knowledge.service ~/.config/systemd/user/
install -m 644 templates/systemd/home-knowledge.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now home-knowledge.timer
```

To use from Codex on the Mac:

```sh
codex mcp add home-knowledge -- ssh -T home-server \
  /usr/bin/python3 /home/egouda/workspace/home-server/scripts/home-knowledge.py mcp
```

Codex on the server can register the same MCP command with `/usr/bin/python3`
without SSH. New Codex sessions see `search_home_knowledge`,
`read_home_knowledge`, `list_home_attachments`, and `open_home_attachment`.
Search returns a small excerpt, source, URL, and source update time. Read expands
a single ID. The attachment tools list files live and return scaled previews.
All tools are read-only; they cannot modify
source apps or grant access. If the embedding service is unavailable, searches
still use SQLite full-text, and syncing waits for embeddings rather than silently
writing a partially semantic index. To rebuild from scratch, move the SQLite file
and its WAL/SHM siblings to a private maintenance backup outside Git, then sync.

## Adding another app

Implement a source generator in `home-knowledge.py` yielding stable ID, source,
name, original HTTPS URL, plain-text content, and update time. It must use the
app's supported read API or a consistent read-only database snapshot. Keep per-user
content separate and enforce source permissions before retrieval. Store only
searchable text/metadata, never entire media files or credentials. Test source
updates, deletions, sensitive-field omission, and citations, then add the source to
`sync()`. Do not add a household-facing route until per-user authorization can be
proved independently of the index.
