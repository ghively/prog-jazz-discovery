---
name: prog-discovery-weekly
description: "Use when running the weekly Prog & Jazz Discovery playlist."
version: 2.0.0
author: Gene Hively
license: MIT
tags: [music, prog, jazz, playlist, spotify, discovery, weekly]
metadata:
  hermes:
    category: media
    tags: [music, prog, jazz, playlist, spotify, discovery, weekly]
    requires_toolsets: [web, terminal, file, spotify]
---

# Prog & Jazz Discovery — Weekly Playlist (v2: lane architecture)

## When to Use

- The Monday cron `prog-discovery-monday` fires (this skill is attached to it).
- the user asks for "this week's playlist", new prog/jazz discovery, or the pipeline misbehaves.

A replacement for a lapsed music-magazine subscription. Every Monday: build ONE Spotify playlist of ~38 tracks across six lanes, verify every track, record attribution, save edition notes, post the link + blurbs.

**State:** `~/.hermes/prog-discovery/state.json` (week counter, played history, scene wheel)
**Pipeline script:** `scripts/pipeline.py (this repo)` — ALL Spotify mechanics go through it (scene / seeds / verify / publish / selftest). The agent does editorial work only; the script does API loops. This is the v2 core fix for small-model context exhaustion.
**Optional PKM:** replace the Capacities step with your own notes system or drop it
**Cron:** `prog-discovery-monday`, Mon 09:00 America/Chicago, pinned glm-4.7-flash/zai

## The six lanes (weights ARE slot quotas)

| Lane | Slots | Definition |
|---|---|---|
| core-prog | 12 | Symphonic, prog-metal, avant-proper, Crossover Prog — the magazine's heart |
| jazz-fusion | 9 | Fusion, jazztronica, Canterbury-adjacent, modern comps |
| fringe | 9 | Psych, post-rock, kraut-descended, experimental — adjacency to prog/jazz, NOT membership. This lane exists because the interesting music lives BETWEEN the categories |
| scene | 4 | This week's featured scene (rotation wheel in state.json) — any lane's sound, from one geography |
| archive | 2 | Pre-2015 obscure bands the user likely missed |
| wildcard | 2 | **Editor's wildcard** — the two most exciting finds of the week from ANY source, regardless of lane fit. Pure editorial judgment |

**NO listening-history personalization.** the owner explicitly rejected it (2026-08-29): the point of this system is to subvert algorithmic lock-in, not recreate it — played ≠ enjoyed; only saved-to-library counts as an endorsement, and that signal is PARKED (not built, not wanted yet). Selection stays 100% editorial: sources, lanes, quotas.

Hard rules across lanes: max 4 tracks per subgenre tag; no artist repeat within 8 weeks; tracks never repeat; obscurity gate unchanged (skip >500k monthly listeners; borderline 200-500k only if <3 albums; legends never).

## Source → lane map (with per-source caps)

| Source | Lane(s) | Cap/week |
|---|---|---|
| loudersound.com/prog Tracks Of The Week | core-prog | **auto-include all that pass gates** (≤5-8; strongest editorial signal) |
| The Progspace release roundups | core-prog | 4 |
| The PROG Mind (reviews, top-40 lists) | core-prog, archive | 4 |
| The Progressive Subway | core-prog, archive | 3 |
| Arctic Drones roundups | jazz-fusion, fringe | 3 |
| ProgArchives country charts (for scene lane) | scene | 3 |
| r/postrock best-of, A Closer Listen, The Free Jazz Collective | fringe | 4 |
| Bandcamp tags (psych, post-rock, zeuhl, jazz) | fringe, jazz-fusion | 4 |
| Spotify related-artists | (none — personalization REJECTED 2026-08-29; do not use listening history or related-artists-as-preference) | 0 |
| Pre-researched candidate pool (`candidates-*.json`) | RESERVE ONLY | top-up short lanes, never primary feed |

Why the caps: Week 1's de facto weight was ~70% candidate-pool (cheapest to fetch), which flattened diversity. Caps force source breadth; attribution (below) makes it auditable.

## Procedure

### 1. Setup (one terminal call)
```
python3 scripts/pipeline.py (this repo) scene    # this week's featured scene
```
Read state.json for week counter + played history. (Do NOT run `seeds` — listening-history personalization was rejected; the subcommand remains only as a passive likes-recorder for the future catalog, see below.)

### 2. Harvest (≤10 web calls, respect per-source caps)
Fetch sources per the lane map. Write candidates to `~/.hermes/prog-discovery/candidates-week.json`:
```json
[{"artist": "...", "track": "...", "lane": "core-prog", "source": "TOTW"}, ...]
```
Gather MORE than the quotas (aim ~50 candidates) — verification will reject some. If a source is thin/unreachable, move on; never pad with famous bands. The candidate pool file tops up any lane still short after harvest.

### 3. Verify (one pipeline call)
```
python3 scripts/pipeline.py (this repo) verify
```
Writes verified tracks + URIs + attribution to `draft.json`. For failures: swap in new candidates and re-run. Loop until ≥40 verified with lane quotas roughly met (34 usable minimum).

### 4. Select + sequence
From draft.json, pick the final ~38 honoring lane quotas and the max-4-per-subgenre rule. Then SEQUENCE as an arc: energetic opener, alternate prog/jazz/fringe through the middle, mellow close. Write the final ordered list back to draft.json (tracks array in order).

### 5. Publish (one pipeline call)
```
python3 scripts/pipeline.py (this repo) publish
```
Creates the playlist, adds in batches, verifies the count via API, and atomically updates state.json + appends attribution.jsonl ONLY on success. If it refuses (draft < 34) or reports MISMATCH, fix and re-run — do not deliver.

### 6. Capacities + deliver
- Capacities: append edition summary to the daily note (title, URL, track count, lane breakdown, 3-5 blurbs). One Album object per highlighted track if quota allows; fall back to daily-note-only on 429.
- Deliver to the job's origin channel: playlist URL, count, lane breakdown one-liner, 3-5 highlight blurbs. Tight — no wall of text.

## Feedback loop — REMOVED by design (2026-08-29)
the owner explicitly rejected listening-history personalization: this system exists to SUBVERT algorithmic lock-in; editorial sources are the whole point. Played ≠ enjoyed; only a save-to-library is an endorsement, and even that signal is parked. **Never wire listening history, related-artists-as-preference, or any engagement signal into selection.** If Gene later asks for a personal catalog, the `seeds` subcommand already records his saved-from-our-playlists tracks passively in its output — it can become the importer then. Selection stays 100% editorial.

## Auth / failure modes
- **Spotify 401** → refresh token revoked; the user must re-run `hermes auth spotify`. Report, don't retry.
- **403 on writes with default Python UA**: pipeline.py sends `User-Agent: HermesAgent/1.0` — Spotify started 403ing default-python UA on writes 2026-08-29. Don't strip it.
- **Playlist create must use `POST /me/playlists`** (new path); `/users/{id}/playlists` 403s now. `pipeline.py` handles this.
- **API shape (2026-08)**: playlist GET nests tracks at `items.items[].item`; count = `items.total`; the `/tracks` sub-endpoint 403s — use the playlist root. Add via `POST /playlists/{id}/items`.
- **Token refresh**: pipeline.py PKCE-refreshes automatically when <60s to expiry.
- **Cron scheduler "completed" ≠ success** — trials proved a mid-generation death still reports completed. Trust only: playlist URL live + count verified + state.json updated. publish does all three atomically.

## Pitfalls
- **The pipeline script does the Spotify work.** Do not run 38 spotify_search tool calls — that killed trial 1 (context exhaustion at msg 56).
- Harvest ≤10 calls, verify/publish = 2 calls. Total agent turn budget stays ~20 calls.
- Never search the same artist twice in one run.
- Subgenre-tag every pick; max 4 per tag across the whole playlist.
- Candidate pool is a reserve, not a feed.
- Capacities: NEVER delete objects (deletion destroys invisible link anchors).
- If a run fails partway, draft.json preserves progress; state is only touched by a successful publish.

## Verification (every run)
- [ ] publish reported `ok: true` AND `state_updated: true` (atomic — no partial bookkeeping)
- [ ] Playlist live, count matches, lane breakdown printed
- [ ] attribution.jsonl has this week's entry
- [ ] Capacities daily note updated
- [ ] Link + blurbs delivered to Gene

## Changelog
- 2.0.1 (2026-08-29): feedback lane REMOVED per Gene — listening-history personalization rejected (subvert the algorithm, editorial only; played ≠ enjoyed, saved = endorsement but that signal is parked). Replaced by editor's wildcard lane (2 slots, best finds of the week from any source). `seeds` subcommand retained purely as a passive saved-tracks recorder for a possible future catalog.
- 2.0.0 (2026-08-29): lane architecture v2 — six lanes with slot quotas, source→lane map with per-source caps, TOTW auto-include, feedback loop via listening history, playlist sequencing, attribution log, atomic publish (state only updates on verified success), all Spotify mechanics moved into scripts/pipeline.py. Designed from the Week-1 postmortem: de facto pool-domination, silent bookkeeping failures, small-model context limits.
- 1.0.4 (2026-08-29): mandatory playlist-count verification via API; Spotify API shape notes.
- 1.0.3 (2026-08-29): small-model hardening (query format, limit:1, draft.json, ≤45-call budget).
- 1.0.0 (2026-08-29): initial creation.
