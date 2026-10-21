#!/usr/bin/env python3
"""Portable, fixture-friendly QA gate for the generated Now Spinning site."""
import json
import re
from collections import Counter
from pathlib import Path


def _read_json(path, failures):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"cannot read {path.name}: {exc}")
        return None


def run_qa(site_root):
    """Validate generated pages against the site's data directory.

    Returns a list of human-readable failures. The caller supplies a site root,
    which lets unit tests use isolated temporary fixtures.
    """
    site_root = Path(site_root)
    data_root = site_root / "data"
    out_root = site_root / "out"
    failures = []

    if not out_root.is_dir():
        return [f"site not built: missing {out_root}"]
    if not data_root.is_dir():
        return [f"site data missing: {data_root}"]

    edition_dirs = sorted(path for path in data_root.iterdir() if path.is_dir())
    if not edition_dirs:
        failures.append("no edition data found")

    seen_tracks = {}
    for data_dir in edition_dirs:
        date = data_dir.name
        edition = _read_json(data_dir / "edition.json", failures)
        tracks_doc = _read_json(data_dir / "tracks.json", failures)
        if not isinstance(edition, dict) or not isinstance(tracks_doc, dict):
            continue

        tracks = tracks_doc.get("tracks")
        if not isinstance(tracks, list):
            failures.append(f"{date}: tracks.json has no tracks list")
            continue
        uris = [track.get("uri") for track in tracks if isinstance(track, dict)]
        if len(uris) != len(tracks) or any(not uri for uri in uris):
            failures.append(f"{date}: tracks.json has malformed track records")

        duplicates = [uri for uri, count in Counter(uris).items() if count > 1]
        if duplicates:
            failures.append(f"{date}: duplicate track URI(s): {duplicates[:3]}")

        for uri in uris:
            if uri in seen_tracks:
                failures.append(f"cross-edition track repeats: {uri} in {seen_tracks[uri]} and {date}")
            else:
                seen_tracks[uri] = date

        artists = []
        for track in tracks:
            if isinstance(track, dict):
                artists.extend(name.strip().casefold() for name in track.get("artists", [])
                               if isinstance(name, str) and name.strip())
        duplicate_artists = [name for name, count in Counter(artists).items() if count > 1]
        if duplicate_artists:
            failures.append(f"{date}: duplicate artist(s): {duplicate_artists[:3]}")

        uri_set = set(uris)
        blurbs = edition.get("blurbs") or {}
        tags = edition.get("tags") or {}
        lanes = edition.get("lanes") or {}
        sources = edition.get("sources") or {}
        if set(blurbs) != uri_set:
            failures.append(f"{date}: blurbs do not match tracks.json")
        if set(tags) != uri_set:
            failures.append(f"{date}: tags do not match tracks.json")
        if set(lanes) != uri_set or any(not str(lanes.get(uri, "")).strip() for uri in uri_set):
            failures.append(f"{date}: missing or extra track lanes")
        for uri, blurb in blurbs.items():
            if not isinstance(blurb, dict) or blurb.get("src") not in sources:
                failures.append(f"{date}: missing source attribution for {uri}")

        if not (edition.get("theme") or {}).get("paras"):
            failures.append(f"{date}: theme essay missing")
        if edition.get("scene") and not edition.get("scene_mode"):
            failures.append(f"{date}: scene present but scene_mode missing")

        page = out_root / date / "index.html"
        if not page.is_file():
            failures.append(f"{date}: built edition page missing")
            continue
        raw = page.read_text(encoding="utf-8")
        if edition.get("playlist_url") and edition["playlist_url"] not in raw:
            failures.append(f"{date}: playlist URL missing from built page")

        page_track_ids = set(re.findall(
            r'<[^>]*class="sleeve[^"]*"[^>]*data-tid="([^"]+)"', raw))
        expected_ids = {str(uri).rsplit(":", 1)[-1] for uri in uris}
        if page_track_ids != expected_ids:
            failures.append(f"{date}: page/tracks.json mismatch")

        sleeves = len(page_track_ids)
        modals = len(re.findall(r'class="modal-back"', raw))
        modal_ids = re.findall(r'id="modal-([0-9A-Za-z]+)"', raw)
        if sleeves != modals or modals != len(set(modal_ids)):
            failures.append(f"{date}: sleeve/modal/unique-id mismatch")
        if "<style>" not in raw or "</style>" not in raw:
            failures.append(f"{date}: missing style wrapper")

    front_path = out_root / "index.html"
    explore_path = out_root / "explore" / "index.html"
    if not front_path.is_file():
        failures.append("front page missing")
    else:
        front = front_path.read_text(encoding="utf-8")
        mast_end = front.find("</header>")
        stats = front.find('class="stats-row"')
        nav = front.find("<nav")
        hero = front.find('class="hero"')
        if not (0 <= mast_end < stats < nav < hero):
            failures.append("front: stats bar misplaced")
        source_line = re.search(r"Sourced from the week.{0,2000}?</div>", front, re.S)
        if source_line:
            outlets = re.findall(r'rel="noopener">([^<]+)</a>', source_line.group(0))
            if len(outlets) != len(set(outlets)):
                failures.append("front: duplicate outlets in source line")
    if not explore_path.is_file():
        failures.append("explore page missing")

    return failures


def main():
    failures = run_qa(Path(__file__).resolve().parent)
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        raise SystemExit(1)
    print("ok: site QA passed")


if __name__ == "__main__":
    main()
