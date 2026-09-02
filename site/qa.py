#!/usr/bin/env python3
"""QA gate for the Now Spinning site build. Exit 0 = safe to deploy.
Checks the bugs found during the 2026-09-02 build sessions."""
import re, sys, json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"
ok = True
def fail(msg):
    global ok; ok = False; print(f"FAIL: {msg}")
def good(msg): print(f"ok:   {msg}")

editions = [d for d in OUT.iterdir() if d.is_dir() and d.name != "explore" and d.name != "genres"]
if not editions: fail("no edition pages built")
for d in editions:
    raw = (d / "index.html").read_text()
    sleeves = len(re.findall(r'class="sleeve[" ]', raw))
    modals = raw.count('class="modal-back"')
    ids = set(re.findall(r'id="modal-([0-9A-Za-z]+)"', raw))
    if sleeves == modals == len(ids) and sleeves > 0:
        good(f"{d.name}: {sleeves} sleeves == modals == unique ids")
    else:
        fail(f"{d.name}: sleeves={sleeves} modals={modals} uniq={len(ids)} mismatch")
    if "<style>" in raw and "</style>" in raw: good(f"{d.name}: style tags present")
    else: fail(f"{d.name}: missing <style> wrapper (CSS-as-text bug)")
    ed = json.loads((Path(__file__).resolve().parent / "data" / d.name / "edition.json").read_text())
    tk = json.loads((Path(__file__).resolve().parent / "data" / d.name / "tracks.json").read_text())
    inlist = {t["uri"] for t in tk["tracks"]}
    if set(ed.get("blurbs", {})) == inlist: good(f"{d.name}: blurbs cover all tracks")
    else: fail(f"{d.name}: blurbs missing {sorted(inlist - set(ed.get('blurbs',{})))[:3]}")
    if set(ed.get("tags", {})) == inlist: good(f"{d.name}: genre tags cover all tracks")
    else: fail(f"{d.name}: tags missing {sorted(inlist - set(ed.get('tags',{})))[:3]}")
    if ed.get("theme", {}).get("paras"): good(f"{d.name}: theme essay present")
    else: fail(f"{d.name}: theme essay missing")

front = (OUT / "index.html").read_text()
i_mast_end = front.find("</header>")
i_stats = front.find('class="stats-row"')
i_nav = front.find("<nav")
i_hero = front.find('class="hero"')
if i_mast_end < i_stats < i_nav < i_hero:
    good("front: stats bar under tagline (masthead < stats < nav < hero)")
else:
    fail(f"front: stats bar misplaced (mast={i_mast_end} stats={i_stats} nav={i_nav} hero={i_hero})")
# duplicate outlet display names in the source line
src_line = re.search(r'Sourced from the week.{0,2000}?</div>', front, re.S)
if src_line:
    outlets = re.findall(r'rel="noopener">([^<]+)</a>', src_line.group(0))
    if len(outlets) == len(set(outlets)): good(f"front: source line deduped ({len(outlets)} outlets)")
    else: fail(f"front: duplicate outlets in source line: {[o for o in outlets if outlets.count(o)>1]}")
if (OUT / "explore" / "index.html").exists(): good("explore page built")
else: fail("explore page missing")
sys.exit(0 if ok else 1)
