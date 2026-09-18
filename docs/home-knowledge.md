# Home knowledge search

`home-knowledge.py` gives the owner one read-only retrieval tool for agents. It runs
on `home-server`, stores a private SQLite full-text and local-embedding index under
`~/.local/share/home-server/knowledge.sqlite3`, and uses the existing ODS
`BAAI/bge-base-en-v1.5` embedding server bound to loopback. It does not call a
hosted embedding API or need an LLM to index content. Codex generates answers from
retrieved excerpts and should cite the original link, not the index as authority.

This is the first working slice of cross-app search. It indexes repository README
and docs, registered service names/URLs/access class, and text from active Draw
boards. It does **not** yet index files in Creative/Local Drive, Life Dashboard,
Jellyfin, Requests, Home Assistant, mail, chats, photos, video, or app databases.
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

## Install and operate

On the server, after updating the repository:

```sh
cd ~/workspace/home-server
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
without SSH. New Codex sessions see `search_home_knowledge` and
`read_home_knowledge`. Search returns a small excerpt, source, URL, and source
update time. Read expands a single ID. Both are read-only; they cannot modify
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
