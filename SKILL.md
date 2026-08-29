---
name: prog-discovery-weekly
description: "Use when running the weekly Prog & Jazz Discovery playlist."
version: 1.0.4
author: Gene Hively
license: MIT
tags: [music, prog, jazz, playlist, spotify, discovery, weekly]
metadata:
  hermes:
    category: media
    tags: [music, prog, jazz, playlist, spotify, discovery, weekly]
    requires_toolsets: [web, terminal, file, spotify]
---

# Prog & Jazz Discovery — Weekly Playlist

## When to Use

- The weekly cron fires (attach this skill to it).
- The user asks for "this week's playlist", new prog/jazz discovery, or the pipeline misbehaves.

A self-running replacement for a lapsed music-magazine subscription. Every Monday: build a Spotify playlist of at least 20 tracks from newer and/or lesser-known prog + jazz-fusion bands, verify every track, save edition notes, post the link.

**State file (source of truth for history):** `~/.hermes/prog-discovery/state.json`
**Scratch file (this run's verified tracks):** `~/.hermes/prog-discovery/draft.json`
**Optional PKM integration:** replace the Capacities block in step 5 with your own note system, or delete it.

## Procedure (all 6 steps, every run)

### 1. Load state

Read `~/.hermes/prog-discovery/state.json`. `week_counter` + 1 = this week's number. `played_artists` (8-week cooldown) and `played_tracks` (never repeat) are the eligibility filters.

### 2. Harvest candidates (rotate emphasis week to week)

Scrape/fetch, in priority order:

1. **loudersound.com/prog "Tracks Of The Week"** (search: `site:loudersound.com prog "tracks of the week"`) — the single best new-band feed
2. **The Progspace** releases-of-the-week (`theprogspace.com/album_releases/`)
3. **The PROG Mind** (`theprogmind.com`) — deep reviews, top-40 lists
4. **The Progressive Subway** (`theprogressivesubway.com`) — lesser-known focus
5. **Arctic Drones** jazz-fusion roundups (`arcticdrones.net`) — the jazz side
6. **ProgArchives** new releases + r/progrockmusic weekly roundup — depth/obscure picks

### 3. Select 20+ tracks — eligibility rules

- **Genre span:** roughly 60-70% prog (rock/metal/psych/post/symphonic/avant), 30-40% jazz (fusion, jazz-prog, jazztronica, Canterbury-adjacent)
- **Recency:** last ~18 months strongly preferred; older OK only for genuinely obscure bands the user likely missed
- **Obscurity gate:** skip artists with >500k Spotify monthly listeners — the point is discovery. Borderline (~200-500k) allowed if the band is new (fewer than 3 albums). Established legends are NEVER eligible — maintain your own exclusion list in the state file.
- **No repeats:** artist not in `played_artists` (last 8 weeks), track never in `played_tracks`
- **Aim for 20-24 tracks** across ~20 distinct artists (two tracks may share a band only if the albums differ wildly)

### 4. Verify + build playlist (Spotify toolset)

For each candidate, ONE search — `spotify_search` with `types: ["track"]`, `limit: 1`, and the query is **the artist name followed by the track's actual title** (NOT the literal word "track"):

- ✅ `query: "Siiga Nostalgia Burns"` → top result is the right track
- ❌ `query: "Siiga track"` — never do this
  Confirm artist + album match the research, then append `{artist, track, uri, album}` to the scratch file `~/.hermes/prog-discovery/draft.json` (write it every 5 finds with the `file` tool — this keeps context small and survives a crash). **Never search the same artist twice.** Budget: the whole run must fit in ~40 tool calls; once you hold ≥22 verified URIs, STOP searching and build.

```
spotify_playlists create → name: "Prog & Jazz Discovery — Week N (YYYY-MM-DD)"
spotify_playlists add_items → all verified URIs (read them back from draft.json)
```

If a track isn't on Spotify, swap in the next candidate — never pad with famous bands.

### 5. Update state + notes

- state.json: increment `week_counter`, append artists + track URIs (from draft.json), append playlist record `{week, date, url, count}`
- Optional PKM step: create one album/note object per featured release, tagged `#prog-discovery #week-N`, or append a summary to a daily note. If rate-limited, fall back to ONE page object with the full tracklist.

### 6. Deliver

Post to the job's origin channel: playlist URL, track count, 3-5 highlight blurbs (one-liners: who they are, why picked). Keep it tight — no wall of text.

## Auth / failure modes

- **Spotify 401** → refresh token revoked; the user must re-run `hermes auth spotify`. Report, don't retry.
- **Spotify 403 No active device** → irrelevant for playlist create/add (headless works); only playback needs a device.
- **PKCE auth from another device:** the callback listener binds 127.0.0.1:PORT on the agent host. Either SSH-forward the port or have the user paste the dead-page callback URL back to the agent, which curls it to the listener.
- **Harvest source thin/unreachable?** Move to the next source; never pad with famous bands to hit 20.

## Pitfalls

- **Hard tool budget: ≤45 calls total.** Harvest in ≤12, verify in ≤25, build/save/deliver in ≤8. If the budget runs short, prefer MORE tracks over MORE sources.
- Don't trust search-result popularity ordering — verify artist monthly-listener counts before including borderline-famous bands.
- The scratch file `draft.json` IS the run's progress — read it, don't re-search what's already in it.
- PKM systems with invisible link anchors: NEVER delete objects to "clean up".
- If a run fails partway, state must still record partial work (played tracks are recorded only AFTER the playlist add succeeds).

## Verification (every run)

- [ ] Playlist live with at least 20 verified tracks (URL proof)
- [ ] **Count check: GET the playlist root via API** (`api.spotify.com/v1/playlists/<id>`) and read `items.total` — the current API shape nests track data under `items.items[].item` (NOT `item.track`; the `/tracks` sub-endpoint 403s). If total < 20, search + add more candidates until it is.
- [ ] state.json updated (week, artists, tracks, playlist URL)
- [ ] Edition record created in your notes system (or skipped)
- [ ] Link + blurbs delivered

## Changelog

- 1.0.4: mandatory playlist-count verification via API; Spotify API shape notes (items.items[].item, /tracks 403, POST /items).
- 1.0.3: small-model hardening — precise search-query spec (artist + actual title), limit:1, no-repeat-searches, draft.json scratch file, hard ≤45-call tool budget. First trial died at 56 messages of context exhaustion on a small model.
- 1.0.0: initial creation.
