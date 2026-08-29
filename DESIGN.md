# Design Document — Lane Architecture (v2)

_Why the weekly playlist is built the way it is. Written 2026-08-29 after Week 1's postmortem and the design session that followed._

## Origin

Week 1 (20 tracks, built by a fully-automated Hermes cron run) worked — but it felt **samey**. The owner liked what he heard (5 of 20 tracks played) but wanted more diversity _without_ losing anything that was working. This document is the honest analysis and the design it produced.

## Week 1 postmortem — what actually happened

The v1 skill said "harvest from six sources in priority order." In practice:

1. **Sources weren't weighted — they were ordered by laziness.** The pre-researched candidate pool (~35 bands, mostly from The PROG Mind's Top 40) required zero web fetches, so the small model filled ~70% of the playlist from it. The pool is US/UK/EU prog-heavy, so the playlist was too.
2. **Selection within the eligible set was order-bias + harvest recency.** No quotas, no per-source caps, no attribution. After the fact, nobody could answer "where did track 7 come from."
3. **The genre spec was two boxes** ("prog" 60-70% / "jazz-fusion" 30-40%). Anything that fringes on prog or jazz without sitting inside either — psych, post-rock, kraut-descended, experimental — didn't count for either side and was structurally squeezed out. The most interesting music in this space lives _between_ the categories.
4. **No personalization.** Nothing looked at what the owner actually played.

## The v2 design

### Lanes, not boxes

Six lanes with **slot quotas** — the weights ARE the quotas, countable and auditable:

| Lane        | Slots | Rationale                                                                                                         |
| ----------- | ----- | ----------------------------------------------------------------------------------------------------------------- |
| core-prog   | 12    | The magazine's heart: symphonic, prog-metal, avant. Never below half the list                                     |
| jazz-fusion | 9     | Fusion, jazztronica, Canterbury-adjacent                                                                          |
| fringe      | 9     | Psych, post-rock, kraut, experimental — **adjacency, not membership**. Exists to fix failure #3                   |
| scene       | 4     | Rotating featured geography (Japanese prog → Zeuhl/Canterbury → Scandinavian → …). Fixes the US/UK/EU monoculture |
| archive     | 2     | Pre-2015 obscure bands. "Allowed" in v1 but never happened; a slot makes it happen                                |
| feedback    | 2     | Styles adjacent to what the owner actually played/saved last week. Fixes failure #4                               |

~38 total (34 floor). Why 38: below ~34 the six lanes collide over the same tracks; above ~40 the max-4-per-subgenre rule forces scraping the bottom of candidate quality. One playlist (a proposed B-sides companion was folded in — one artifact, one ritual).

### Source caps + attribution

Every source maps to lanes with a per-week cap (see SKILL.md). The candidate pool is demoted to **reserve** — it tops up short lanes, never leads. TOTW (the single strongest editorial signal, only 5-8 tracks/week) is **auto-included** when it passes the gates.

Every published track carries `{lane, source}` into `attribution.jsonl`. Source weighting stops being vibes; it's a queryable log.

### Feedback loop

`pipeline.py seeds` intersects the owner's recently-played/saved with last week's playlist → seed artists → the feedback lane picks stylistically-adjacent candidates (obscurity gate still applies). Playing music is the only input required. Reactions (🔥/🚫) on the delivery message can augment it.

### Mechanics moved out of the model

Trial 1 died of context exhaustion: 38 verbose Spotify search payloads in a small model's context. v2 moves ALL Spotify mechanics into `scripts/pipeline.py`:

- `scene` / `seeds` — setup calls
- `verify` — batched verification of the candidates file → draft.json (one tool call replaces ~40 searches)
- `publish` — create (new `POST /me/playlists` path), batched adds, **count verification via API**, and **atomic state update** (week counter + played history only written on verified success — fixes the Week 1 bookkeeping failure where 19 tracks shipped under a claim of 20)

The agent does editorial work only: harvest judgment, lane selection, sequencing (arc: energetic opener → alternate lanes → mellow close), blurbs. Agent budget drops from ~45 calls to ~20.

## Things that broke during the build (2026-08-29, current API reality)

- Spotify **403s default-Python User-Agent on writes**. The pipeline sends `User-Agent: HermesAgent/1.0`.
- Playlist create must use `POST /me/playlists`; the classic `/users/{id}/playlists` 403s.
- Playlist GET nests track data at `items.items[].item` (not `item.track`); the count is `items.total`; the `/tracks` sub-endpoint 403s.
- A cron run that dies mid-generation still reports **"completed"** to the scheduler. Never trust that flag; trust `publish`'s atomic `ok: true`.

## Invariant rules (unchanged from v1)

- Obscurity gate: >500k monthly listeners excluded; borderline 200-500k only if <3 albums; legends never.
- No artist repeat within 8 weeks; tracks never repeat.
- Never pad with famous bands to hit a number.
