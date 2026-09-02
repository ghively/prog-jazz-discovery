---
name: prog-discovery-weekly
description: "Run the weekly Prog & Jazz Discovery playlist and Now Spinning site edition: harvest by scene mode, verify, publish, build."
version: 3.0.0
author: Gene Hively
license: MIT
tags: [music, prog, jazz, playlist, spotify, discovery, weekly]
metadata:
  hermes:
    category: media
    tags: [music, prog, jazz, playlist, spotify, discovery, weekly]
    requires_toolsets: [web, terminal, file, spotify]
---

# Prog & Jazz Discovery — Weekly Playlist + Now Spinning Edition (v3: scene modes)

## When to Use

- The Monday cron `prog-discovery-monday` fires (this skill is attached to it).
- Gene asks for "this week's playlist", new prog/jazz discovery, or the pipeline misbehaves.

A replacement for a lapsed music-magazine subscription. Every Monday: build ONE Spotify playlist of ~38 tracks across six lanes, verify every track, record attribution, publish, then build and deploy the Now Spinning site edition.

**State:** `~/.hermes/prog-discovery/state.json` (week counter, played history `{artist: last_week}`, scene wheel with modes)
**Pipeline script:** `scripts/pipeline.py` — ALL Spotify mechanics go through it (scene / seeds / verify / publish / selftest). The agent does editorial work only; the script does API loops. This is the v2 core fix for small-model context exhaustion.
**Site generator:** `site/build_site.py` + `site/qa.py` — turns each published edition into a page at music.hively.dev.
**Cron:** `prog-discovery-monday`, Mon 09:00 America/Chicago, pinned glm-4.7-flash/zai

## The six lanes (weights ARE slot quotas)

| Lane        | Slots | Definition                                                                                                                                                            |
| ----------- | ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| core-prog   | 12    | Symphonic, prog-metal, avant-proper, Crossover Prog — the magazine's heart                                                                                            |
| jazz-fusion | 9     | Fusion, jazztronica, Canterbury-adjacent, modern comps                                                                                                                |
| fringe      | 9     | Psych, post-rock, kraut-descended, experimental — adjacency to prog/jazz, NOT membership. This lane exists because the interesting music lives BETWEEN the categories |
| scene       | 4     | This week's featured scene — harvested according to the scene's MODE (below)                                                                                          |
| archive     | 2     | Pre-2015 obscure bands Gene likely missed. In a **lineage** week these must reach somewhere OTHER than the lineage (no duplicated history lesson)                     |
| wildcard    | 2     | **Editor's wildcard** — the two most exciting finds of the week from ANY source. Pure editorial judgment                                                              |

**NO listening-history personalization.** Gene explicitly rejected it (2026-08-29): the point of this system is to subvert algorithmic lock-in. Played ≠ enjoyed; only saved-to-library counts as an endorsement, and that signal is PARKED. Selection stays 100% editorial: sources, lanes, quotas, modes.

Hard rules across lanes (pipeline.py ENFORCES the first three): tracks never repeat (verify rejects); no artist within 8 weeks (verify warns — played_artists stores `{artist: last_week}`); max 4 tracks per fine tag (verify counts, publish refuses); per-source caps (below). Obscurity gate: skip >500k followers; borderline only if <3 albums; legends never. `verify` prints each artist's `followers` and `popularity` — apply the gate against those numbers, never against vibes.

## Scene modes (v3, owner decisions 2026-09-02)

A scene MAY be a history lesson; a scene that traverses old and new across decades is the most interesting kind. But not every scene is a lineage. Each wheel entry in `state.json.scene_rotation.scenes` carries a `mode` and a one-line `angle`; `pipeline.py scene` prints both. Harvest and write the edition accordingly:

| Mode           | Scene lane picks                                                                                                                     | Sources                                                                             | Site Deep Dive                                                                                |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| **lineage**    | Span the decades: roots, middle, where the line is now. Week 2 (Zeuhl & Canterbury) is the template. Archive lane reaches elsewhere. | ProgArchives for the tree; Bandcamp tags + current articles for the living branches | Family trees (as week 2)                                                                      |
| **living**     | Current + previous-year releases from that scene. ONE root allowed if it explains the sound.                                         | ProgArchives only to FIND active bands, never to supply tracks                      | "Who is making this now": active bands, labels, cities (`deep.now = {bands, labels, cities}`) |
| **moment**     | A label, festival, year, or city at a specific time — whatever defines the moment, any age.                                          | Whatever documents the moment                                                       | Timeline                                                                                      |
| **microgenre** | The story is the sound: the records that define it plus who does it best now, any age.                                               | Bandcamp tags first, then subgenre pages + current reviews                          | "What defines the sound": markers, key records, current practitioners                         |

- The agent may argue a different mode for a given week if the harvest supports it: write `scene_mode` + one-line `scene_reason` into draft.json (top level) before publish; publish records both into `state.json.playlists[]`.
- No age ratios, age quotas, or old/new splits anywhere — the mode system is what keeps weeks distinct, not arithmetic.
- The wheel is a default, not a law: if the week's press clusters on something (a country, a label, a death, an anniversary), the agent may name that as the theme and must record the justification in `scene_reason`.

## Source → lane map (with per-source caps)

Caps live in ONE place: `SOURCE_CAPS` at the top of `pipeline.py`. The numbers here mirror it — keep them identical when either changes.

| Source                                           | Lane(s)                           | Cap/week                                |
| ------------------------------------------------ | --------------------------------- | --------------------------------------- |
| loudersound.com/prog Tracks Of The Week (`TOTW`) | core-prog                         | 8 (auto-include all that pass gates)    |
| The Progspace release roundups (`Progspace`)     | core-prog                         | 4                                       |
| The PROG Mind (`TPM`)                            | core-prog, archive                | 4                                       |
| The Progressive Subway (`Subway`)                | core-prog, archive                | 3                                       |
| Arctic Drones (`ArcticDrones`)                   | jazz-fusion, fringe               | 3                                       |
| ProgArchives (`ProgArchives`)                    | scene (lineage mode: tree source) | 3                                       |
| r/postrock best-of, A Closer Listen (`postrock`) | fringe                            | 4                                       |
| The Free Jazz Collective (`FJC`)                 | fringe                            | 4                                       |
| Bandcamp tags (`Bandcamp`)                       | fringe, jazz-fusion               | 4                                       |
| Spotify related-artists                          | —                                 | 0 (personalization REJECTED 2026-08-29) |
| Pre-researched candidate pool (`reserve`)        | RESERVE ONLY                      | no cap, never primary feed              |

Week 2 postmortem lesson (2026-08-31): Bandcamp 6/4, Subway 5/3, ProgArchives 5/3 all exceeded caps because nothing counted them. Now `verify` prints per-source/per-tag counts and `publish` refuses (exit 4, state untouched) on violations.

## Candidate schema (v3)

```json
{
  "artist": "...",
  "track": "...",
  "lane": "core-prog",
  "source": "TOTW",
  "tag": "symphonic"
}
```

`tag` is REQUIRED (audit S-7): it is the fine subgenre used for the max-4 rule and later the site's genre tags. `verify` carries `followers` and `popularity` into draft.json per track.

## Procedure

### 1. Setup (one terminal call)

```
python3 ~/.hermes/skills/media/prog-discovery-weekly/scripts/pipeline.py scene
```

Reads state.json, prints week, scene, short, **mode**, **angle**. Harvest the scene lane per the mode table. (Do NOT run `seeds` — personalization rejected; subcommand is a passive recorder only.)

### 2. Harvest (≤10 web calls, respect per-source caps)

Fetch sources per the lane map. Write `~/.hermes/prog-discovery/candidates-week.json` (~50 candidates, each with artist/track/lane/source/tag). If a source is thin, move on; never pad with famous bands. The reserve pool tops up short lanes after harvest.

### 3. Verify (one pipeline call)

```
python3 ~/.hermes/skills/media/prog-discovery-weekly/scripts/pipeline.py verify
```

Searches Spotify per candidate, rejects artist mismatches, REJECTS tracks already in `played_tracks`, WARNS on artists in the 8-week cooldown (with the week they last appeared), fetches each artist's followers + popularity, and prints per-source/per-tag counts with violations. Writes draft.json. Swap failed candidates and re-run until ≥40 verified, 34 usable minimum.

### 4. Select + sequence

From draft.json pick the final ~38 honoring lane quotas, source caps, and max-4-per-tag. SEQUENCE as an arc: energetic opener, alternate prog/jazz/fringe, mellow close. Write the ordered list back to draft.json. If arguing a different scene mode, set `scene_mode` + `scene_reason` at draft.json top level now.

### 5. Publish (one pipeline call)

```
python3 ~/.hermes/skills/media/prog-discovery-weekly/scripts/pipeline.py publish
```

Refuses (exit 2) under 34 tracks; refuses (exit 4) on source/tag cap violations; creates the playlist named `Prog & Jazz Discovery — YYYY-MM-DD · <Scene>` (NO week numbers), adds in batches, verifies count via API, and only on match atomically updates state.json (week counter, playlists[] now including `scene`, `scene_mode`, `scene_reason`; played_artists as `{artist: week}`) and appends attribution.jsonl. Mismatch exits 3 with state untouched. If it refuses: fix the draft, re-run. Do not deliver on any nonzero exit.

### 6. Site edition — research (Phase 2 of the cron)

- PIN the exact article URL per selected track (the article page, not the site root).
- Per-track facts from those articles: band origin, what the piece says, quotable lines.
- Scene research FOLLOWS THE MODE (genealogy / active bands+labels+cities / timeline / sound markers + key records + current practitioners).
- Verify a Bandcamp or official-site URL for every NEW artist: HEAD-check, only 2xx/3xx, never invent. Append to `site/data/artists.json`.

### 7. Site edition — build + deploy (Phase 3 of the cron)

Write `site/data/<date>/tracks.json` (Spotify playlist fetch incl. album_art, duration_ms, release_date, urls) and `site/data/<date>/edition.json`:

- week, date, scene, **scene_mode** (required), scene_reason, playlist id/url, editor_note
- sources: name/outlet/author/url per source
- blurbs + tags keyed by track uri (every track, grounded in the pinned article)
- **lanes: {uri: lane}** from draft.json — the site reads lanes ONLY from edition.json (D-4 fix; never from draft.json at build time)
- theme {name, kicker, origin, paras, deep{intro, paras, trees (lineage) | now {bands, labels, cities} (living), outro}}

Then:

```
cd ~/.hermes/prog-discovery/site && python3 build_site.py && python3 qa.py
```

Deploy ONLY on qa exit 0: `rsync -a --delete out/ /var/www/music/` — never `cp -r` (D-5: retired pages must disappear). Confirm with `curl -s https://music.hively.dev/`.

### 8. Deliver (Phase 4)

To the job origin: playlist URL, count, lane breakdown one-liner, scene + scene_mode, 3-5 highlight blurbs, edition URL, qa-passed confirmation. Tight — no wall of text.

## Auth / failure modes

- **Spotify 401** → refresh token revoked; Gene must re-run `hermes auth spotify`. Report, don't retry.
- **403 on writes with default Python UA**: pipeline.py sends a custom UA — don't strip it.
- **Playlist create must use `POST /me/playlists`**; `/users/{id}/playlists` 403s.
- **API shape (2026-08)**: playlist GET nests tracks at `items.items[].item`; count = `items.total`; `/tracks` sub-endpoint 403s.
- **Token refresh**: pipeline.py PKCE-refreshes automatically when <60s to expiry.
- **Cron scheduler "completed" ≠ success** — trust only: playlist URL live + count verified + state.json updated. publish proves all three atomically.

## Pitfalls

- **The pipeline script does the Spotify work.** Do not run 38 spotify_search calls — that killed trial 1 (context exhaustion at msg 56).
- Harvest ≤10 calls, verify/publish = 2 calls; agent turn budget ~20 calls.
- Never search the same artist twice in one run.
- Subgenre-tag every pick (`tag` field); pipeline counts and refuses on cap breaches — if publish refuses, trim the named over-cap source/tag, don't relitigate.
- Candidate pool is a reserve, not a feed.
- Capacities (optional): NEVER delete objects.
- If a run fails partway, draft.json preserves progress; state is only touched by a successful publish.
- **Read state from the right lifetime** (D-4): the site builder must never read the live draft.json — lane data is per-edition and lives in each edition.json. Anything week-scoped (draft, candidates) must be persisted into edition-scoped files before the next week overwrites it.
- **Keep the aesthetic stable** (owner, 2026-09-02): the site's look was approved as-is; the polish session's visual redesign was reverted by Gene the same day. Fix rendering bugs with the smallest diff that fixes the named bug — do not re-systematize the CSS. (The audit's C-1..C-12 token work exists in git history if ever wanted.)
- **Positioned overlays need measured overlap checks** (R-1): absolute-positioned badges/notes over sleeves overlap flexible content by default; verify with a layout check (Playwright bounding boxes), not eyeballing. (Current badge overlap is accepted by owner preference; the method stands for any future change.)
- **Deploy with rsync --delete, never cp -r** (D-5): retired pages stay live forever otherwise.
- **A structural QA gate does not catch visual bugs** (D-8): qa.py checks data-level invariants (lane presence per track, scene_mode when a scene exists). Visual bugs need measured layout checks at fix time.
- **Written rules need a mechanical enforcer** (S-5..S-8): any rule that only lives in prose (caps, repeats, cooldowns) decays in one week. Pipeline counts and refuses; if a rule matters, make the code say no.
- **A theme wheel without intent produces catalog-default weeks** (S-1): every wheel entry carries mode + angle; the mode drives harvest, Deep Dive shape, and is recorded on publish.

## Verification (every run)

- [ ] publish reported `ok: true` AND `state_updated: true` (atomic — no partial bookkeeping)
- [ ] Playlist title = `Prog & Jazz Discovery — YYYY-MM-DD · <Scene Short>` (no week number)
- [ ] Playlist live, count matches, lane + source + tag counts printed, no cap violations
- [ ] state.json playlists[] entry carries scene, scene_mode, scene_reason
- [ ] attribution.jsonl has this week's entry
- [ ] edition.json has scene_mode + lanes covering every track uri; qa.py exit 0
- [ ] rsync --delete deployed; https://music.hively.dev/ serves the new edition
- [ ] Link + blurbs delivered to Gene

## Changelog

- 3.0.0 (2026-09-02): scene modes (lineage/living/moment/microgenre) per owner decisions — wheel entries carry mode+angle, harvest and Deep Dive follow the mode, agent may argue mode with recorded reason; scene/scene_mode/scene_reason recorded on publish; played_artists migrated to {artist: last_week}; verify enforces played-track rejection + cooldown warnings + per-source/per-tag caps + followers/popularity fetch; publish refuses on cap violations (exit 4); candidates carry required `tag`; SOURCE_CAPS dict is the single source of caps (mirrored in the source map); site phases 2-4 documented (D-1); edition.json now carries lanes (D-4) and scene_mode; deploy via rsync --delete (D-5). Written from the 2026-09-02 audit + polish session (docs/POLISH-REPORT-2026-09-02.md).
- 2.0.2 (2026-08-29): playlist retitling — no week numbers; scene wheel entries carry short display names.
- 2.0.1 (2026-08-29): feedback lane REMOVED (personalization rejected); replaced by editor's wildcard lane.
- 2.0.0 (2026-08-29): lane architecture v2 — six lanes, source caps, atomic publish, mechanics in pipeline.py.
- 1.0.4 (2026-08-29): mandatory playlist-count verification; Spotify API shape notes.
- 1.0.3 (2026-08-29): small-model hardening.
- 1.0.0 (2026-08-29): initial creation.
