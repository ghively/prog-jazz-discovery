# Hermes handoff prompt — Now Spinning polish pass + scene-mode selection fix

Paste everything below the line into Hermes (interactive session, not the Monday cron). It is written so Hermes does the work and records what it learned, rather than having the fixes handed to it.

---

You built the Prog & Jazz Discovery skill, the Now Spinning site generator (`~/.hermes/prog-discovery/site/build_site.py`), and the two live editions at https://music.hively.dev. An independent audit of the generator, the live site, the Monday cron flow, and the skill's selection logic was done on 2026-09-02. You are going to fix what it found, verify each fix yourself, and write down what you learned so the next build does not repeat it.

**Read first, in full, before touching anything:**
`~/repos/prog-jazz-discovery/docs/AUDIT-2026-09-02.md`

Every finding has an ID. D-* data/flow, R-* rendering, C-* cohesion, M-* mechanics, S-* selection and theme. Section 1 explains how the three copies of this project relate and why the repo does not match the installed skill. Section 8 explains the selection findings and carries Gene's decisions on them; those decisions are final and are restated below.

## Two workstreams, in this order

### Workstream A — the site (D, R, C, M findings)

Work in the order given in the audit's section 6. **D-4 first**: backfill lane data for 2026-08-31 from the current `~/.hermes/prog-discovery/draft.json` into that edition's data files, then change `load_all()` to read lanes from the edition directory only. Next Monday's publish overwrites `draft.json` and the backfill source is gone. Prove it: rename `draft.json` temporarily, rebuild, confirm the 2026-08-31 page still shows its Spotlight and Editor's Picks, rename it back.

### Workstream B — the skill's scene logic and rule enforcement (S findings)

Gene's decisions, which you implement and do not relitigate:

- **A scene may be a history lesson.** A scene that traverses old and new across decades is the most interesting kind. Week 2 (Zeuhl & Canterbury, 1975 to 2026) was right. Do not add age ratios, age quotas, or old/new splits anywhere.
- **But not every scene is a lineage.** The bug is that nothing decides what shape a scene takes, so every scene defaults to four ProgArchives catalog picks. Fix the logic, not the proportions.
- **Archive stays at 2, unchanged.** Only nudge: in a lineage week, archive picks should reach somewhere other than that lineage.

Implement it like this:

1. **Scene modes in the wheel.** Each entry in `state.json.scene_rotation.scenes` (live) and `templates/state.json` (repo) gets a `mode` field: `lineage`, `living`, `moment`, or `microgenre`, plus a one-line `angle` describing the story for that scene. Suggested defaults: Zeuhl & Canterbury = `lineage`; Japan = `lineage` (Kenso, Ain Soph, Koenjihyakkei through to today, but argue `living` if you think the current Tokyo scene is the better story); Scandinavia, Latin America, Eastern Europe, Middle East, Aus/NZ, East Asian Jazz = `living`. You may propose different modes; put your reasoning in the report so Gene can override. Consider adding 4 to 8 more entries of mixed type and mark them as proposals: a label, a city-and-year, an instrument tradition, an RIO lineage, and at least two `microgenre` entries (Gene named this type explicitly; candidates: jazztronica, dark jazz, math-rock, avant-metal, dissonant death, hyperpop-prog, kraut revival).
2. **`pipeline.py scene` prints the mode and angle** alongside the name, and defaults to `living` for any legacy entry without a mode.
3. **SKILL.md scene harvest follows the mode.** Rewrite the scene lane definition and the scene row of the source map so the instructions differ by mode:
   - `lineage`: picks span the decades, roots through to where the line is now. ProgArchives for the tree; Bandcamp tags and current articles for the living branches. Week 2 is the template.
   - `living`: picks are current and previous-year releases from that scene. One root allowed if it explains the sound. ProgArchives is for *finding* active bands, not supplying tracks.
   - `moment`: whatever defines the moment, any age.
   - `microgenre`: the story is the sound itself. The records that define it plus who is doing it best now, any age. Bandcamp tags first, then subgenre pages and current reviews.
   The agent may argue a different mode for a given week if the harvest supports it, and must record `scene_mode` and one line of `scene_reason`.
4. **The site's Deep Dive follows the mode.** `lineage` = family tree (as now). `living` = "who is making this now" with the scene's active bands, labels, and cities. `moment` = timeline. `microgenre` = "what defines the sound": the markers, the key records, the current practitioners. Add the mode to `edition.json` and branch in `build_edition()`. Do not redesign the Deep Dive panel; reuse its structure.
5. **`publish` records `scene`, `scene_mode`, and `scene_reason`** into `state.json.playlists[]` so history is auditable. Backfill week 2 by hand (`lineage`).
6. **Enforce the written rules in `pipeline.py`** (S-5 through S-8). Changes to `pipeline.py` are in scope for this workstream only; do not touch selection quotas or the obscurity threshold.
   - `verify`: reject any candidate whose URI is in `played_tracks`. Warn on artists in `played_artists` with the week they last appeared; migrate `played_artists` from a flat list to `{artist: last_week}` (keep reading the old shape). Fetch each verified track's primary artist once and print `followers.total` and `popularity` so the obscurity gate has data. Count per-source totals against the caps in SKILL.md and print violations. Accept an optional `tag` on candidates and count per-tag totals against max 4.
   - `publish`: refuse (nonzero exit, state untouched) on per-source cap violations, the same way it refuses under 34 tracks. Print the source and tag counts on success.
   - Put the caps in one dict at the top of `pipeline.py` and reference the same numbers from SKILL.md so they cannot drift.
7. **Update the cron job prompt** (`prog-discovery-monday` in `~/.hermes/cron/jobs.json`, via `hermes cron`, not by hand-editing the file) so Phase 1 reads the mode from `pipeline.py scene` and harvests accordingly, and Phase 3 writes the mode into `edition.json`.

## Rules for this session

1. **Fix the root cause, not the symptom.** 41 font sizes means build a token scale and delete literals, not change one number. Lane data read from the wrong file means persist lanes per edition, not patch this week's page.
2. **Verify every fix with evidence you produced.** Screenshots via headless Chromium at 1440px and 390px (a Playwright Chromium exists at `~/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome`; use `--headless=new --screenshot --window-size`), grep counts over `out/`, `qa.py` exit codes, and for `pipeline.py` changes a dry run of `verify` against `candidates-week.json` with a deliberately duplicated track and an over-cap source to prove the rejections fire. Look at the screenshots yourself.
3. **Extend `qa.py` for every site bug you fix** where a cheap check is possible (audit D-8). Add a check that every track in every edition has a non-empty lane and that `edition.json` carries a `scene_mode` when it has a scene.
4. **Do not change the aesthetic.** Layout, shelves, neon masthead, stickers, paper card all stay. Cohesive, not different. Anything beyond the audit goes under "Proposed".
5. **Do not touch playlist selection beyond what Workstream B specifies.** No changes to lane quotas, the obscurity threshold, the source list, or the personalization stance. `seeds` stays as-is.
6. **Do not run `publish` or `selftest`** during this session. Test `verify` only, and only against a throwaway copy of the candidates file so `draft.json` is not overwritten before D-4's backfill is done.
7. **Deploy only on green.** `cd ~/.hermes/prog-discovery/site && python3 build_site.py && python3 qa.py` must exit 0 before `rsync -a --delete out/ /var/www/music/` (rsync with delete, not `cp -r`, per D-5). Confirm https://music.hively.dev/ serves the new build with curl.
8. **Keep the repo in sync.** After the live copies work, copy `build_site.py`, `qa.py`, and `pipeline.py` into `~/repos/prog-jazz-discovery`, refresh `site/examples/` from live data (D-6), fix `templates/state.json` (D-7 plus the new modes), add the site-edition phases and the scene-mode rules to `SKILL.md` and `README.md` (D-1), bump the SKILL.md version and changelog. Then re-install the skill so the installed SKILL.md and the repo SKILL.md are identical, with `author: Gene Hively` and a clean one-sentence description (D-3). Do not commit; leave the working tree for Gene to review.

## Report format (deliver at the end, and save a copy)

Save the report to `~/repos/prog-jazz-discovery/docs/POLISH-REPORT-<date>.md` and send Gene the summary. Structure:

1. **Fixed** — one line per audit ID: what changed, which file and function, and the evidence (screenshot path, grep count before/after, qa check added, verify dry-run output).
2. **Scene modes as set** — the wheel with each entry's mode and angle, plus your reasoning for any you changed from the suggested defaults and any new entries you propose.
3. **Not fixed** — audit IDs you did not complete, with the specific reason. "Ran out of time" is acceptable; "seemed fine" is not, because the audit observed it on the live site or in the live data.
4. **Proposed** — design or structural changes you believe are needed but were out of scope under rules 4 and 5.
5. **Metrics after** — re-run the table in audit section 4 and show the new numbers.
6. **Lessons** — the part that matters most. For each class of mistake (reading state from the wrong lifetime, building CSS without a scale, positioning badges without checking overlap, deploying with cp instead of rsync, trusting a structural QA gate for visual bugs, writing rules in prose that no code checks, letting a theme wheel run without intent), write one or two sentences on why it happened and the rule you will apply next time. Add those rules to the skill's Pitfalls section so the Monday run inherits them.

Start by reading the audit. Then confirm back, in one short message, the order you will work in and the first three things you will do. Then go.
