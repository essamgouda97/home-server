# Footage organization and edit preparation

The owner's 2026-09-14 clarification makes clean **data clustering** a central
requirement: the library must help them find and assemble a video, not merely
store camera files. The flow below is the proposed server-side follow-on to the
Pi importer. Clustering, its review UI, proxy delivery and Resolve integration are
not installed yet.

## End-to-end workflow

1. Create a project with a short creative brief, target duration and aspect ratio.
   Name the shoot/session when importing a card; preserve that explicit choice.
2. The Pi mounts the selected camera card read-only and transfers its files to the
   home server. It resumes partial uploads, checks source/server SHA-256, refuses
   conflicts and records a completion manifest. It never erases camera media.
3. Server workers use completed manifests to index originals and generate previews,
   contact sheets, transcripts and editing proxies. Never index an upload as ready
   simply because a partially copied filename appeared in the inbox.
4. Present the library primarily as **project → shoot/session → scene**, combining
   relevant footage from both cameras. Expose camera, subject, shot role, quality
   suggestions and favourites as filters/collections within that hierarchy.
5. The owner reviews proposed groups and selects clip ranges. Codex uses the brief,
   group descriptions, transcripts, representative frames and approved selects to
   prepare versioned rough cuts and an OTIO handoff.
6. Resolve opens the organized material and rough-cut timeline on the Mac. Local
   proxies support responsive editing; original media remains on the server for
   relinking/full-quality delivery. The owner finishes pacing, grading and sound.

## Clustering contract

- **Group by meaning, keep source identity.** A Riverbank scene may contain a
  drone establishing shot, Pocket walking footage and water close-ups. Camera
  folders are ingest provenance, not the main editing experience.
- **Separate events from subjects.** Two river trips on different days stay in
  separate sessions, while both can appear under the searchable subject `river`.
- **Combine evidence.** Use capture timestamps, camera metadata and location when
  available; add visual similarity and transcript context. Timestamp/GPS data can
  be missing or wrong, so suggested membership must not masquerade as certainty.
- **Support subclips and multiple memberships.** A long recording may contain
  several scenes. Groups reference precise source ranges, and the same range can
  be part of a scene, a B-roll collection and the owner's favourites.
- **Keep suggestions editable.** Allow rename, merge, split, move membership and
  pin/lock user assignments. Re-indexing must preserve manual decisions. Put
  uncertain material in a visible review queue instead of silently misfiling it.
- **Do not move or duplicate originals to implement clusters.** Keep the verified
  `Projects/<project>/Originals/<card>/...` storage layout and original filenames.
  Catalog entries/sidecars reference stable media IDs, SHA-256, paths and time ranges.
- **Distinguish duplicate types.** Exact byte duplicates can be identified by
  SHA-256. Similar takes, alternate angles and near-duplicates are suggestions for
  review; never automatically delete them or substitute one for another.
- **Make the handoff editable.** Preserve scene/collection information in Resolve
  bins, markers or subclips as supported by the importer. Keep successive rough
  cuts as new timelines; do not modify the live project database directly.

Example browsing view (logical collections, not physical folder moves):

```text
River Trip
  Saturday afternoon
    Arrival       — Pocket approach, drone establishing shot
    Riverbank     — aerials, water details, walking shots
    Sunset        — wide views, silhouettes
  Filters: camera · subject · shot role · favourites · needs review
```

The first useful release should provide trustworthy project/session grouping,
cross-camera scene suggestions, explicit review controls and a selects collection.
More sophisticated automatic story structure follows after evaluating real footage.
Keep infrastructure and catalog schema in Git; keep footage, private GPS metadata,
transcripts, generated previews and the runtime catalog outside the public repo.
