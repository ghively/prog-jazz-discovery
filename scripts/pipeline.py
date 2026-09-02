#!/usr/bin/env python3
"""Prog & Jazz Discovery pipeline — mechanical Spotify work as ONE tool call each.

The agent does editorial work (harvest, selection judgment); this script does
the mechanical API loops so a small model never burns context on 38 searches.

Subcommands:
  scene     Print this week's featured scene (rotation wheel from state.json)
  seeds     Listening feedback: which past picks were played/saved -> artist seeds
  verify    Verify candidates file on Spotify (batched in-process) -> draft.json
  publish   Create Week N playlist from draft.json, add tracks, verify count
  selftest  Create+verify+DELETE a throwaway playlist (proves the full path)

Files (override dir with $PD_HOME, default ~/.hermes/prog-discovery):
  state.json               week counter, played history, scene wheel
  candidates-week.json     INPUT: [{artist, track, lane, source}, ...]
  draft.json               OUTPUT of verify: verified tracks + URIs + attribution

Auth: reads Spotify entry from Hermes auth.json ($HERMES_AUTH_JSON,
default ~/.hermes/auth.json); PKCE-refreshes the access token when expired.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
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


def get_token():
    d = json.loads(AUTH.read_text())
    sp = d["providers"]["spotify"]
    exp = sp.get("expires_at")
    tok = sp["access_token"]
    if exp:
        try:
            epoch = datetime.fromisoformat(exp).timestamp() if isinstance(exp, str) else float(exp)
            if epoch - time.time() < 60:
                data = urllib.parse.urlencode({
                    "grant_type": "refresh_token",
                    "refresh_token": sp["refresh_token"],
                    "client_id": sp["client_id"],
                }).encode()
                req = urllib.request.Request(ACCOUNTS, data=data, method="POST")
                with urllib.request.urlopen(req, timeout=15) as r:
                    tok = json.load(r)["access_token"]
                sp["access_token"] = tok
                sp["expires_at"] = datetime.now(timezone.utc).isoformat()
                sp["obtained_at"] = sp["expires_at"]
                AUTH.write_text(json.dumps(d, indent=2))
        except Exception as e:
            print(f"WARN: token refresh failed ({e}); trying existing token", file=sys.stderr)
    return tok


def api_get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": UA})
    return _retry(req)


def api_send(url, token, payload=None, method="POST"):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": UA}
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    return _retry(req)


def _retry(req):
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read().decode()
                return r.status, json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt == 1:
                time.sleep(2.5)
                continue
            raise
    raise RuntimeError("unreachable")


def norm(s):
    return "".join(c for c in s.casefold() if c.isalnum())


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


def cmd_seeds():
    token = get_token()
    st = load_state()

    # recently played (handle both old and new item shapes)
    _, recent = api_get(f"{API}/me/player/recently-played?limit=50", token)
    played_tracks = {}
    for it in recent.get("items", []):
        t = it.get("track") or it.get("item") or {}
        if t.get("id"):
            played_tracks[t["id"]] = (t["artists"][0]["name"], t["name"])

    # last playlist from state
    ours = {}
    playlists = st.get("playlists", [])
    if playlists:
        pid = playlists[-1]["url"].rstrip("/").split("/")[-1]
        _, pl = api_get(f"{API}/playlists/{pid}", token)
        page = pl.get("items", {})
        for it in page.get("items", []) if isinstance(page, dict) else []:
            t = it.get("item") or it.get("track") or {}
            if t.get("id"):
                ours[t["id"]] = (t["artists"][0]["name"], t["name"])

    # saved signal for our tracks
    saved_ids = []
    if ours:
        ids = list(ours)[:50]
        qs = urllib.parse.urlencode({"ids": ",".join(ids)})
        try:
            _, arr = api_get(f"{API}/me/tracks/contains?{qs}", token)
            saved_ids = [i for i, flag in zip(ids, arr) if flag]
        except Exception:
            pass  # endpoint optional

    played_ours = {tid: v for tid, v in ours.items() if tid in played_tracks}
    saved_ours = {tid: ours[tid] for tid in saved_ids if tid in ours}
    seed_artists = sorted({a for a, _ in {**played_ours, **saved_ours}.values()})
    print(json.dumps({
        "last_week_playlist": playlists[-1]["url"] if playlists else None,
        "played_from_ours": [f"{a} — {t}" for a, t in played_ours.values()],
        "saved_from_ours": [f"{a} — {t}" for a, t in saved_ours.values()],
        "seed_artists": seed_artists,
        "hint": "Bias this week's feedback-lane candidates toward styles/scenes adjacent to seed_artists; obscurity gate still applies.",
    }, indent=1))


def _played_artists_map(st):
    """played_artists may be a flat list (v2) or {artist: last_week} (v3). Normalize to a map."""
    pa = st.get("played_artists", [])
    if isinstance(pa, dict):
        return dict(pa)
    return {a: None for a in pa}


def cmd_verify(candidates_path=None):
    token = get_token()
    cpath = Path(candidates_path) if candidates_path else HOME / "candidates-week.json"
    cands = json.loads(cpath.read_text())
    if isinstance(cands, dict):
        cands = cands.get("candidates", cands.get("tracks", []))

    st = load_state()
    played_tracks = set(st.get("played_tracks", []))
    played_artists = _played_artists_map(st)
    week = st.get("week_counter", 0) + 1

    verified, failures, warnings, artist_cache = [], [], [], {}
    for c in cands:
        q = urllib.parse.urlencode({"q": f"{c['artist']} {c['track']}", "type": "track", "limit": "1"})
        try:
            _, res = api_get(f"{API}/search?{q}", token)
            items = res.get("tracks", {}).get("items", []) or res.get("items", [])
        except Exception as e:
            failures.append({**c, "reason": f"search error: {e}"})
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
        if uri in played_tracks:
            failures.append({**c, "reason": "REPEAT: track already published (played_tracks)"})
            continue
        if c["artist"] in played_artists:
            last = played_artists[c["artist"]]
            when = f"week {last}" if last else "an earlier week"
            warnings.append(f"{c['artist']} appeared in {when} (8-week cooldown rule)")
        # obscurity data: primary artist followers + popularity (one call per NEW artist)
        followers = popularity = None
        primary_id = (t.get("artists") or [{}])[0].get("id")
        if primary_id:
            if primary_id in artist_cache:
                followers, popularity = artist_cache[primary_id]
            else:
                try:
                    _, art = api_get(f"{API}/artists/{primary_id}", token)
                    followers, popularity = art.get("followers", {}).get("total"), art.get("popularity")
                except Exception:
                    pass
                artist_cache[primary_id] = (followers, popularity)
        verified.append({
            "artist": c["artist"], "track": t["name"], "album": t.get("album", {}).get("name", ""),
            "uri": uri, "lane": c.get("lane", "?"), "source": c.get("source", "?"),
            "tag": c.get("tag") or c.get("subgenre") or "",
            "followers": followers, "popularity": popularity,
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
    print(json.dumps({"verified": len(verified), "failed": len(failures), "failures": failures,
                      "warnings": warnings, "source_counts": src_counts, "tag_counts": tag_counts,
                      "cap_violations": cap_violations + tag_violations}, indent=1))
    if failures:
        print("ACTION: swap failed candidates in candidates-week.json and re-run verify.")
    if cap_violations or tag_violations:
        print("ACTION: trim over-cap sources/tags before sequencing; publish will refuse.")


def cmd_publish(week=None, date=None, min_tracks=None):
    min_tracks = min_tracks or MIN_TRACKS
    token = get_token()
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
    scene_reason = draft.get("scene_reason", "")
    name = f"Prog & Jazz Discovery — {date} · {scene_short}"

    _, pl = api_send(f"{API}/me/playlists", token,
                     {"name": name, "public": True,
                      "description": f"Week {week} · featured scene: {scene_short}. Editorial discovery — core prog / jazz-fusion / fringe lanes."})
    pid = pl["id"]

    uris = [t["uri"] for t in tracks]
    for i in range(0, len(uris), 50):
        api_send(f"{API}/playlists/{pid}/items", token, {"uris": uris[i:i + 50]})

    # count check via playlist root (new API shape: items.total)
    _, root = api_get(f"{API}/playlists/{pid}", token)
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
        # played_artists v3: {artist: last_week} so the 8-week cooldown is computable
        pa = st.get("played_artists", [])
        played_a = dict(pa) if isinstance(pa, dict) else {a: None for a in pa}
        played_t = set(st.get("played_tracks", []))
        for t in tracks:
            played_a[t["artist"]] = week
            played_t.add(t["uri"])
        st["played_artists"] = dict(sorted(played_a.items()))
        st["played_tracks"] = sorted(played_t)
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
    token = get_token()
    _, pl = api_send(f"{API}/me/playlists", token,
                     {"name": "PD pipeline selftest (deleted)", "public": False})
    pid = pl["id"]
    q = urllib.parse.urlencode({"q": "Slift It's Something", "type": "track", "limit": "1"})
    _, res = api_get(f"{API}/search?{q}", token)
    uri = res["tracks"]["items"][0]["uri"]
    api_send(f"{API}/playlists/{pid}/items", token, {"uris": [uri]})
    _, root = api_get(f"{API}/playlists/{pid}", token)
    total = root.get("items", {}).get("total", 0)
    api_send(f"{API}/playlists/{pid}/followers", token, method="DELETE")
    print(json.dumps({"created": True, "added": 1, "counted": total, "deleted": True,
                      "full_path_ok": total == 1}))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "scene":
        cmd_scene()
    elif cmd == "seeds":
        cmd_seeds()
    elif cmd == "verify":
        cmd_verify(sys.argv[sys.argv.index("--candidates") + 1] if "--candidates" in sys.argv else None)
    elif cmd == "publish":
        kw = {}
        if "--week" in sys.argv:
            kw["week"] = int(sys.argv[sys.argv.index("--week") + 1])
        if "--date" in sys.argv:
            kw["date"] = sys.argv[sys.argv.index("--date") + 1]
        cmd_publish(**kw)
    elif cmd == "selftest":
        cmd_selftest()
    else:
        print(__doc__)
        sys.exit(1)
