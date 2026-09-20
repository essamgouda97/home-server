# Local non-English movie matching

## Decision (19 September 2026)

Use the existing ODS Qwen3.5 4B model to assess Arabic titles, transliterations and
catalog aliases. Keep inference on the server, separate from download authority.
This is a callable **search-only helper**, not yet a Radarr pre-search integration.
Ordinary Radarr searches still have release parsing limitations documented in
[media-hardlinks.md](media-hardlinks.md). The helper supports Arabic normalization;
other languages require their own live validation before claiming equivalent support.

Run on the server:

```sh
cd ~/workspace/home-server
python3 scripts/search-nonenglish-movie.py --tmdb-id 1329071
```

Agents can invoke this command over SSH. It needs no new public route or secret,
uses existing local Radarr/Prowlarr API credentials internally, and queries only
the selected enabled indexer (ArabP2P by default).

## Data flow and boundaries

1. Resolve the supplied TMDB ID through Radarr's catalog lookup. Retain title,
   original title, aliases, year, TMDB ID and IMDb ID.
2. Search Prowlarr using original and English titles, without the release year:
   at most two tracker queries. Retain release titles and seeder counts only.
3. Rank exact catalog-title/year evidence first; evaluate at most 24 candidates.
4. Send sanitized titles and catalog metadata to loopback
   `http://127.0.0.1:11434/v1/chat/completions`. No API credentials, download URLs,
   tracker account data, media files or media directory listings enter the prompt.
5. Require structured JSON covering every supplied candidate ID exactly once.
   Reject malformed, duplicate, unknown or incomplete classifications. Inference
   has a 90-second timeout, a 1,600-token limit and no cloud fallback.
6. Recommend review only when the model says `same`, a full normalized catalog
   title/alias occurs in the release, and its year is within one year of catalog.
   These checks are supporting evidence, **not proof of identity**. All decisions
   have `automatic_download_allowed: false`.

A one-year tolerance covers possible festival/theatrical discrepancies without
rewriting catalog metadata. Wrong movies, collections and prompt injection remain
possible model errors: the helper has no tool execution or download capability.

Reports (including public result titles) are private, mode 0600:
`~/.local/state/home-server-maintenance/media-matcher/<tmdb-id>.json`.
Standard output reports counts and timings only. Calls share the existing ODS GPU;
there is no background poller or persistent model load added by this helper.

## Tests and future integration

```sh
python3 -m unittest discover -s services/media-matcher -v
```

Tests cover Arabic normalization, title/year evidence, prompt field whitelisting,
URL filtering, and strict response validation. Live testing must additionally check
actual ODS inference; a passing model health endpoint alone is insufficient.

Live validation on 19 September 2026: the supplied TMDB ID returned 36 deduplicated
indexer results; 24 were evaluated in 10.14 seconds, yielding three candidates for
review. The first unconstrained response omitted candidates and was rejected.
Adding explicit array cardinality to the JSON schema produced complete coverage.
No downloads, requests, or private media reads were performed.

A future Torznab adapter could expose verified candidates to normal Radarr searches.
That adapter is **proposed**, not deployed. It must preserve release identity,
quality, language, credentials, seeding policy and human review for ambiguity.
Do not fabricate release names or IDs merely to bypass Radarr rejection.

## Editable architecture

[Media architecture — Arabic matching & storage](https://draw.home.egouda.xyz/?board=mu9d1x4q9jb77fsrde)
contains the local inference boundary, proposed adapter, and deployed hardlink /
seeding decisions. All 20 elements were read back through the authenticated Draw API.
Publisher: `scripts/publish-media-architecture.py`; existing board edits are preserved.
The standing requirement to update architecture diagrams is in `AGENTS.md` and
`MEMORY.md`.
