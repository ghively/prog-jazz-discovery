# Prog & Jazz Discovery — Weekly Playlist Skill

A [Hermes Agent](https://hermes-agent.nousresearch.com) skill (works with any tool-calling AI agent) that builds a **weekly Spotify playlist of 20+ tracks from newer and lesser-known progressive rock and jazz-fusion bands** — a self-running replacement for a lapsed music-magazine subscription.

Every Monday it harvests new-release candidates from six genre sources, applies an obscurity gate, verifies every track exists on Spotify, builds the playlist, records history so nothing repeats, and delivers the link with highlight blurbs.

## Why this exists

Genre magazines (Prog, in this case) are the traditional discovery engine for new bands — but subscriptions lapse. The public web already publishes everything the magazine curates (weekly track columns, release roundups, best-of lists); this skill wires those feeds into a repeatable pipeline with memory, so discovery keeps happening without anyone paying for it or remembering to do it.

## What's in the box

| File                   | Purpose                                                                            |
| ---------------------- | ---------------------------------------------------------------------------------- |
| `SKILL.md`             | The skill itself — drop into `~/.hermes/skills/media/` (or your agent's skill dir) |
| `templates/state.json` | Clean starting state — copy to `~/.hermes/prog-discovery/state.json`               |
| `README.md`            | This file                                                                          |

## Requirements

- A Hermes install (or any agent that can call the Spotify Web API, fetch web pages, and read/write files)
- Spotify toolset enabled + OAuth'd: `hermes tools enable spotify && hermes auth spotify` (PKCE flow; the callback listener binds 127.0.0.1 on the host running the agent — forward the port or paste the callback URL to the agent if you authorizing from another device)
- A Spotify app registered at developer.spotify.com with redirect URI `http://127.0.0.1:<port>/spotify/callback` and scopes: playlist read/modify, library read/modify, playback read
- Works on Free; playback control needs Premium (playlist building does not)

## Setup

1. Copy `SKILL.md` into your skills directory.
2. `mkdir -p ~/.hermes/prog-discovery && cp templates/state.json ~/.hermes/prog-discovery/state.json`
3. Auth Spotify (above).
4. Schedule it — Hermes cron example, pinned to a cheap model (this skill is deliberately tuned to run on small/fast models, see "Hardening" below):

```bash
hermes cron create --name prog-discovery-monday \
  --schedule "0 9 * * 1" \
  --skill prog-discovery-weekly \
  --model glm-4.7-flash --provider zai \
  --prompt "Run the weekly Prog & Jazz Discovery playlist build. Follow the prog-discovery-weekly skill exactly."
```

5. First Monday, you get a playlist. Edit the sources/eligibility sections in `SKILL.md` to repurpose for any genre.

## How it works

1. **Load state** — week counter, played artists (8-week cooldown), played tracks (never repeat)
2. **Harvest** — six sources in priority order: loudersound.com/prog Tracks Of The Week → The Progspace → The PROG Mind → The Progressive Subway → Arctic Drones (jazz-fusion side) → ProgArchives/r-progrockmusic
3. **Select** — 60-70% prog / 30-40% jazz-fusion, last ~18 months preferred, **obscurity gate: skip artists over 500k monthly listeners**, famous bands never eligible
4. **Verify + build** — one Spotify search per candidate (`artist + actual track title`, limit 1), URIs accumulated in a scratch file, then playlist create + add
5. **Record** — state updated, optional Capacities/PKM edition notes
6. **Deliver** — playlist URL + 3-5 highlight blurbs to your channel

## Hardening notes (learned the hard way)

These exist because real trial runs failed without them:

- **Exact query format matters**: search `"Artist Actual Track Title"` — small models will literally search the word "track" otherwise.
- **Hard tool budget (≤45 calls)** with a scratch file (`draft.json`) so progress survives interruption — small models exhaust context on verbose Spotify JSON.
- **Never re-search an artist** already verified in this run.
- **Verify the playlist count via API** (`GET /playlists/{id}` → `items.total`) — do not trust the add response or the model's self-report. Spotify's current API nests track data at `items.items[].item` (not `item.track`), and the `/tracks` sub-endpoint 403s; add via `POST /playlists/{id}/items`.
- **A scheduler "completed" flag is not success.** The first trial run died mid-generation and was still marked completed — always verify the artifact exists.

## Customizing

- Different genre? Swap the six sources and the legend list in the eligibility rules.
- Stricter obscurity? Lower the 500k listener gate.
- No Capacities? Delete step 5's Capacities block or point it at a markdown log.
- The state file is plain JSON — inspect or edit history any time.

## License

MIT — do whatever, attribution appreciated.
