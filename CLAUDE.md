# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A Hermes Agent skill plus two Python scripts. There is no build system, package manager, test suite, or linter. Everything is stdlib Python 3 (`urllib`, `json`, `pathlib`).

- `SKILL.md` — the agent-facing procedure for the weekly playlist run. Its YAML frontmatter `version` must stay aligned with the `## Changelog` at the bottom and with README references. Regenerating SKILL.md from another source has previously wiped the `author` field; check it after edits.
- `scripts/pipeline.py` — ALL Spotify API mechanics for the skill (scene / seeds / verify / publish / selftest).
- `site/build_site.py` + `site/qa.py` — the "Now Spinning" static-site generator that turns published editions into HTML, and its QA gate.
- `DESIGN.md` — the rationale (Week-1 postmortem, lane quotas, decisions). Read it before changing lanes, sources, or the personalization stance.
- `docs/AUDIT-2026-09-02.md` — audit of the site generator, live site, and cron flow, with IDs per finding. `docs/HERMES-PROMPT-site-polish.md` is the handoff prompt for Hermes to fix them. Check for a `docs/POLISH-REPORT-*.md` before assuming a finding is still open.

The live system is not this repo. The installed skill is at `~/.hermes/skills/media/prog-discovery-weekly/`, the working data and the real site build are under `~/.hermes/prog-discovery/`, and the site-edition phases of the Monday run live only in the Hermes cron job prompt. See the audit's section 1.

## Commands

Pipeline (runtime state lives outside the repo, default `~/.hermes/prog-discovery/`, override with `$PD_HOME`; Spotify creds come from `~/.hermes/auth.json`, override with `$HERMES_AUTH_JSON`):

```bash
python3 scripts/pipeline.py scene                         # this week's featured scene
python3 scripts/pipeline.py verify [--candidates FILE]    # candidates-week.json -> draft.json
python3 scripts/pipeline.py publish [--week N] [--date YYYY-MM-DD]
python3 scripts/pipeline.py selftest                      # creates + deletes a throwaway playlist (hits the live API)
```

Site:

```bash
python3 site/build_site.py     # reads site/data/<date>/{edition,tracks}.json + site/data/artists.json -> site/out/
python3 site/qa.py             # exit 0 = safe to deploy; run after every build
```

`site/data/` and `site/out/` are not in the repo. To exercise the generator locally, copy an example into place, e.g. `site/examples/edition-2026-08-31/` to `site/data/2026-08-31/` and `site/examples/artists.json` to `site/data/artists.json`. The directory name under `site/data/` becomes the URL path and must equal `edition.json`'s `date`.

## Architecture: the split between agent and script

The core design constraint is that a small, cheap model runs this weekly. Trial 1 died of context exhaustion doing ~40 Spotify searches in-model, so **the agent does editorial work only** (harvest, lane selection, sequencing, blurbs) and **`pipeline.py` does every API loop in one call each**. Do not move Spotify calls back into SKILL.md steps, and do not add chatty output to the script.

Data flow for one run:

1. `scene` reads `state.json` (`week_counter`, `scene_rotation`) and prints the featured scene. Scene index = `week_counter mod len(scenes)`; scenes may be strings (v1) or `{name, short}` dicts (v2), and the code handles both.
2. Agent writes `candidates-week.json`: `[{artist, track, lane, source}]`.
3. `verify` searches each candidate (`"Artist Track"`, `limit=1`), rejects artist mismatches via `norm()`, and writes `draft.json` with URIs plus the `lane`/`source` attribution carried through.
4. Agent reorders `draft.json` into the final ~38.
5. `publish` refuses below 34 tracks (exit 2), creates the playlist titled `Prog & Jazz Discovery — YYYY-MM-DD · <Scene short>`, adds in batches of 50, re-fetches the playlist to compare `items.total` against the URIs sent, and **only on match** bumps `week_counter`, appends to `playlists` / `played_artists` / `played_tracks` in `state.json`, and appends a line to `attribution.jsonl`. Mismatch exits 3 with state untouched. This atomicity is the fix for a Week-1 bookkeeping failure and must be preserved.

`seeds` is intentionally dead code for selection: listening-history personalization was built, then removed at the owner's direction (2026-08-29). It stays only as a passive recorder of saved tracks. **No engagement signal may ever feed selection.** The `wildcard` lane replaced the old `feedback` lane; `templates/state.json` now says "wildcard 2" (fixed 2026-09-02).

## Spotify API realities baked into pipeline.py (2026-08)

These were all discovered by live failures. Don't "clean them up":

- Custom `User-Agent` on every request. Default Python UA gets 403 on writes.
- Create via `POST /me/playlists`. The classic `/users/{id}/playlists` path 403s.
- Playlist GET nests tracks at `items.items[].item`, count is `items.total`, and the `/tracks` sub-endpoint 403s. Add via `POST /playlists/{id}/items`.
- PKCE token refresh happens in `get_token()` when under 60s to expiry and writes the refreshed token back into `auth.json`.
- One retry with a 2.5s sleep on 429/5xx.

## Architecture: the site generator

`build_site.py` is a single file: a large CSS string, HTML helper functions, then `load_all` / `build_edition` / `build_front` / `build_explore` / `main`. Everything is f-string templating with `esc()` for escaping.

- **Inputs per edition:** `edition.json` (editorial: `sources`, `blurbs` keyed by track URI with `{src, text, quote}`, `tags` keyed by URI, `theme` with optional `deep` dive containing `paras` and `trees`, `scene`, `editor_note`) and `tracks.json` (raw Spotify playlist fetch with `album_art`, `release_date`, `url`). `artists.json` holds only verified Bandcamp/website links; anything absent falls back to the Spotify artist URL.
- **Lane data is in the edition files (since 2026-09-02).** `load_all` reads each edition's `edition.json` `lanes` map (`{uri: lane}`) to drive the Spotlight section (tracks with `lane == "scene"`). Never reintroduce a read of `~/.hermes/prog-discovery/draft.json` here — it holds only the current week and silently corrupted older editions on rebuild before the fix. `edition.json` also carries `scene_mode` (lineage / living / moment / microgenre), which selects the Deep Dive panel heading; qa fails an edition that has a scene but no `scene_mode`.
- **Taxonomy:** fine `tags` map to stable shelves via `SHELVES` at the top of the file; unknown tags fall to "The Fringes". Add new tags there rather than inventing new shelves. Tracks released before 2015 render with a `vintage` sepia treatment.
- **Additive by construction:** edition pages are meant to be stable once built; the front page and Explore are reassembled from all data present. The old `/genres/` output is deleted on each build because Explore replaced it. Deploy is `rsync -a --delete out/ /var/www/music/` — never `cp -r`, or retired pages stay live (2026-09-02 audit D-5).
- **Page structure per edition** (order matters, `qa.py` checks it): header, Spotlight (scene tracks), deep dive, then shelves, with one `modal-back` per sleeve and unique `id="modal-<trackid>"`.

`qa.py` encodes regressions from the 2026-09-02 build sessions: sleeve/modal/id counts equal, `<style>` wrapper present, blurbs and tags cover every track, theme essay present, front-page section ordering, and no duplicate outlet names in the source line. Add a check there whenever a visual bug is fixed.

## Invariants to respect in any change

- Six lanes with slot quotas (core-prog 12 / jazz-fusion 9 / fringe 9 / scene 4 / archive 2 / wildcard 2), ~38 tracks, 34 floor.
- Obscurity gate: skip >500k monthly listeners; legends in `excluded_legends` never.
- No artist repeat within 8 weeks; tracks never repeat; never pad with famous bands.
- Playlist titles carry the date and scene, never a week number. Never label an artifact with a theme it wasn't built around.
- Capacities (optional PKM step): never delete objects.
