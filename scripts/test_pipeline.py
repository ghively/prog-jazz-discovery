#!/usr/bin/env python3
"""Deterministic test suite for the prog-discovery pipeline hardening
(kanban t_64963b0f, spec items 1+2). Pure fixtures — no network, no Spotify,
no writes outside tmp dirs.

Runs with plain unittest:  python3 test_pipeline.py [-v]
"""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
PIPELINE = SCRIPTS / "pipeline.py"
REAL_QA = Path.home() / ".hermes" / "prog-discovery" / "site" / "qa.py"
if not REAL_QA.exists():  # non-sandboxed checkouts
    REAL_QA = Path("/home/ghively/.hermes/prog-discovery/site/qa.py")

DATE = "2099-01-04"
PID = "5xK9amplePlaylistId"
PURL = f"https://open.spotify.com/playlist/{PID}"
URIS = [f"spotify:track:FIXTURE{i:03d}abcdefgh" for i in range(1, 5)]
ARTISTS = ["Alpha Band", "Beta Unit", "Gamma Collective", "Delta Pair"]
TAGS = ["prog-metal", "jazz-fusion", "post-rock", "zeuhl"]
LANES = ["core-prog", "jazz-fusion", "fringe", "scene"]
SOURCES = {"TOTW": {"name": "Tracks Of The Week", "url": "https://example.com/totw", "outlet": "TOTW"},
           "Progspace": {"name": "The Progspace", "url": "https://example.com/ps", "outlet": "Progspace"}}


def load_pipeline():
    spec = importlib.util.spec_from_file_location("pd_pipeline", PIPELINE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def edition_html(uris, playlist_url):
    sleeves = "".join(
        f'<div class="sleeve" data-tid="{u.rsplit(":", 1)[-1]}"></div>' for u in uris)
    modals = "".join(
        f'<div class="modal-back" id="modal-{u.rsplit(":", 1)[-1]}"></div>' for u in uris)
    return (f"<!doctype html><html><head><style></style></head><body>"
            f"{sleeves}{modals}"
            f'<a href="{playlist_url}">playlist</a></body></html>')


def front_html():
    return ('<!doctype html><html><body><header></header>'
            '<div class="stats-row"></div><nav></nav>'
            '<section class="hero"></section></body></html>')


def write_site_fixtures(home, *, uris=URIS, artists=ARTISTS, tags=TAGS, lanes=LANES,
                        tracks_extra=None, state_entry_mutate=None,
                        edition_mutate=None, html_uris=None, drop_attribution=False):
    """Materialize a complete fake PD_HOME tree (state + site data/out)."""
    d = home / "site" / "data" / DATE
    d.mkdir(parents=True)
    tracks = []
    for i, u in enumerate(uris):
        tracks.append({"name": f"Fixture Track {i + 1}", "uri": u, "duration_ms": 1000,
                       "artists": [artists[i]], "album": f"Album {i + 1}",
                       "release_date": "2099-01-01",
                       "url": f"https://open.spotify.com/track/{u.rsplit(':', 1)[-1]}"})
    if tracks_extra:
        tracks.extend(tracks_extra)
    (d / "tracks.json").write_text(json.dumps(
        {"total": len(uris), "tracks": tracks}, indent=1))
    blurbs = {u: {"src": "TOTW", "text": "fixture blurb", "quote": None} for u in uris}
    edition = {
        "date": DATE, "week": 42, "playlist_id": PID, "playlist_url": PURL,
        "playlist_title": "Prog & Jazz Discovery — fixture scene",
        "scene": "Fixture Scene", "scene_mode": "living", "scene_reason": "",
        "editor_note": "Fixture note.",
        "blurbs": blurbs,
        "tags": {u: tags[i] for i, u in enumerate(uris)},
        "lanes": {u: lanes[i] for i, u in enumerate(uris)},
        "sources": SOURCES,
        "theme": {"paras": ["fixture theme"]},
    }
    if edition_mutate:
        edition_mutate(edition)
    (d / "edition.json").write_text(json.dumps(edition, indent=1))

    out = home / "site" / "out"
    (out / DATE).mkdir(parents=True)
    (out / DATE / "index.html").write_text(
        edition_html(html_uris if html_uris is not None else uris, PURL))
    (out / "index.html").write_text(front_html())
    (out / "explore").mkdir()
    (out / "explore" / "index.html").write_text("<html></html>")
    shutil.copy(REAL_QA, home / "site" / "qa.py")

    entry = {"week": 42, "date": DATE, "url": PURL, "count": len(uris),
             "lanes": {l: lanes.count(l) for l in set(lanes)},
             "scene": "Fixture Scene", "scene_mode": "living", "scene_reason": ""}
    if state_entry_mutate:
        state_entry_mutate(entry)
    (home / "state.json").write_text(json.dumps(
        {"week_counter": 41, "playlists": [entry],
         "played_tracks": [], "played_artists": []}, indent=1))

    if not drop_attribution:
        attr_tracks = [{"artist": artists[i], "track": f"Fixture Track {i + 1}",
                        "uri": uris[i], "lane": lanes[i], "source": "TOTW", "tag": tags[i]}
                       for i in range(len(uris))]
        (home / "attribution.jsonl").write_text(
            json.dumps({"week": 42, "date": DATE, "playlist": PID,
                        "tracks": attr_tracks}) + "\n")


def run_pipeline(home, *args):
    env = {"PATH": "/usr/bin:/bin", "PD_HOME": str(home),
           "HERMES_AUTH_JSON": str(home / "auth.json"), "HOME": str(home)}
    return subprocess.run([sys.executable, str(PIPELINE), *args], env=env,
                          capture_output=True, text=True)


class CheckDraftTests(unittest.TestCase):
    """Unit tests for the deterministic draft gate (duplicates + provenance)."""

    @classmethod
    def setUpClass(cls):
        cls.mod = load_pipeline()

    def track(self, artist, uri, lane="core-prog", source="TOTW", tag="prog-metal"):
        return {"artist": artist, "track": "T", "uri": uri,
                "lane": lane, "source": source, "tag": tag}

    def test_duplicate_track_rejected(self):
        errors, _ = self.mod.check_draft([
            self.track("A", "spotify:track:1"), self.track("B", "spotify:track:1")])
        self.assertTrue(any("duplicate track" in e for e in errors), errors)

    def test_duplicate_artist_rejected(self):
        errors, _ = self.mod.check_draft([
            self.track("Same Artist", "spotify:track:1"),
            self.track("Same Artist", "spotify:track:2")])
        self.assertTrue(any("duplicate artist" in e for e in errors), errors)

    def test_missing_provenance_rejected(self):
        t = self.track("A", "spotify:track:1", tag="", lane="", source="")
        errors, _ = self.mod.check_draft([t])
        self.assertTrue(any("missing provenance" in e and "lane,source,tag" in e for e in errors),
                        errors)

    def test_valid_draft_clean(self):
        errors, _ = self.mod.check_draft([
            self.track("A", "spotify:track:1"), self.track("B", "spotify:track:2")])
        self.assertEqual(errors, [])


class SpotifyAuthTests(unittest.TestCase):
    """Regression tests for token expiry and mid-run 401 recovery."""

    @classmethod
    def setUpClass(cls):
        cls.mod = load_pipeline()

    def auth_file(self, tmp, *, expires_at="2000-01-01T00:00:00+00:00"):
        auth = {
            "providers": {"spotify": {
                "access_token": "old-token", "refresh_token": "refresh-token",
                "client_id": "client-id", "expires_at": expires_at,
            }}
        }
        path = tmp / "auth.json"
        path.write_text(json.dumps(auth))
        return path

    def response(self, payload, status=200):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps(payload).encode()
            def __getattr__(self, name):
                if name == "status": return status
                raise AttributeError(name)
        return Response()

    def test_refresh_persists_expiry_after_token_lifetime(self):
        tmp = Path(tempfile.mkdtemp(prefix="pd_auth_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        auth_path = self.auth_file(tmp)
        client = self.mod.SpotifyClient(auth_path)
        with mock.patch.object(self.mod.urllib.request, "urlopen",
                               return_value=self.response({"access_token": "new-token",
                                                           "expires_in": 3600})):
            client.refresh()
        saved = json.loads(auth_path.read_text())["providers"]["spotify"]
        self.assertEqual(saved["access_token"], "new-token")
        self.assertEqual(saved["expires_in"], 3600)
        self.assertGreater(saved["expires_at"], saved["obtained_at"])

    def test_request_refreshes_and_retries_once_on_401(self):
        tmp = Path(tempfile.mkdtemp(prefix="pd_auth401_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        auth_path = self.auth_file(tmp, expires_at="2099-01-01T00:00:00+00:00")
        client = self.mod.SpotifyClient(auth_path)
        error = self.mod.urllib.error.HTTPError(
            "https://api.spotify.com/v1/search", 401, "expired", {}, None)
        with mock.patch.object(self.mod.urllib.request, "urlopen",
                               side_effect=[error, self.response({"ok": True})]) as opened, \
             mock.patch.object(client, "refresh", return_value=None) as refresh:
            client.token = "refreshed-token"
            status, body = client.get("https://api.spotify.com/v1/search")
        self.assertEqual((status, body), (200, {"ok": True}))
        self.assertEqual(opened.call_count, 2)
        refresh.assert_called_once()


class HandoffTests(unittest.TestCase):
    """End-to-end fixture runs of `pipeline.py handoff` in a tmp PD_HOME."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="pd_handoff_"))
        self.addCleanup(shutil.rmtree, self.home, True)

    def test_valid_fixture_produces_handoff(self):
        write_site_fixtures(self.home)
        r = run_pipeline(self.home, "handoff", "--date", DATE)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        hpath = self.home / "site" / "data" / DATE / "handoff.json"
        self.assertTrue(hpath.exists())
        h = json.loads(hpath.read_text())
        for f in ("playlist_id", "playlist_url", "track_count", "scene", "scene_mode",
                  "lane_counts", "source_counts", "tag_counts", "site_url", "qa"):
            self.assertIn(f, h, f)
        self.assertEqual(h["playlist_id"], PID)
        self.assertEqual(h["playlist_url"], PURL)
        self.assertEqual(h["track_count"], len(URIS))
        self.assertEqual(h["scene"], "Fixture Scene")
        self.assertEqual(h["scene_mode"], "living")
        self.assertEqual(h["site_url"], f"https://music.hively.dev/{DATE}/")
        self.assertEqual(h["lane_counts"], {"core-prog": 1, "jazz-fusion": 1, "fringe": 1, "scene": 1})
        self.assertEqual(h["source_counts"], {"TOTW": 4})
        self.assertEqual(h["qa"]["exit"], 0)
        self.assertTrue(h["qa"]["ran_at"])

    def test_missing_tracks_json_exits_nonzero(self):
        write_site_fixtures(self.home)
        (self.home / "site" / "data" / DATE / "tracks.json").unlink()
        r = run_pipeline(self.home, "handoff", "--date", DATE)
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertIn("missing", r.stdout)

    def test_missing_scene_exits_nonzero(self):
        def mutate_state(e):
            e["scene"] = ""
        def mutate_ed(ed):
            ed["scene"] = ""
        write_site_fixtures(self.home, state_entry_mutate=mutate_state,
                            edition_mutate=mutate_ed)
        r = run_pipeline(self.home, "handoff", "--date", DATE)
        self.assertEqual(r.returncode, 6, r.stdout + r.stderr)
        self.assertIn("scene missing", r.stdout)

    def test_malformed_playlist_url_exits_nonzero(self):
        def mutate_state(e):
            e["url"] = "not-a-url"
        write_site_fixtures(self.home, state_entry_mutate=mutate_state)
        r = run_pipeline(self.home, "handoff", "--date", DATE)
        self.assertEqual(r.returncode, 6, r.stdout + r.stderr)
        self.assertIn("playlist URL malformed", r.stdout)

    def test_count_mismatch_exits_nonzero(self):
        def mutate_state(e):
            e["count"] = 99
        write_site_fixtures(self.home, state_entry_mutate=mutate_state)
        r = run_pipeline(self.home, "handoff", "--date", DATE)
        self.assertEqual(r.returncode, 6, r.stdout + r.stderr)
        self.assertIn("track count mismatch", r.stdout)

    def test_no_state_entry_exits_nonzero(self):
        write_site_fixtures(self.home)
        r = run_pipeline(self.home, "handoff", "--date", "2001-01-01")
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)

    def test_missing_attribution_exits_nonzero(self):
        write_site_fixtures(self.home, drop_attribution=True)
        r = run_pipeline(self.home, "handoff", "--date", DATE)
        self.assertEqual(r.returncode, 6, r.stdout + r.stderr)
        self.assertIn("attribution.jsonl", r.stdout)

    def test_site_not_built_exits_nonzero(self):
        write_site_fixtures(self.home)
        (self.home / "site" / "out" / DATE / "index.html").unlink()
        r = run_pipeline(self.home, "handoff", "--date", DATE)
        self.assertEqual(r.returncode, 6, r.stdout + r.stderr)
        self.assertIn("site not built", r.stdout)


class QaTests(unittest.TestCase):
    """Fixture runs of the hardened site QA gate (run_qa on a tmp site tree)."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="pd_qa_"))
        self.addCleanup(shutil.rmtree, self.home, True)
        spec = importlib.util.spec_from_file_location("pd_qa", REAL_QA)
        self.qa = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.qa)

    def test_valid_fixture_passes(self):
        write_site_fixtures(self.home)
        failures = self.qa.run_qa(self.home / "site")
        self.assertEqual(failures, [])

    def test_site_data_mismatch_fails(self):
        # built page shows a track that tracks.json does not have
        write_site_fixtures(self.home, html_uris=URIS + ["spotify:track:GHOSTtrack00"])
        failures = self.qa.run_qa(self.home / "site")
        self.assertTrue(any("page/tracks.json mismatch" in f for f in failures), failures)

    def test_duplicate_track_in_data_fails(self):
        extra = {"name": "Dup", "uri": URIS[0], "duration_ms": 1, "artists": ["Other"],
                 "album": "X", "release_date": "2099", "url": "u"}
        write_site_fixtures(self.home, tracks_extra=[extra], html_uris=URIS)
        failures = self.qa.run_qa(self.home / "site")
        self.assertTrue(any("duplicate track" in f for f in failures), failures)

    def test_duplicate_artist_in_data_fails(self):
        extra = {"name": "Other", "uri": "spotify:track:DUPEartst00000000x", "duration_ms": 1,
                 "artists": [ARTISTS[0]], "album": "X", "release_date": "2099", "url": "u"}
        write_site_fixtures(self.home, tracks_extra=[extra],
                            html_uris=URIS + ["spotify:track:DUPEartst00000000x"])
        failures = self.qa.run_qa(self.home / "site")
        self.assertTrue(any("duplicate artist" in f for f in failures), failures)

    def test_missing_source_attribution_fails(self):
        def mutate_ed(ed):
            ed["blurbs"][URIS[1]]["src"] = "NONEXISTENT_SOURCE"
        write_site_fixtures(self.home, edition_mutate=mutate_ed)
        failures = self.qa.run_qa(self.home / "site")
        self.assertTrue(any("missing source attribution" in f for f in failures), failures)

    def test_cross_edition_repeat_fails(self):
        write_site_fixtures(self.home)
        # a second edition reusing one track uri
        d2 = self.home / "site" / "data" / "2099-01-11"
        d2.mkdir()
        tracks = [{"name": "Repeat", "uri": URIS[0], "duration_ms": 1, "artists": ["Zeta"],
                   "album": "X", "release_date": "2099", "url": "u"}]
        (d2 / "tracks.json").write_text(json.dumps({"total": 1, "tracks": tracks}))
        (d2 / "edition.json").write_text(json.dumps({
            "blurbs": {URIS[0]: {"src": "TOTW"}}, "tags": {URIS[0]: "prog-metal"},
            "lanes": {URIS[0]: "core-prog"}, "sources": SOURCES,
            "theme": {"paras": ["x"]}, "scene": "S", "scene_mode": "living",
            "playlist_url": PURL, "playlist_id": PID, "date": "2099-01-11", "week": 43}))
        failures = self.qa.run_qa(self.home / "site")
        self.assertTrue(any("cross-edition track repeats" in f for f in failures), failures)

    def test_playlist_url_missing_from_page_fails(self):
        write_site_fixtures(self.home, html_uris=URIS)
        p = self.home / "site" / "out" / DATE / "index.html"
        p.write_text(edition_html(URIS, "https://wrong.example/playlist"))
        failures = self.qa.run_qa(self.home / "site")
        self.assertTrue(any("playlist URL missing from built page" in f for f in failures), failures)


class PreferenceTests(unittest.TestCase):
    """B2 (t_9116f466): bounded, visible, non-listening-history preference path."""

    @classmethod
    def setUpClass(cls):
        cls.mod = load_pipeline()

    def cand(self, artist, track):
        return {"artist": artist, "track": track, "lane": "core-prog",
                "source": "TOTW", "tag": "prog-metal"}

    def test_validate_rejects_bad_weight(self):
        for w in (0, 0.05, 2.5, -1, "1.5", True, None):
            errs = self.mod.validate_preferences({"boost": [{"name": "X", "weight": w}]})
            self.assertTrue(any("weight" in e for e in errs), (w, errs))

    def test_validate_rejects_out_of_cap(self):
        errs = self.mod.validate_preferences({"include": [f"Artist {i}" for i in range(51)]})
        self.assertTrue(any("cap 50" in e for e in errs), errs)
        errs = self.mod.validate_preferences({"boost": [{"name": f"A{i}", "weight": 1.0} for i in range(21)]})
        self.assertTrue(any("cap 20" in e for e in errs), errs)

    def test_validate_rejects_cross_list_and_unknown_keys(self):
        errs = self.mod.validate_preferences({"include": ["Magma"], "exclude": ["Magma"]})
        self.assertTrue(any("appears in both" in e for e in errs), errs)
        errs = self.mod.validate_preferences({"include": ["Magma"],
                                              "boost": [{"name": "Magma", "weight": 1.0}]})
        self.assertTrue(any("appears in both" in e for e in errs), errs)
        errs = self.mod.validate_preferences({"frobnicate": []})
        self.assertTrue(any("unknown top-level keys" in e for e in errs), errs)

    def test_validate_accepts_well_formed_file(self):
        errs = self.mod.validate_preferences({
            "include": [{"name": "Magma", "note": "loved the Zeuhl lane", "added_by": "gene",
                         "added_at": "2026-09-05T00:00:00+00:00"}],
            "exclude": ["Yes"],
            "boost": [{"name": "Koenjihyakkei", "weight": 1.8}],
        })
        self.assertEqual(errs, [])

    def test_validate_refuses_playback_derived_entries(self):
        for origin in ("recently-played", "listening-history", "derived from skips",
                       "spotify playback stats", "related-artist feed", "auto-infer"):
            errs = self.mod.validate_preferences(
                {"include": [{"name": "X", "origin": origin}]})
            self.assertTrue(any("playback-derived" in e for e in errs), (origin, errs))
            errs = self.mod.validate_preferences(
                {"boost": [{"name": "X", "weight": 1.0, "derived_from": origin}]})
            self.assertTrue(any("playback-derived" in e for e in errs), (origin, errs))

    def test_fixture_reorders_candidate_ranking(self):
        """include/exclude/boost demonstrably reorder a fixed candidate list."""
        cands = [self.cand(a, t) for a, t in [
            ("Alpha Band", "Song A"), ("Beta Unit", "Song B"),
            ("Gamma Collective", "Song C"), ("Delta Pair", "Song D")]]
        prefs = {
            "include": ["Delta Pair"],                    # moves last -> first
            "exclude": ["Beta Unit"],                     # dropped entirely
            "boost": [{"name": "Song C", "weight": 1.5}], # Gamma above Alpha
        }
        ranked, summary = self.mod.apply_preferences(cands, prefs)
        self.assertEqual([c["artist"] for c in ranked],
                         ["Delta Pair", "Gamma Collective", "Alpha Band"])
        self.assertEqual(summary["applied"]["include_matched"], ["Delta Pair"])
        self.assertEqual(summary["applied"]["boost_matched"],
                         [{"name": "Song C", "weight": 1.5}])
        self.assertEqual(summary["applied"]["excluded_candidates"], ["Beta Unit — Song B"])

    def test_ranking_is_deterministic_and_stable(self):
        cands = [self.cand(f"Artist {i}", f"Track {i}") for i in range(6)]
        ranked1, _ = self.mod.apply_preferences(cands, {"include": [], "exclude": [], "boost": []})
        ranked2, _ = self.mod.apply_preferences(cands, {})
        self.assertEqual([c["artist"] for c in ranked1], [c["artist"] for c in ranked2])
        # no preferences -> harvest order preserved
        self.assertEqual([c["artist"] for c in ranked1], [c["artist"] for c in cands])

    def test_handoff_carries_effective_preferences(self):
        home = Path(tempfile.mkdtemp(prefix="pd_pref_"))
        self.addCleanup(shutil.rmtree, home, True)
        write_site_fixtures(home)
        (home / "preferences.json").write_text(json.dumps({
            "include": [{"name": "Alpha Band", "note": "requested", "added_by": "gene",
                         "added_at": "2026-09-05T00:00:00+00:00"}],
            "exclude": [],
            "boost": [{"name": "Gamma Collective", "weight": 1.5}],
        }))
        r = run_pipeline(home, "handoff", "--date", DATE)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        h = json.loads((home / "site" / "data" / DATE / "handoff.json").read_text())
        ep = h["effective_preferences"]
        self.assertEqual(ep["counts"], {"include": 1, "exclude": 0, "boost": 1})
        self.assertEqual(ep["include"][0]["name"], "Alpha Band")
        self.assertEqual(ep["include"][0]["note"], "requested")
        self.assertEqual(ep["boost"][0]["weight"], 1.5)
        self.assertIn("never Spotify listening history", ep["source"])
        # visibility: same summary recorded in the edition data dir
        edir = json.loads((home / "site" / "data" / DATE / "preferences.json").read_text())
        self.assertEqual(edir, ep)

    def test_handoff_fails_on_invalid_preferences(self):
        home = Path(tempfile.mkdtemp(prefix="pd_prefbad_"))
        self.addCleanup(shutil.rmtree, home, True)
        write_site_fixtures(home)
        (home / "preferences.json").write_text(json.dumps(
            {"boost": [{"name": "X", "weight": 9.0}]}))
        r = run_pipeline(home, "handoff", "--date", DATE)
        self.assertEqual(r.returncode, 6, r.stdout + r.stderr)
        self.assertIn("weight", r.stdout)
        hpath = home / "site" / "data" / DATE / "handoff.json"
        self.assertFalse(hpath.exists())  # never write a handoff from bad prefs

    def test_handoff_cannot_bypass_required_qa(self):
        home = Path(tempfile.mkdtemp(prefix="pd_qabypass_"))
        self.addCleanup(shutil.rmtree, home, True)
        write_site_fixtures(home)
        r = run_pipeline(home, "handoff", "--date", DATE, "--skip-qa")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((home / "site" / "data" / DATE / "handoff.json").exists())

    def test_pipeline_has_no_listening_history_path(self):
        source = PIPELINE.read_text()
        for forbidden in ("/me/player/recently-played", "played_tracks", "played_artists",
                          "seed_artists", "saved_ours", "played_ours"):
            self.assertNotIn(forbidden, source)

    def test_pref_subcommand_add_remove_validate(self):
        home = Path(tempfile.mkdtemp(prefix="pd_prefcmd_"))
        self.addCleanup(shutil.rmtree, home, True)
        write_site_fixtures(home)
        r = run_pipeline(home, "pref", "add", "include", "Magma",
                         "--note", "more zeuhl please", "--added-by", "gene")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run_pipeline(home, "pref", "add", "boost", "Koenjihyakkei", "--weight", "1.5")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        on_disk = json.loads((home / "preferences.json").read_text())
        self.assertEqual(on_disk["include"][0]["name"], "Magma")
        self.assertEqual(on_disk["include"][0]["note"], "more zeuhl please")
        self.assertEqual(on_disk["boost"][0]["weight"], 1.5)
        self.assertTrue(on_disk["include"][0]["added_at"])  # provenance stamped
        r = run_pipeline(home, "pref", "validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run_pipeline(home, "pref", "remove", "include", "Magma")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        on_disk = json.loads((home / "preferences.json").read_text())
        self.assertEqual(on_disk["include"], [])

    def test_pref_add_refuses_bad_weight_and_leaves_file_untouched(self):
        home = Path(tempfile.mkdtemp(prefix="pd_prefadd_"))
        self.addCleanup(shutil.rmtree, home, True)
        write_site_fixtures(home)
        r = run_pipeline(home, "pref", "add", "boost", "X", "--weight", "5.0")
        self.assertEqual(r.returncode, 8, r.stdout + r.stderr)
        self.assertIn("outside", r.stdout)
        self.assertFalse((home / "preferences.json").exists())  # file NOT modified

    def test_pref_validate_exit8_on_playback_derived_file(self):
        home = Path(tempfile.mkdtemp(prefix="pd_prefplay_"))
        self.addCleanup(shutil.rmtree, home, True)
        write_site_fixtures(home)
        (home / "preferences.json").write_text(json.dumps(
            {"include": [{"name": "Hypnotic Brass", "origin": "from recently-played feed"}]}))
        r = run_pipeline(home, "pref", "validate")
        self.assertEqual(r.returncode, 8, r.stdout + r.stderr)
        self.assertIn("playback-derived", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
