#!/usr/bin/env python3
"""Prog & Jazz Discovery pipeline — mechanical Spotify work as ONE tool call each.

The agent does editorial work (harvest, selection judgment); this script does
the mechanical API loops so a small model never burns context on 38 searches.

Subcommands:
  scene     Print this week's featured scene (rotation wheel from state.json)
  verify    Verify candidates file on Spotify (batched in-process) -> draft.json
  publish   Create Week N playlist from draft.json, add tracks, verify count
  handoff   Build + validate site/data/<date>/handoff.json delivery proof
  pref      show|add|remove|validate user preference notes (include/exclude/boost)
  selftest  Create+verify+DELETE a throwaway playlist (proves the full path)

Files (override dir with $PD_HOME, default ~/.hermes/prog-discovery):
  state.json               week counter, played history, scene wheel
  candidates-week.json     INPUT: [{artist, track, lane, source}, ...]
  draft.json               OUTPUT of verify: verified tracks + URIs + attribution
  preferences.json         user-entered include/exclude/boost notes (B2) — NEVER
                         derived from Spotify listening history or playback

Auth: reads Spotify entry from Hermes auth.json ($HERMES_AUTH_JSON,
default ~/.hermes/auth.json); PKCE-refreshes the access token when expired.
"""
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path(os.environ.get("PD_HOME", Path.home() / ".hermes" / "prog-discovery"))
AUTH = Path(os.environ.get("HERMES_AUTH_JSON", Path.home() / ".hermes" / "auth.json"))
API = "https://api.spotify.com/v1"
ACCOUNTS = "https://accounts.spotify.com/api/token"
UA = "HermesAgent/1.0 prog-discovery-pipeline"  # Spotify 403s default-python UA on writes (found 2026-08-29)

# ---- per-source caps per week (audit S-5; mirror these numbers in SKILL.md) ----
SOURCE_CAPS = {
    "TOTW": 8,        # loudersound Tracks Of The Week — auto-include, hard ceiling 8
    "Progspace": 4,
    "TPM": 4,         # The PROG Mind
    "Subway": 3,      # The Progressive Subway
    "ArcticDrones": 3,
    "ProgArchives": 3,
    "postrock": 4,    # r/postrock + A Closer Listen pool
    "FJC": 4,         # Free Jazz Collective
    "Bandcamp": 4,
    "reserve": None,  # candidate-pool reserve: no cap, but never primary feed
}
MAX_PER_TAG = 4      # max tracks sharing one fine subgenre tag
MIN_TRACKS = 34

DEFAULT_SCENES = [
    "Japanese prog", "Zeuhl / Canterbury descendants", "Scandinavian",
    "Latin American", "Eastern European", "Israel / Middle East",
    "Australian / NZ", "East Asian jazz",
]


# ---------- auth ----------

def load_state():
    p = HOME / "state.json"
    state = json.loads(p.read_text()) if p.exists() else {}
    if "scene_rotation" not in state:  # v1 -> v2 migration, in memory only
        state["scene_rotation"] = {"scenes": DEFAULT_SCENES, "note": "index = week_counter mod len"}
    return state


class SpotifyClient:
    """Small stateful client that can refresh once during a long run."""

    def __init__(self, auth_path=AUTH):
        self.auth_path = Path(auth_path)
        self.auth = json.loads(self.auth_path.read_text())
        self.sp = self.auth["providers"]["spotify"]
        self.token = self.sp["access_token"]

    def refresh(self):
        data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": self.sp["refresh_token"],
            "client_id": self.sp["client_id"],
        }).encode()
        req = urllib.request.Request(ACCOUNTS, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            refreshed = json.load(r)
        now = datetime.now(timezone.utc)
        expires_in = int(refreshed.get("expires_in") or self.sp.get("expires_in") or 3600)
        self.token = refreshed["access_token"]
        self.sp["access_token"] = self.token
        self.sp["expires_in"] = expires_in
        self.sp["obtained_at"] = now.isoformat()
        self.sp["expires_at"] = (now + timedelta(seconds=expires_in)).isoformat()
        self.auth_path.write_text(json.dumps(self.auth, indent=2))

    def _request(self, url, payload=None, method="GET"):
        for attempt in (1, 2):
            headers = {"Authorization": f"Bearer {self.token}", "User-Agent": UA}
            data = None
            if payload is not None:
                headers["Content-Type"] = "application/json"
                data = json.dumps(payload).encode()
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    body = r.read().decode()
                    return r.status, json.loads(body) if body else {}
            except urllib.error.HTTPError as e:
                if e.code == 401 and attempt == 1:
                    self.refresh()
                    continue
                if e.code in (429, 500, 502, 503) and attempt == 1:
                    time.sleep(2.5)
                    continue
                raise
        raise RuntimeError("unreachable")

    def get(self, url):
        return self._request(url)

    def send(self, url, payload=None, method="POST"):
        return self._request(url, payload=payload, method=method)


def get_token():
    client = SpotifyClient()
    exp = client.sp.get("expires_at")
    if exp:
        try:
            epoch = datetime.fromisoformat(exp).timestamp() if isinstance(exp, str) else float(exp)
            if epoch - time.time() < 60:
                client.refresh()
        except Exception as e:
            print(f"WARN: token refresh failed ({e}); trying existing token", file=sys.stderr)
    return client.token


def norm(s):
    return "".join(c for c in s.casefold() if c.isalnum())


# ---------- deterministic draft/edition checks (no network) ----------

def check_draft(tracks):
    """Intra-edition deterministic checks on a verified draft / track list.
    Returns (errors, warnings); errors must block publish."""
    errors, warnings = [], []
    seen_uri, seen_artist = {}, {}
    for pos, t in enumerate(tracks, 1):
        uri, artist = t.get("uri", ""), t.get("artist", "")
        if uri and uri in seen_uri:
            errors.append(f"duplicate track: {artist} — {t.get('track', '?')} ({uri}) "
                          f"also listed at position {seen_uri[uri]}")
        elif uri:
            seen_uri[uri] = pos
        if artist and artist in seen_artist:
            errors.append(f"duplicate artist: {artist} (positions {seen_artist[artist]}, {pos}) "
                          f"— max one track per artist per edition")
        elif artist:
            seen_artist[artist] = pos
        missing = [f for f in ("lane", "source", "tag") if not str(t.get(f) or "").strip()]
        if missing:
            errors.append(f"missing provenance: {artist} — {t.get('track', '?')} ({uri}) "
                          f"lacks {','.join(missing)}")
    return errors, warnings


def _load_attribution(week):
    """Per-week published track list with lane/source/tag, from attribution.jsonl."""
    path = HOME / "attribution.jsonl"
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("week") == week:
            return rec
    return None


def cmd_pref(args):
    """pref show|add|remove|validate — deterministic management of the
    user-entered preference file. All mutations validate before writing;
    a bad file is never silently accepted (exit 8)."""
    ppath = HOME / "preferences.json"
    sub = args[0] if args else "show"

    def die(msgs):
        print("PREF INVALID:")
        for m in msgs:
            print("  -", m)
        sys.exit(8)

    if sub == "show":
        prefs = load_preferences(ppath)
        errs = validate_preferences(prefs)
        print(json.dumps(preference_summary(prefs) if not errs else {"invalid": errs}, indent=1))
        if errs:
            sys.exit(8)

    elif sub == "add":
        # pref add include|exclude Name [--note ...] [--added-by ...]
        # pref add boost Name --weight 1.5 [--note ...]
        if len(args) < 3:
            print("usage: pref add include|exclude|boost Name [--weight W] [--note T] [--added-by WHO]")
            sys.exit(1)
        kind, name = args[1], args[2]  # multi-word names: pass as one quoted arg
        i, opt = 3, {}
        while i < len(args):
            if args[i] == "--note":
                opt["note"] = args[i + 1]; i += 2
            elif args[i] == "--added-by":
                opt["added_by"] = args[i + 1]; i += 2
            elif args[i] == "--weight":
                try:
                    opt["weight"] = float(args[i + 1])
                except ValueError:
                    die([f"--weight must be a number, got {args[i + 1]!r}"])
                i += 2
            else:
                die([f"unknown option {args[i]!r}"])
        if kind == "boost":
            if "weight" not in opt:
                die(["boost entries require --weight (0.1–2.0)"])
            entry = {"name": name, "weight": opt["weight"], **{k: v for k, v in opt.items() if k != "weight"},
                     "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        else:
            entry = {"name": name, **opt,
                     "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        prefs = load_preferences(ppath)
        prefs.setdefault(kind, []).append(entry)
        errs = validate_preferences(prefs)
        if errs:
            die(errs + ["(file NOT modified)"])
        ppath.write_text(json.dumps(prefs, indent=1))
        print(json.dumps(preference_summary(prefs), indent=1))

    elif sub == "remove":
        if len(args) < 3:
            print("usage: pref remove include|exclude|boost Name")
            sys.exit(1)
        kind = args[1]
        target = norm(" ".join(args[2:]))
        prefs = load_preferences(ppath)
        before = len(prefs.get(kind, []))
        prefs[kind] = [e for e in prefs.get(kind, []) if norm(_pref_entry_name(e)) != target]
        if len(prefs[kind]) == before:
            print(f"no {kind} entry matching {args[2:]!r}")
            sys.exit(1)
        errs = validate_preferences(prefs)
        if errs:
            die(errs)
        ppath.write_text(json.dumps(prefs, indent=1))
        print(json.dumps(preference_summary(prefs), indent=1))

    elif sub == "validate":
        try:
            prefs = load_preferences(ppath)
        except json.JSONDecodeError as e:
            die([f"preferences.json is not valid JSON: {e}"])
        errs = validate_preferences(prefs)
        if errs:
            die(errs)
        print(json.dumps({"valid": True, **preference_summary(prefs)["counts"]}, indent=1))

    else:
        print("usage: pref show|add|remove|validate")
        sys.exit(1)


def cmd_handoff(date=None):
    """Build and validate the machine-verifiable delivery artifact
    site/data/<date>/handoff.json. Exits nonzero if any required field is
    missing or inconsistent with the published data — scheduler completion
    alone is never proof of success."""
    date = date or datetime.now().strftime("%Y-%m-%d")
    st = load_state()
    entry = next((p for p in st.get("playlists", []) if p["date"] == date), None)
    if not entry:
        print(f"HANDOFF FAILED: no published playlist for {date} in state.json")
        sys.exit(5)
    week = entry.get("week")

    ddir = HOME / "site" / "data" / date
    tpath = ddir / "tracks.json"
    epath = ddir / "edition.json"
    hpath = ddir / "handoff.json"
    if not tpath.exists():
        print(f"HANDOFF FAILED: {tpath} missing — build the site data first")
        sys.exit(5)
    tk = json.loads(tpath.read_text())
    ed = json.loads(epath.read_text()) if epath.exists() else {}
    tracks = tk["tracks"]
    uris = [t["uri"] for t in tracks]

    problems = list(check_draft_attribution(week, uris, ed, entry))

    playlist_url = entry.get("url") or ""
    playlist_id = playlist_url.rstrip("/").rsplit("/", 1)[-1]
    if "spotify.com/playlist/" not in playlist_url or not playlist_id:
        problems.append(f"playlist URL malformed or missing in state: {playlist_url!r}")
    if ed.get("playlist_url") and ed["playlist_url"] != playlist_url:
        problems.append(f"playlist URL mismatch: state={playlist_url} edition={ed['playlist_url']}")
    if ed.get("playlist_id") and playlist_id and ed["playlist_id"] != playlist_id:
        problems.append(f"playlist id mismatch: state={playlist_id} edition={ed['playlist_id']}")
    if entry.get("count") is not None and entry["count"] != len(uris):
        problems.append(f"track count mismatch: state.count={entry['count']} tracks.json={len(uris)}")
    if tk.get("total") is not None and tk["total"] != len(uris):
        problems.append(f"track count mismatch: tracks.json total={tk['total']} entries={len(uris)}")
    scene = entry.get("scene") or ed.get("scene")
    scene_mode = entry.get("scene_mode") or ed.get("scene_mode")
    if not scene:
        problems.append("scene missing (state and edition)")
    if not scene_mode:
        problems.append("scene_mode missing (state and edition)")
    if not (HOME / "site" / "out" / date / "index.html").exists():
        problems.append(f"site not built: site/out/{date}/index.html missing — run build_site.py")

    # QA is mandatory proof; a handoff without a successful run is invalid.
    qa = HOME / "site" / "qa.py"
    qa_exit = None
    if qa.exists():
        qa_exit = subprocess.call([sys.executable, str(qa)])
        if qa_exit != 0:
            problems.append(f"site QA failed (qa.py exit {qa_exit})")
    else:
        problems.append(f"qa.py not found at {qa}")
    if qa_exit != 0:
        problems.append(f"site QA proof must exit 0 (got {qa_exit})")

    attr = _attribution_tracks(week, ed)
    src_counts, tag_counts, lane_counts = {}, {}, {}
    for t in (attr or {}).get("tracks", []):
        lane_counts[t.get("lane") or "?"] = lane_counts.get(t.get("lane") or "?", 0) + 1
        src_counts[t.get("source") or "?"] = src_counts.get(t.get("source") or "?", 0) + 1
        tag_counts[t.get("tag") or "?"] = tag_counts.get(t.get("tag") or "?", 0) + 1
    if entry.get("lanes") and entry["lanes"] != lane_counts:
        problems.append(f"lane counts mismatch: state={entry['lanes']} attribution={lane_counts}")

    # B2: effective preferences must be valid and visible in every edition
    try:
        prefs = load_preferences()
    except json.JSONDecodeError as e:
        problems.append(f"preferences.json is not valid JSON: {e}")
        prefs = {"include": [], "exclude": [], "boost": []}
    pref_errors = validate_preferences(prefs)
    problems.extend(f"preferences: {e}" for e in pref_errors)
    pref_sum = preference_summary(prefs)

    handoff = {
        "schema": "prog-discovery/handoff/v1",
        "date": date,
        "week": week,
        "playlist_id": playlist_id,
        "playlist_url": playlist_url,
        "track_count": len(uris),
        "scene": scene,
        "scene_mode": scene_mode,
        "lane_counts": lane_counts,
        "source_counts": src_counts,
        "tag_counts": tag_counts,
        "effective_preferences": pref_sum,
        "site_url": f"https://music.hively.dev/{date}/",
        "qa": {"exit": qa_exit, "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
    }
    for f in ("playlist_id", "playlist_url", "track_count", "scene", "scene_mode",
              "lane_counts", "source_counts", "tag_counts", "site_url"):
        if not handoff.get(f):
            problems.append(f"required handoff field empty: {f}")

    if problems:
        print("HANDOFF FAILED:")
        for p in problems:
            print("  -", p)
        sys.exit(6)
    hpath.write_text(json.dumps(handoff, indent=1))
    (ddir / "preferences.json").write_text(json.dumps(pref_sum, indent=1))  # B2 visibility
    print(json.dumps(handoff, indent=1))


def _attribution_tracks(week, ed):
    """Load week's attribution record enriched with edition.json tags/lanes.
    Legacy records (pre-2026-09-05) carry lane+source but no tag; edition.json
    tags/lanes are the site-side authority. Returns None if no record."""
    attr = _load_attribution(week)
    if attr is None:
        return None
    ed_tags = ed.get("tags") or {}
    ed_lanes = ed.get("lanes") or {}
    for t in attr.get("tracks", []):
        if not (t.get("tag") or "").strip():
            t["tag"] = ed_tags.get(t.get("uri"), "")
        if not (t.get("lane") or "").strip():
            t["lane"] = ed_lanes.get(t.get("uri"), "")
    return attr


def check_draft_attribution(week, uris, ed, entry):
    """Cross-check the published attribution log against the site track list.
    Yields problem strings; deterministic, no network."""
    attr = _attribution_tracks(week, ed)
    if attr is None:
        yield f"no attribution.jsonl record for week {week} — cannot verify source provenance"
        return
    a_uris = [t["uri"] for t in attr.get("tracks", [])]
    if set(a_uris) != set(uris):
        extra = sorted(set(a_uris) - set(uris))[:3]
        missing = sorted(set(uris) - set(a_uris))[:3]
        yield (f"attribution/tracks.json track set mismatch: "
               f"only-in-attribution={extra} only-in-tracks.json={missing}")
    errors, _ = check_draft(attr.get("tracks", []))
    yield from errors
    if attr.get("playlist") and entry.get("url") and attr["playlist"] not in entry["url"]:
        yield f"attribution playlist {attr['playlist']} != state url {entry['url']}"


# ---------- explicit preference feedback (B2) ----------
# User-entered include/exclude/boost notes ONLY. Never derived from Spotify
# listening history, plays, skips, or related-artist feeds; validate refuses
# any entry whose provenance claims playback derivation.

PREF_CAPS = {"include": 50, "exclude": 50, "boost": 20}
PREF_WEIGHT_MIN, PREF_WEIGHT_MAX = 0.1, 2.0
FORBIDDEN_ORIGIN_TOKENS = (
    "listening-history", "listening history", "recently-played", "recently played",
    "played", "plays", "skips", "skipped", "playback", "related-artist",
    "related artist", "spotify-history", "auto-infer",
)


def _pref_entry_name(e):
    return e["name"] if isinstance(e, dict) else e


def _origin_forbidden(e):
    if not isinstance(e, dict):
        return False
    origin = str(e.get("origin") or e.get("source") or e.get("derived_from") or "").casefold()
    return any(tok in origin for tok in FORBIDDEN_ORIGIN_TOKENS)


def load_preferences(path=None):
    p = Path(path) if path else HOME / "preferences.json"
    if not p.exists():
        return {"include": [], "exclude": [], "boost": []}
    return json.loads(p.read_text())


def validate_preferences(prefs):
    """Bounded-schema validation. Returns error strings; empty list = valid.
    Fails loudly on caps, bad weights, cross-list duplicates, unknown keys,
    and any playback-derived provenance — nothing is silently dropped."""
    errors = []
    if not isinstance(prefs, dict):
        return ["preferences: top level must be an object"]
    unknown = sorted(set(prefs) - set(PREF_CAPS))
    if unknown:
        errors.append(f"preferences: unknown top-level keys {unknown} (allowed: {sorted(PREF_CAPS)})")
    seen = {}
    for key in ("include", "exclude"):
        lst = prefs.get(key, [])
        if not isinstance(lst, list):
            errors.append(f"preferences.{key}: must be a list")
            continue
        if len(lst) > PREF_CAPS[key]:
            errors.append(f"preferences.{key}: {len(lst)} entries > cap {PREF_CAPS[key]}")
        for e in lst:
            name = _pref_entry_name(e)
            if not isinstance(name, str) or not name.strip():
                errors.append(f"preferences.{key}: entry missing non-empty name: {e!r}")
                continue
            if _origin_forbidden(e):
                errors.append(f"preferences.{key}: entry {name!r} has playback-derived "
                              f"provenance — preferences must be user-entered only")
            n = norm(name)
            if n in seen:
                errors.append(f"preferences: {name!r} appears in both {seen[n]} and {key}")
            else:
                seen[n] = key
    boost = prefs.get("boost", [])
    if not isinstance(boost, list):
        errors.append("preferences.boost: must be a list")
        return errors
    if len(boost) > PREF_CAPS["boost"]:
        errors.append(f"preferences.boost: {len(boost)} entries > cap {PREF_CAPS['boost']}")
    bnames = set()
    for e in boost:
        if not isinstance(e, dict):
            errors.append(f"preferences.boost: entries must be objects with name+weight: {e!r}")
            continue
        name = e.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"preferences.boost: entry missing non-empty name: {e!r}")
            continue
        if _origin_forbidden(e):
            errors.append(f"preferences.boost: entry {name!r} has playback-derived "
                          f"provenance — preferences must be user-entered only")
        w = e.get("weight")
        if isinstance(w, bool) or not isinstance(w, (int, float)):
            errors.append(f"preferences.boost: {name!r} weight {w!r} must be a number "
                          f"in [{PREF_WEIGHT_MIN}, {PREF_WEIGHT_MAX}]")
        elif not (PREF_WEIGHT_MIN <= float(w) <= PREF_WEIGHT_MAX):
            errors.append(f"preferences.boost: {name!r} weight {w} outside "
                          f"[{PREF_WEIGHT_MIN}, {PREF_WEIGHT_MAX}]")
        n = norm(name)
        if n in bnames:
            errors.append(f"preferences.boost: duplicate entry for {name!r}")
        bnames.add(n)
        if n in seen:
            errors.append(f"preferences: {name!r} appears in both {seen[n]} and boost")
        else:
            seen[n] = "boost"
    return errors


def preference_summary(prefs):
    """Post-validation summary recorded into the edition data dir and handoff.json,
    so every published edition shows which preference notes influenced it."""
    def ent(e):
        d = {"name": _pref_entry_name(e)}
        if isinstance(e, dict):
            if e.get("note"):
                d["note"] = e["note"]
            if e.get("added_by"):
                d["added_by"] = e["added_by"]
            if e.get("added_at"):
                d["added_at"] = e["added_at"]
            if "weight" in e:
                d["weight"] = e["weight"]
        return d
    return {
        "source": "user-entered preferences.json — never Spotify listening history",
        "include": [ent(e) for e in prefs.get("include", [])],
        "exclude": [ent(e) for e in prefs.get("exclude", [])],
        "boost": [ent(e) for e in prefs.get("boost", [])],
        "counts": {k: len(prefs.get(k, [])) for k in PREF_CAPS},
    }


def apply_preferences(candidates, prefs):
    """Editorial-only consumption of preferences in the harvest/draft phase.
    Pure and deterministic (no network): excluded names are dropped, included
    names sort first, boost weights multiply a candidate's score (stable order
    otherwise). Returns (ranked_candidates, summary_with_applied_notes)."""
    inc = {norm(_pref_entry_name(e)): _pref_entry_name(e) for e in prefs.get("include", [])}
    exc = {norm(_pref_entry_name(e)): _pref_entry_name(e) for e in prefs.get("exclude", [])}
    boosts, boost_names = {}, {}
    for e in prefs.get("boost", []):
        if isinstance(e, dict) and isinstance(e.get("weight"), (int, float)):
            n = norm(_pref_entry_name(e))
            boosts[n] = float(e["weight"])
            boost_names[n] = _pref_entry_name(e)
    scored, dropped = [], []
    matched_inc, matched_boost = set(), set()
    for c in candidates:
        keys = {norm(str(c.get("artist") or "")), norm(str(c.get("track") or ""))}
        if keys & set(exc):
            dropped.append(f"{c.get('artist', '?')} — {c.get('track', '?')}")
            continue
        score = 1.0
        hit = keys & set(inc)
        if hit:
            score += 1000.0
            matched_inc |= hit
        for k, w in boosts.items():
            if k in keys:
                score *= w
                matched_boost.add(k)
        scored.append((score, c))
    scored.sort(key=lambda sc: -sc[0])  # stable: ties keep harvest order
    summary = preference_summary(prefs)
    summary["applied"] = {
        "include_matched": [inc[k] for k in sorted(matched_inc)],
        "boost_matched": [{"name": boost_names[k], "weight": boosts[k]}
                          for k in sorted(matched_boost)],
        "excluded_candidates": dropped,
    }
    return [c for _, c in scored], summary


# ---------- subcommands ----------

def cmd_scene():
    st = load_state()
    scenes = st.get("scene_rotation", {}).get("scenes", DEFAULT_SCENES)
    week = st.get("week_counter", 0) + 1
    entry = scenes[(week - 1) % len(scenes)]
    if isinstance(entry, dict):
        scene_name, scene_short = entry["name"], entry.get("short", entry["name"])
        mode = entry.get("mode", "living")   # legacy entries default to living
        angle = entry.get("angle", "")
        proposed = entry.get("proposed", False)
    else:
        scene_name = scene_short = entry
        mode, angle, proposed = "living", "", False
    print(json.dumps({"week": week, "scene": scene_name, "scene_short": scene_short,
                      "mode": mode, "angle": angle, "proposed": proposed}))


def published_track_uris():
    """Return tracks from published edition data for repeat protection only."""
    uris = set()
    for path in (HOME / "site" / "data").glob("*/tracks.json"):
        try:
            uris.update(t["uri"] for t in json.loads(path.read_text()).get("tracks", []))
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
    return uris


def cmd_verify(candidates_path=None):
    client = SpotifyClient()
    exp = client.sp.get("expires_at")
    if exp:
        try:
            epoch = datetime.fromisoformat(exp).timestamp()
            if epoch - time.time() < 60:
                client.refresh()
        except Exception as e:
            print(f"WARN: token refresh failed ({e}); trying existing token", file=sys.stderr)
    cpath = Path(candidates_path) if candidates_path else HOME / "candidates-week.json"
    cands = json.loads(cpath.read_text())
    if isinstance(cands, dict):
        cands = cands.get("candidates", cands.get("tracks", []))

    st = load_state()
    week = st.get("week_counter", 0) + 1

    verified, failures, warnings, artist_cache = [], [], [], {}
    for c in cands:
        # Recovery candidates may carry a Spotify URI/URL from the editorial
        # harvest or web-player lookup.  Resolve those directly so a spent
        # catalog-search quota cannot invalidate an otherwise complete draft.
        candidate_uri = c.get("uri") or c.get("spotify_uri") or c.get("spotify_url")
        if candidate_uri:
            track_id = str(candidate_uri).rstrip("/").split("/")[-1].split(":")[-1]
            try:
                _, t = client.get(f"{API}/tracks/{track_id}")
                items = [t] if isinstance(t, dict) and t.get("id") else []
            except Exception as e:
                failures.append({**c, "reason": f"direct track lookup error: {e}"})
                continue
        else:
            q = urllib.parse.urlencode({"q": f"{c['artist']} {c['track']}", "type": "track", "limit": "1"})
            try:
                _, res = client.get(f"{API}/search?{q}")
                items = res.get("tracks", {}).get("items", []) or res.get("items", [])
            except Exception as e:
                failures.append({**c, "reason": f"search error: {e}"})
                continue
            if not items:
                failures.append({**c, "reason": "not found"})
                continue
        if not items:
            failures.append({**c, "reason": "not found"})
            continue
        t = items[0]
        names = [a["name"] for a in t.get("artists", [])]
        if norm(c["artist"]) not in {norm(n) for n in names}:
            failures.append({**c, "reason": f"artist mismatch (found: {names[0]} — {t['name']})"})
            continue
        uri = t["uri"]
        if uri in published_track_uris():
            failures.append({**c, "reason": "REPEAT: track already present in a published edition"})
            continue
        # Spotify removed Artist.followers and Artist.popularity from the
        # Web API in February 2026. Do not make a second request that can only
        # return nulls (or turn an editorial candidate into a silent failure).
        # Obscurity is now an editorial/source-evidence decision; preserve the
        # fields as null for backwards-compatible draft consumers.
        verified.append({
            "artist": c["artist"], "track": t["name"], "album": t.get("album", {}).get("name", ""),
            "uri": uri, "lane": c.get("lane", "?"), "source": c.get("source", "?"),
            "tag": c.get("tag") or c.get("subgenre") or "",
            "followers": None, "popularity": None,
        })
        time.sleep(0.15)  # gentle on rate limits

    # per-source and per-tag cap counts over VERIFIED candidates (audit S-5/S-7)
    src_counts, tag_counts = {}, {}
    for v in verified:
        src_counts[v["source"]] = src_counts.get(v["source"], 0) + 1
        if v.get("tag"):
            tag_counts[v["tag"]] = tag_counts.get(v["tag"], 0) + 1
    cap_violations = []
    for s, n in sorted(src_counts.items()):
        cap = SOURCE_CAPS.get(s)
        if cap is not None and n > cap:
            cap_violations.append(f"source {s}: {n} verified > cap {cap}")
    tag_violations = [f"tag {t}: {n} > {MAX_PER_TAG}" for t, n in sorted(tag_counts.items()) if n > MAX_PER_TAG]

    out = {"week": week, "tracks": verified}
    (HOME / "draft.json").write_text(json.dumps(out, indent=1))
    # deterministic pre-publish checks: dupes + per-track provenance (no network)
    d_errors, _ = check_draft(verified)
    if d_errors:
        print("DETERMINISTIC CHECK FAILURES (draft written but DO NOT publish):")
        for e in d_errors:
            print("  -", e)
    print(json.dumps({"verified": len(verified), "failed": len(failures), "failures": failures,
                      "warnings": warnings, "source_counts": src_counts, "tag_counts": tag_counts,
                      "cap_violations": cap_violations + tag_violations}, indent=1))
    if failures:
        print("ACTION: swap failed candidates in candidates-week.json and re-run verify.")
    if cap_violations or tag_violations:
        print("ACTION: trim over-cap sources/tags before sequencing; publish will refuse.")
    if d_errors:
        sys.exit(7)


def cmd_publish(week=None, date=None, min_tracks=None):
    min_tracks = min_tracks or MIN_TRACKS
    client = SpotifyClient()
    st = load_state()
    draft = json.loads((HOME / "draft.json").read_text())
    tracks = draft["tracks"]
    if len(tracks) < min_tracks:
        print(f"REFUSED: draft has {len(tracks)} tracks, minimum is {min_tracks}. "
              "Harvest more candidates, verify again.")
        sys.exit(2)

    # per-source / per-tag caps enforced at publish (audit S-5/S-7)
    src_counts, tag_counts = {}, {}
    for t in tracks:
        src_counts[t.get("source", "?")] = src_counts.get(t.get("source", "?"), 0) + 1
        tg = t.get("tag") or ""
        if tg:
            tag_counts[tg] = tag_counts.get(tg, 0) + 1
    violations = [f"source {s}: {n} > cap {SOURCE_CAPS[s]}" for s, n in sorted(src_counts.items())
                  if SOURCE_CAPS.get(s) is not None and n > SOURCE_CAPS[s]]
    violations += [f"tag {t}: {n} > {MAX_PER_TAG}" for t, n in sorted(tag_counts.items()) if n > MAX_PER_TAG]
    if violations:
        print("REFUSED: per-source/per-tag cap violations (state untouched):")
        for v in violations:
            print("  -", v)
        print(json.dumps({"source_counts": src_counts, "tag_counts": tag_counts}, indent=1))
        sys.exit(4)
    # deterministic repeat/provenance gate (dupes, missing lane/source/tag)
    d_errors, _ = check_draft(tracks)
    if d_errors:
        print("REFUSED: deterministic check failures (state untouched):")
        for e in d_errors:
            print("  -", e)
        sys.exit(7)

    week = week or draft.get("week") or st.get("week_counter", 0) + 1
    date = date or datetime.now().strftime("%Y-%m-%d")
    scenes = st.get("scene_rotation", {}).get("scenes", DEFAULT_SCENES)
    entry = scenes[(week - 1) % len(scenes)]
    if isinstance(entry, dict):
        scene_short = entry.get("short", entry["name"])
        scene_mode = entry.get("mode", "living")
    else:
        scene_short, scene_mode = entry, "living"
    # agent may override the wheel's mode via draft.json scene_mode/scene_reason
    scene_mode = draft.get("scene_mode") or scene_mode
    scene_reason = str(draft.get("scene_reason") or "").strip()
    if scene_mode not in {"lineage", "living", "moment", "microgenre"}:
        print(f"REFUSED: invalid scene_mode {scene_mode!r}; choose lineage, living, moment, or microgenre (state untouched).")
        sys.exit(7)
    if not scene_reason:
        print("REFUSED: scene_reason is required; the LLM must explain the evidence-based story before publish (state untouched).")
        sys.exit(7)
    name = f"Prog & Jazz Discovery — {date} · {scene_short}"

    _, pl = client.send(f"{API}/me/playlists",
                     {"name": name, "public": True,
                      "description": f"Week {week} · featured scene: {scene_short}. Editorial discovery — core prog / jazz-fusion / fringe lanes."})
    pid = pl["id"]

    uris = [t["uri"] for t in tracks]
    for i in range(0, len(uris), 50):
        client.send(f"{API}/playlists/{pid}/items", {"uris": uris[i:i + 50]})

    # count check via playlist root (new API shape: items.total)
    _, root = client.get(f"{API}/playlists/{pid}")
    total = root.get("items", {}).get("total", 0)
    lanes = {}
    for t in tracks:
        lanes[t["lane"]] = lanes.get(t["lane"], 0) + 1

    ok = total == len(uris)
    if ok:
        # state updates ONLY on verified publish (atomicity)
        st["week_counter"] = week
        st.setdefault("playlists", []).append(
            {"week": week, "date": date, "url": f"https://open.spotify.com/playlist/{pid}",
             "count": total, "lanes": lanes,
             "scene": scene_short, "scene_mode": scene_mode, "scene_reason": scene_reason})
        (HOME / "state.json").write_text(json.dumps(st, indent=2))
        # attribution log for source-weight auditing
        log_path = HOME / "attribution.jsonl"
        with open(log_path, "a") as f:
            f.write(json.dumps({"week": week, "date": date, "playlist": pid,
                                "tracks": tracks}) + "\n")

    print(json.dumps({
        "url": f"https://open.spotify.com/playlist/{pid}", "name": name,
        "expected": len(uris), "actual_total": total,
        "lanes": lanes, "source_counts": src_counts, "tag_counts": tag_counts,
        "scene": scene_short, "scene_mode": scene_mode,
        "ok": ok,
        "state_updated": ok,
    }, indent=1))
    if not ok:
        print("MISMATCH: playlist total != added URIs; investigate before delivering.")
        sys.exit(3)


def cmd_selftest():
    client = SpotifyClient()
    _, pl = client.send(f"{API}/me/playlists",
                     {"name": "PD pipeline selftest (deleted)", "public": False})
    pid = pl["id"]
    q = urllib.parse.urlencode({"q": "Slift It's Something", "type": "track", "limit": "1"})
    _, res = client.get(f"{API}/search?{q}")
    uri = res["tracks"]["items"][0]["uri"]
    client.send(f"{API}/playlists/{pid}/items", {"uris": [uri]})
    _, root = client.get(f"{API}/playlists/{pid}")
    total = root.get("items", {}).get("total", 0)
    client.send(f"{API}/playlists/{pid}/followers", method="DELETE")
    print(json.dumps({"created": True, "added": 1, "counted": total, "deleted": True,
                      "full_path_ok": total == 1}))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "scene":
        cmd_scene()

    elif cmd == "verify":
        cmd_verify(sys.argv[sys.argv.index("--candidates") + 1] if "--candidates" in sys.argv else None)
    elif cmd == "publish":
        kw = {}
        if "--week" in sys.argv:
            kw["week"] = int(sys.argv[sys.argv.index("--week") + 1])
        if "--date" in sys.argv:
            kw["date"] = sys.argv[sys.argv.index("--date") + 1]
        cmd_publish(**kw)
    elif cmd == "pref":
        cmd_pref(sys.argv[2:])
    elif cmd == "handoff":
        if "--skip-qa" in sys.argv:
            print("HANDOFF FAILED: --skip-qa is not supported; QA proof is mandatory")
            sys.exit(2)
        cmd_handoff(sys.argv[sys.argv.index("--date") + 1] if "--date" in sys.argv else None)
    elif cmd == "selftest":
        cmd_selftest()
    else:
        print(__doc__)
        sys.exit(1)
