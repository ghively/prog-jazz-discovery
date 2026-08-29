# Prog & Jazz Discovery — Weekly Playlist Skill

A [Hermes Agent](https://hermes-agent.nousresearch.com) skill (works with any tool-calling AI agent) that builds a **weekly Spotify playlist of ~38 tracks from newer and lesser-known progressive rock, jazz-fusion, and fringe artists** — a self-running, editorially-driven replacement for a lapsed music-magazine subscription.

Every Monday it harvests new-release candidates from curated genre sources, distributes them across six lanes with enforced diversity quotas, applies an obscurity gate, verifies every track against the Spotify catalog, builds and sequences the playlist, records per-track attribution for auditing, and delivers the link with highlight blurbs.

**Deliberately not personalized.** No listening history, no engagement signals, no related-artists-as-preference — the system exists to _subvert_ algorithmic lock-in, not recreate it. Selection is 100% editorial. (See DESIGN.md for the full rationale.)

## Why this exists

Genre magazines (Prog, in this case) are the traditional discovery engine for new bands — but subscriptions lapse. The public web already publishes everything the magazine curates (weekly track columns, release roundups, best-of lists); this skill wires those feeds into a repeatable pipeline with memory and enforced diversity, so discovery keeps happening without anyone paying for it or remembering to do it.

## What's in the box

| File                   | Purpose                                                                                                                                                   |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SKILL.md`             | The skill itself — drop into `~/.hermes/skills/media/` (or your agent's skill dir)                                                                        |
| `scripts/pipeline.py`  | Does ALL Spotify mechanics: scene rotation, batched track verification, atomic playlist publish, self-test. The agent never loops Spotify searches itself |
| `templates/state.json` | Clean v2 starting state (scene wheel with short names, exclusion list) — copy to `~/.hermes/prog-discovery/state.json`                                    |
| `DESIGN.md`            | The why: Week-1 postmortem, lane rationale, decisions and their reasons                                                                                   |
| `README.md`            | This file                                                                                                                                                 |

## How selection works (v2 lane architecture)

~38 tracks across six lanes with enforced slot quotas — the weights ARE the quotas:

| Lane        | Slots | What lives here                                                                                  |
| ----------- | ----- | ------------------------------------------------------------------------------------------------ |
| core-prog   | 12    | Symphonic, prog-metal, avant — the magazine's heart                                              |
| jazz-fusion | 9     | Fusion, jazztronica, Canterbury-adjacent                                                         |
| fringe      | 9     | Psych, post-rock, kraut-descended, experimental — _adjacent_ to prog/jazz, not inside either box |
| scene       | 4     | Rotating featured geography (Japan → Zeuhl & Canterbury → Scandinavia → …)                       |
| archive     | 2     | Pre-2015 obscure bands you likely missed                                                         |
| wildcard    | 2     | Editor's two most exciting finds of the week, from any source                                    |

Cross-cutting rules: max 4 tracks per subgenre tag, no artist repeat within 8 weeks, tracks never repeat, obscurity gate (skip >500k monthly listeners; established legends never eligible). Ten sources feed the lanes with per-source caps so no single feed can dominate — the Week-1 postmortem found one candidate pool had quietly supplied ~70% of a playlist (details in DESIGN.md).

**Playlist title format:** `Prog & Jazz Discovery — YYYY-MM-DD · <Scene>` — dated, scene visible, no week numbers (the counter lives in state + the playlist description).

## Requirements

- A Hermes install (or any agent that can run Python, fetch web pages, and edit files)
- Spotify OAuth: `hermes tools enable spotify && hermes auth spotify` (PKCE; the callback listener binds 127.0.0.1 — port-forward or paste the callback URL to the agent if authorizing from another device)
- A Spotify app at developer.spotify.com with redirect URI `http://127.0.0.1:<port>/spotify/callback` and scopes: playlist read/modify, library read/modify
- Works on Free; only playback control needs Premium

## Setup

1. Copy `SKILL.md` into your skills directory.
2. `mkdir -p ~/.hermes/prog-discovery && cp templates/state.json ~/.hermes/prog-discovery/state.json`
3. Auth Spotify (above).
4. Sanity-check the mechanics (creates, verifies, and deletes a throwaway playlist):

```bash
python3 scripts/pipeline.py selftest
```

5. Schedule it — pinned to a cheap model; the pipeline design is what makes that safe:

```bash
hermes cron create --name prog-discovery-monday \
  --schedule "0 9 * * 1" \
  --skill prog-discovery-weekly \
  --model glm-4.7-flash --provider zai \
  --prompt "Run the weekly Prog & Jazz Discovery playlist build. Follow the prog-discovery-weekly skill exactly."
```

6. First Monday, you get a playlist. Swap sources, lanes, or quotas in `SKILL.md` to repurpose for any genre.

## Hardening notes (learned the hard way)

These exist because real trial runs failed without them:

- **All Spotify mechanics live in `pipeline.py`, not the model.** A small model doing 38 sequential Spotify searches dies of context exhaustion around message 56 (proven in trial 1). The script does verify/publish in two calls total.
- **Exact query format matters**: search `"Artist Actual Track Title"` — small models will literally search the word "track" otherwise.
- **Verify the playlist count via API** (`GET /playlists/{id}` → `items.total`) — never trust the add response or the model's self-report. `publish` refuses to update state unless the count matches.
- **A scheduler "completed" flag is not success.** A run that dies mid-generation still reports completed — trust only the atomic `publish` result.
- **2026-08 Spotify API reality**: default-Python User-Agent gets 403'd on writes (pipeline sends its own UA); playlist creation is `POST /me/playlists` (the classic `/users/{id}/playlists` path now 403s); playlist GET nests track data at `items.items[].item`; the `/tracks` sub-endpoint 403s.
- **Atomic state**: week counter and play history update only after the playlist is live and count-verified. Partial runs leave draft.json intact and state untouched.

## Customizing

- Different genre? Swap the source list and lane definitions in `SKILL.md`.
- Different diversity targets? The lane slot numbers are one table — edit and go.
- No Capacities/PKM? Delete step 6's note block or point it at a markdown log.
- The state file is plain JSON — inspect or edit history any time. `attribution.jsonl` (written on each publish) records every track's lane + source, so "where did this week come from" is a one-line query.

## License

MIT — do whatever, attribution appreciated.
