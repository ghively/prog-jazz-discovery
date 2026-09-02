#!/usr/bin/env python3
"""Build the NOW SPINNING music discovery log.

Reads:   site/data/<date>/edition.json  (editorial: sources, blurbs, tags)
         site/data/<date>/tracks.json   (Spotify API fetch, incl. artist URLs)
         site/data/artists.json         (verified bandcamp/website links)
Writes:  site/out/index.html            (blog front — hero w/ themes, archive)
         site/out/explore/index.html    (EXPLORE: genre + artist database)
         site/out/<date>/index.html     (one page per edition — stable design)

Aesthetic: a collector's listening log — sleeves on wooden shelves, genre
stickers, grease-pencil notes. Blog voice, not shop cosplay.
Additive by construction: edition pages never regenerate; the front page
and Explore assemble from whatever data exists.
"""
import json, html, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
OUT = BASE / "out"

SITE_NAME = "Now Spinning"
TAGLINE = "a weekly music discovery log — prog, fusion & the fringes"

# ---- taxonomy: fine tag -> shelf. Shelves are stable; tags accumulate. ----
SHELVES = [
    ("prog-metal",  "Prog Metal",          ["prog-metal", "djent", "symphonic-metal", "avant-metal",
                                            "dissonant-death", "tech-death", "prog-death", "modern-metal"]),
    ("prog-rock",   "Prog Rock",           ["modern prog", "neo-prog", "art-rock", "psych-prog", "symphonic",
                                            "symphonic-prog", "rock-opera", "crossover-prog", "chamber-prog",
                                            "avant-prog", "space-rock", "krautrock"]),
    ("post-psych",  "Post-Rock & Psych",   ["post-rock", "post-metal", "doom-psych", "psych", "stoner-rock",
                                            "atmospheric-sludge", "atmo-sludge"]),
    ("jazz-fusion", "Jazz Fusion",         ["jazz-fusion", "jazztronica", "avant-jazz", "nu-jazz", "fusion",
                                            "avant-fusion", "prog-jazz"]),
    ("jazz",        "Jazz",                ["modern jazz", "free-jazz", "jazz-punk", "ambient-jazz",
                                            "chamber-jazz", "dark-jazz", "noir-jazz", "spiritual-jazz"]),
    ("zeuhl-cant",  "Zeuhl & Canterbury",  ["zeuhl", "canterbury", "rock-in-opposition", "rio"]),
    ("fringe",      "The Fringes",         []),  # fallback: math-rock, hyperpop-prog, vgm, experiments
]
SHELF_OF = {}
for key, _label, tags in SHELVES:
    for t in tags:
        SHELF_OF[t] = key
SHELF_LABEL = {k: l for k, l, _ in SHELVES}

def esc(s): return html.escape(str(s)) if s is not None else ""

def dur(ms):
    if not ms: return ""
    s = ms // 1000
    return f"{s//60}:{s%60:02d}"

def year(rd): return (rd or "")[:4]

def shelf_for(tag):
    return SHELF_OF.get((tag or "").strip().lower(), "fringe")

CSS = """
:root{
  --wall:#191009; --wall2:#221609;
  --wood:#4a3320; --wood-hi:#6b4c2e; --wood-lo:#2a1c0e;
  --sleeve:#e9e2d0; --paper:#f3ead2; --aged:#e6d9b8;
  --ink:#241c12; --ink-soft:#5a4d3a;
  --neon:#ff5c8a; --neon2:#59e6b3;
  --sticker:#f7d968; --sticker-red:#c8442e; --sticker-blue:#1d6f8a;
  --sticker-purple:#5b4a86; --sticker-green:#3f7d4d; --sticker-tan:#b39b52;
  --text:#e8dcc8; --text-dim:#a6988a;
}
*{box-sizing:border-box; margin:0}
html{scroll-behavior:smooth}
body{
  color:var(--text);
  font-family:'Libre Franklin',system-ui,-apple-system,sans-serif;
  background:
    repeating-linear-gradient(90deg, rgba(255,255,255,.012) 0 2px, transparent 2px 7px),
    radial-gradient(ellipse 120% 60% at 50% -10%, #2e1d0e, transparent 70%),
    linear-gradient(180deg, var(--wall) 0%, var(--wall2) 100%);
  background-attachment:fixed;
  min-height:100vh;
}
a{color:var(--neon2); text-decoration:none}
.wrap{max-width:72rem; margin:0 auto; padding:0 1.2rem 6rem}
.mono{font-family:'Courier Prime','Courier New',monospace}
.hand{font-family:'Caveat',cursive}

/* ============ MASTHEAD ============ */
.masthead{text-align:center; padding:2.6rem 0 1.6rem; position:relative}
.masthead .tube{
  font-family:'Monoton',cursive; font-size:clamp(1.5rem,4.8vw,3.6rem);
  color:#ffd9e6; letter-spacing:.05em; line-height:1.15;
  text-shadow:0 0 4px #fff6f9, 0 0 11px #ff9dbd, 0 0 24px #ff5c8a, 0 0 60px #ff2467;
  animation:buzz 7s infinite;
}
@keyframes buzz{0%,91%,94%,100%{opacity:1} 92%,93%{opacity:.62}}
.masthead .under{
  display:inline-flex; gap:1.2rem; align-items:center; margin-top:.8rem; flex-wrap:wrap; justify-content:center;
  font-family:'Courier Prime',monospace; font-size:.72rem; letter-spacing:.32em;
  color:var(--text-dim); text-transform:uppercase;
}
.masthead .under .dot{color:var(--neon)}
.monday-note{position:absolute; right:0; top:2.2rem}
@media(max-width:1000px){.monday-note{display:none}}
.blogstrip{
  display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:.6rem;
  border-top:2px solid var(--wood-hi); border-bottom:2px solid var(--wood-lo);
  padding:.55rem .2rem; margin-bottom:2.2rem;
  font-family:'Courier Prime',monospace; font-size:.74rem; letter-spacing:.22em;
  text-transform:uppercase; color:var(--text-dim);
}
.blogstrip a{color:var(--text)}
.blogstrip a:hover{color:var(--neon2)}
.blogstrip .nav-active{color:var(--neon2)}
.blogstrip .navlinks{display:flex; gap:2.6rem; align-items:center}

/* ============ SPOTLIGHT ============ */
.spotlight{
  position:relative; margin:2.4rem 0 3rem; padding:1.6rem 1.4rem 1.2rem;
  background:linear-gradient(180deg,#241408,#1a0e05);
  border:1px solid #6b4c2e; border-top:none;
  box-shadow:inset 0 2px 0 rgba(255,220,150,.08), 0 14px 34px rgba(0,0,0,.5);
}
.spotlight::before{
  content:""; position:absolute; top:-2px; left:-6px; right:-6px; height:10px;
  background:repeating-linear-gradient(90deg,#ff5c8a 0 14px,#241c12 14px 18px,#59e6b3 18px 32px,#241c12 32px 36px);
  border-radius:6px; box-shadow:0 2px 8px rgba(0,0,0,.6);
}
.spotlight h2{
  font-size:.78rem; letter-spacing:.34em; text-transform:uppercase; color:var(--neon2);
  text-shadow:0 0 10px rgba(89,230,179,.55); margin:.4rem 0 1rem;
  font-family:'Courier Prime',monospace;
}
.spotlight .name{
  font-family:'Alfa Slab One',serif; font-weight:400; color:#f2e7cf;
  font-size:clamp(1.5rem,4vw,2.6rem); line-height:1.05; margin-bottom:.9rem;
  text-shadow:2px 3px 0 rgba(0,0,0,.55);
}
.spotlight .note{color:var(--text-dim); font-size:.95rem; max-width:46rem}

/* ============ SHELVES ============ */
.shelf-section{margin:3.4rem 0}
.shelf-head{display:flex; align-items:flex-end; gap:1rem; margin-bottom:.4rem; flex-wrap:wrap}
.divider{
  background:linear-gradient(180deg,#e9e2d0,#d9cfb4);
  color:var(--ink); padding:1.05rem 1.3rem .55rem;
  font-family:'Alfa Slab One',serif; font-size:1.02rem; letter-spacing:.05em;
  border-radius:4px 4px 0 0; transform:rotate(-.6deg);
  box-shadow:0 -2px 0 rgba(0,0,0,.25), inset 0 3px 0 #fff8;
  position:relative; min-width:11rem;
}
.divider .count{
  display:block; font-family:'Courier Prime',monospace; font-size:.62rem;
  letter-spacing:.3em; color:var(--ink-soft); margin-top:.2rem;
}
.shelf-sub{color:var(--text-dim); font-size:.85rem; font-style:italic; padding-bottom:.5rem}
.crate{
  background:linear-gradient(180deg,#120b05,#0d0703);
  border:2px solid var(--wood); border-radius:3px;
  box-shadow:inset 0 14px 30px rgba(0,0,0,.75), inset 0 -6px 12px rgba(0,0,0,.6);
  padding:1.6rem 1.1rem 1.2rem; position:relative; overflow-x:auto;
}
.crate::before{
  content:""; position:absolute; left:0; right:0; bottom:0; height:1.15rem;
  background:linear-gradient(180deg,var(--wood-hi),var(--wood-lo));
  border-top:1px solid #8a6537;
}
.sleeves{
  display:grid; grid-template-columns:repeat(auto-fill,minmax(158px,1fr)); gap:1.15rem .9rem;
  padding-bottom:.4rem;
}

/* ============ SLEEVE ============ */
.sleeve{
  position:relative; background:var(--sleeve); border-radius:2px; cursor:pointer;
  box-shadow:0 2px 4px rgba(0,0,0,.55), 0 10px 18px rgba(0,0,0,.35);
  transition:transform .22s cubic-bezier(.2,.9,.3,1.4), box-shadow .22s;
  transform:rotate(var(--tilt,0deg));
  outline:none;
}
.sleeve:nth-child(3n+1){--tilt:-1.3deg}
.sleeve:nth-child(3n+2){--tilt:.9deg}
.sleeve:nth-child(5n+3){--tilt:-.5deg}
.sleeve:hover,.sleeve:focus-visible{
  transform:rotate(0) translateY(-10px) scale(1.05);
  box-shadow:0 6px 8px rgba(0,0,0,.5), 0 26px 40px rgba(0,0,0,.55);
  z-index:3;
}
.sleeve img{display:block; width:100%; aspect-ratio:1; object-fit:cover; background:#cfc5ad}
.sleeve.vintage img{filter:sepia(.42) saturate(.8) brightness(.92)}
.sleeve .spine{
  padding:.5rem .55rem .55rem; color:var(--ink); background:var(--sleeve);
  border-top:1px solid #cfc5ad;
}
.sleeve .artist{font-weight:700; font-size:.8rem; line-height:1.15; letter-spacing:-.01em}
.sleeve .title{font-size:.76rem; font-style:italic; color:var(--ink-soft); line-height:1.2}
.sleeve .tag{
  position:absolute; top:-9px; right:-7px; z-index:2; transform:rotate(6deg);
  font-family:'Courier Prime',monospace; font-size:.56rem; font-weight:700;
  letter-spacing:.14em; text-transform:uppercase; color:#241c12;
  background:var(--sticker); padding:.3rem .5rem;
  box-shadow:0 2px 5px rgba(0,0,0,.45);
  transition:transform .22s; max-width:85%; overflow-wrap:break-word;
}
.sleeve:hover .tag{transform:rotate(2deg) scale(1.08)}
.sleeve.vintage .tag{background:var(--sticker-tan); color:#f6ecd6}
.sleeve .hype{
  position:absolute; bottom:2.35rem; left:-6px; transform:rotate(-7deg);
  background:var(--sticker); color:var(--ink);
  font-family:'Courier Prime',monospace; font-weight:700; font-size:.66rem;
  padding:.14rem .42rem; box-shadow:0 2px 4px rgba(0,0,0,.4);
}
.sleeve.vintage .hype{background:var(--aged); color:#5a4d3a}
.sleeve .hand-note{
  position:absolute; left:50%; bottom:2.5rem; transform:translateX(-50%) rotate(-2deg);
  color:#3b2f1e; font-family:'Caveat',cursive; font-size:.95rem; white-space:nowrap;
  text-shadow:0 1px 0 #fff9; pointer-events:none;
}
.starburst{
  position:absolute; top:-16px; left:-14px; z-index:2; width:64px; height:64px;
  display:grid; place-items:center; transform:rotate(-12deg);
  color:#fff; font-family:'Courier Prime',monospace; font-size:.5rem; font-weight:700;
  letter-spacing:.06em; text-align:center; line-height:1.1;
  background:var(--sticker-red);
  clip-path:polygon(50% 0,61% 12%,76% 6%,79% 22%,95% 24%,88% 38%,100% 50%,88% 62%,95% 76%,79% 78%,76% 94%,61% 88%,50% 100%,39% 88%,24% 94%,21% 78%,5% 76%,12% 62%,0 50%,12% 38%,5% 24%,21% 22%,24% 6%,39% 12%);
  text-shadow:0 1px 2px rgba(0,0,0,.5);
}

/* ============ PULL-OUT MODAL ============ */
.modal-back{
  position:fixed; inset:0; background:rgba(8,4,1,.82); backdrop-filter:blur(3px);
  display:none; align-items:center; justify-content:center; z-index:50; padding:1.2rem;
}
.modal-back.open{display:flex}
.modal{
  display:grid; grid-template-columns:minmax(220px,320px) minmax(280px,500px);
  gap:0; max-width:56rem; width:100%; max-height:88vh; overflow:auto;
  background:linear-gradient(180deg,#241408,#160b04);
  border:1px solid #6b4c2e; border-radius:4px;
  box-shadow:0 40px 90px rgba(0,0,0,.7);
}
@media(max-width:760px){.modal{grid-template-columns:1fr}}
.vinyl-side{
  position:relative; padding:2rem 1.4rem; display:grid; place-items:center; overflow:hidden;
  background:
    radial-gradient(circle at 50% 40%, rgba(255,200,120,.05), transparent 60%),
    repeating-linear-gradient(45deg, rgba(0,0,0,.15) 0 2px, transparent 2px 4px);
}
.the-record{position:relative; width:min(100%,280px); aspect-ratio:1}
.sleeve-big{
  position:absolute; inset:0; z-index:2; border-radius:2px; overflow:hidden;
  box-shadow:0 12px 30px rgba(0,0,0,.6);
}
.sleeve-big img{width:100%; height:100%; object-fit:cover; display:block}
.sleeve-big .corner{
  position:absolute; inset:0; box-shadow:inset 0 0 34px rgba(60,35,8,.35);
  border:1px solid rgba(255,240,200,.14);
}
.disc{
  position:absolute; z-index:1; top:12%; left:0; width:76%; aspect-ratio:1; border-radius:50%;
  background:
    radial-gradient(circle at 50% 50%, #0c0c0e 0 15.5%, transparent 15.8%),
    repeating-radial-gradient(circle at 50% 50%, #111114 0 1.6px, #191a20 1.6px 3.4px);
  box-shadow:0 8px 22px rgba(0,0,0,.65);
  transform:translateX(-38%);   /* tucked behind the sleeve */
  transition:transform .5s cubic-bezier(.2,.9,.25,1);
}
.modal-back.open .disc{transform:translateX(18%)}  /* slid out, still inside the column */
.modal-back.open .disc.spin{animation:spin 7s linear infinite}
@keyframes spin{from{transform:translateX(18%) rotate(0)} to{transform:translateX(18%) rotate(360deg)}}
.disc::after{
  content:attr(data-label);
  position:absolute; inset:33%; border-radius:50%;
  background:radial-gradient(circle at 38% 32%, #f0a4a4, #c8442e 70%);
  display:grid; place-items:center; text-align:center;
  font-family:'Courier Prime',monospace; font-size:.5rem; font-weight:700; color:#2a0e08;
  letter-spacing:.06em; line-height:1.25; padding:.4rem;
  box-shadow:inset 0 0 0 1px rgba(0,0,0,.25);
}
.disc::before{
  content:""; position:absolute; z-index:2; left:50%; top:50%; width:9px; height:9px;
  transform:translate(-50%,-50%); border-radius:50%; background:#160b04;
  box-shadow:inset 0 1px 2px #000;
}
.notes-side{padding:2rem 1.8rem 1.6rem; border-left:1px solid #3a2a1a; min-width:0}
@media(max-width:760px){.notes-side{border-left:none; border-top:1px solid #3a2a1a}}
.notes-side .kick{
  font-family:'Courier Prime',monospace; font-size:.62rem; letter-spacing:.3em;
  text-transform:uppercase; color:var(--neon2); margin-bottom:.5rem;
}
.notes-side h3{font-family:'Alfa Slab One',serif; font-weight:400; color:#f2e7cf;
  font-size:1.45rem; line-height:1.15; margin-bottom:.15rem}
.notes-side h3 .t{display:block; font-family:'Caveat',cursive; font-size:1.5rem;
  color:var(--neon); transform:rotate(-1deg); margin-top:.1rem}
.facts{font-family:'Courier Prime',monospace; font-size:.68rem; color:var(--text-dim);
  letter-spacing:.05em; margin:.6rem 0 1rem; line-height:1.7}
.facts b{color:var(--text)}
.notes-side p.body{font-size:.98rem; line-height:1.65; color:#e8dcc8; margin-bottom:1rem}
blockquote.press{
  background:var(--paper); color:var(--ink); padding:.8rem 1rem .7rem; margin:0 0 1.1rem;
  transform:rotate(-.8deg); font-style:italic; font-size:.92rem; line-height:1.5;
  box-shadow:0 6px 14px rgba(0,0,0,.45);
  clip-path:polygon(0 3%,4% 0,98% 1%,100% 96%,95% 100%,2% 99%);
}
.clipping{
  background:var(--aged); color:var(--ink); display:inline-block; padding:.55rem .8rem .5rem;
  transform:rotate(.7deg); box-shadow:0 5px 12px rgba(0,0,0,.4); margin-bottom:1.1rem;
  clip-path:polygon(1% 0,99% 2%,100% 97%,2% 100%);
}
.clipping .from{font-family:'Courier Prime',monospace; font-size:.6rem; letter-spacing:.22em;
  text-transform:uppercase; color:#7a6a34; margin-bottom:.25rem}
.clipping a{color:#8a2d18; font-weight:700; font-size:.88rem; border-bottom:2px solid #c8442e}
.clipping .outlet{display:block; font-size:.72rem; color:#5a4d3a; margin-top:.15rem}
.playrow{display:flex; gap:.7rem; align-items:center; flex-wrap:wrap}
.spotify-btn{
  display:inline-flex; align-items:center; gap:.5rem; background:#1db954; color:#04120a;
  font-weight:700; font-size:.82rem; letter-spacing:.02em; padding:.55rem .95rem; border-radius:999px;
  box-shadow:0 4px 14px rgba(29,185,84,.35);
}
.spotify-btn:hover{background:#1ed760; transform:translateY(-1px)}
.ghost-btn{
  display:inline-flex; align-items:center; gap:.45rem; background:transparent; color:var(--neon2);
  font-family:'Courier Prime',monospace; font-weight:700; font-size:.78rem; letter-spacing:.06em;
  padding:.55rem .9rem; border-radius:999px; border:1px dashed var(--neon2);
}
.ghost-btn:hover{background:rgba(89,230,179,.12)}
.closer{
  position:absolute; top:.7rem; right:.9rem; background:none; border:none; color:var(--text-dim);
  font-size:1.6rem; cursor:pointer; line-height:1;
}
.closer:hover{color:#fff}

/* ============ EDITION HEAD ============ */
.edhead{display:grid; grid-template-columns:auto 1fr; gap:1.8rem; align-items:center;
  margin:1.4rem 0 0}
@media(max-width:700px){.edhead{grid-template-columns:1fr; text-align:center}}
.edhead .cover{
  width:210px; height:210px; border-radius:3px; transform:rotate(-2.4deg);
  box-shadow:0 3px 6px rgba(0,0,0,.5), 0 22px 44px rgba(0,0,0,.55);
  border:1px solid rgba(255,240,200,.18);
}
.edhead h2{font-family:'Alfa Slab One',serif; font-weight:400; color:#f2e7cf;
  font-size:clamp(1.4rem,3.4vw,2.3rem); line-height:1.08; margin:.3rem 0 .5rem}
.edhead .sub{color:var(--text-dim); font-size:.92rem; max-width:40rem}
.ednote{
  margin:1.8rem 0 0; display:block;
  font-family:'Caveat',cursive; font-size:1.5rem; line-height:1.3; color:#f5d67b;
  transform:rotate(-.4deg); max-width:44rem;
  text-shadow:0 2px 3px rgba(0,0,0,.6);
}
.ednote::before{content:"✎ "}

/* ============ DEEP DIVE (edition page) ============ */
.deepdive{
  margin:2.8rem 0 0; padding:1.7rem 1.9rem 1.5rem;
  background:linear-gradient(180deg,#1c1108,#130a04);
  border:1px solid #3a2a1a; border-left:4px solid var(--neon2);
  border-radius:0 6px 6px 0;
  box-shadow:0 14px 34px rgba(0,0,0,.45);
}
.deepdive h2{
  font-family:'Courier Prime',monospace; font-size:.72rem; letter-spacing:.3em;
  color:var(--neon2); text-transform:uppercase; margin-bottom:1rem;
}
.deepdive p.lead{font-size:1.04rem; line-height:1.7; color:#e0d4c0; margin-bottom:1.4rem}
.deepdive p.dpara{font-size:1rem; line-height:1.7; color:#d8ccb8; margin:0 0 1.1rem}
.deepdive p.dpara::first-letter{
  font-size:1.6em; color:var(--neon); font-weight:700; font-family:'Alfa Slab One',serif;
}
.deepdive p.outro{font-size:1rem; line-height:1.7; color:#d8ccb8; margin-top:1.4rem;
  border-top:1px dashed #3a2a1a; padding-top:1.2rem}
.trees{display:grid; grid-template-columns:1fr 1fr; gap:1.6rem}
@media(max-width:860px){.trees{grid-template-columns:1fr}}
.tree{
  background:rgba(13,7,3,.55); border:1px solid #2c2012; border-radius:4px;
  padding:1.2rem 1.2rem 1rem;
}
.tree-title{font-family:'Alfa Slab One',serif; font-weight:400; color:#f2e7cf;
  font-size:1.08rem; margin-bottom:.55rem}
.tree-root{
  font-size:.66rem; color:#f5d67b; letter-spacing:.04em; line-height:1.7;
  border-bottom:1px solid #3a2a1a; padding-bottom:.6rem; margin-bottom:.6rem;
}
.tree-items{list-style:none; padding:0; margin:0}
.tree-items li{position:relative; display:flex; gap:.7rem; align-items:flex-start;
  padding:.5rem 0 .5rem 1.3rem;
  border-bottom:1px dotted #2c2012; font-size:.86rem; color:#d8ccb8; line-height:1.5}
.tree-items li:last-child{border-bottom:none}
.tree-items li::before{
  content:"└"; position:absolute; left:0; top:.5rem; color:var(--sticker-tan);
  font-family:'Courier Prime',monospace;
}
.tree-items li img{width:44px; height:44px; border-radius:2px; object-fit:cover; flex:0 0 auto;
  transform:rotate(-1.5deg); box-shadow:0 2px 5px rgba(0,0,0,.5); margin-top:.05rem;
  border:1px solid rgba(255,240,200,.2)}
.node-blank{width:44px; height:44px; flex:0 0 auto; border-radius:2px;
  background:rgba(233,226,208,.05); border:1px dashed #3a2a1a}
.tree-items li b{color:#f2e7cf}
.here-mark{
  display:inline-block; margin-left:.45rem; padding:.06rem .4rem;
  font-family:'Courier Prime',monospace; font-size:.52rem; font-weight:700; letter-spacing:.14em;
  color:#04120a; background:#59e6b3; border-radius:2px; vertical-align:.08em;
}
.tree-cap{color:#f5d67b; font-size:1.15rem; margin-top:.7rem; transform:rotate(-.5deg)}

/* ============ FRONT PAGE ============ */
.hero{margin:2.5rem 0}
.hero-grid{display:grid; grid-template-columns:minmax(240px,340px) 1fr; gap:2rem; align-items:center}
@media(max-width:760px){.hero-grid{grid-template-columns:1fr}}
.hero img.cover{
  width:100%; aspect-ratio:1; object-fit:cover; border-radius:3px; transform:rotate(-2.2deg);
  box-shadow:0 3px 6px rgba(0,0,0,.5), 0 26px 50px rgba(0,0,0,.55);
  border:1px solid rgba(255,240,200,.18);
}
.hero .kick{font-family:'Courier Prime',monospace; font-size:.66rem; letter-spacing:.3em;
  color:var(--neon2); text-transform:uppercase; margin-bottom:.4rem}
.hero h2{font-family:'Alfa Slab One',serif; font-weight:400; color:#f2e7cf;
  font-size:clamp(1.6rem,4vw,2.6rem); line-height:1.08; margin:.2rem 0 .6rem}
.hero h2 a{color:inherit}
.hero .actions{display:flex; gap:.8rem; margin-top:.2rem; flex-wrap:wrap}
.hero .runcount{font-size:.68rem; color:var(--text-dim); letter-spacing:.08em; margin-top:1rem}
.themeessay{
  margin:2.8rem 0 0; padding:1.6rem 1.8rem 1.4rem;
  background:linear-gradient(180deg,#1c1108,#130a04);
  border:1px solid #3a2a1a; border-left:4px solid var(--neon);
  border-radius:0 6px 6px 0;
  box-shadow:0 14px 34px rgba(0,0,0,.45);
}
.themeessay .t-kick{font-family:'Courier Prime',monospace; font-size:.62rem; letter-spacing:.26em;
  text-transform:uppercase; color:var(--neon); margin-bottom:.7rem}
.themeessay h3{font-family:'Alfa Slab One',serif; font-weight:400; color:#f2e7cf;
  font-size:clamp(1.3rem,3vw,1.9rem); line-height:1.12; margin-bottom:.8rem}
.themeessay p{font-size:1.02rem; line-height:1.7; color:#e0d4c0; margin-bottom:.9rem}
.themeessay p.lead::first-letter{
  font-size:3em; float:left; line-height:.82; padding-right:.5rem;
  color:var(--neon); font-weight:700; font-family:'Alfa Slab One',serif;
}
.themeessay .srcs{font-size:.68rem; color:var(--text-dim); letter-spacing:.06em; line-height:1.8}
.themeessay .srcs a{border-bottom:1px dotted var(--neon2)}
.archive{margin:3.2rem 0}
.archive-head{display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:.6rem;
  border-bottom:2px solid var(--wood); padding-bottom:.5rem; margin-bottom:1.2rem}
.archive h3{font-family:'Alfa Slab One',serif; font-weight:400; color:#f2e7cf; font-size:1.3rem}
.archive .hint{font-family:'Courier Prime',monospace; font-size:.66rem; letter-spacing:.2em;
  text-transform:uppercase; color:var(--text-dim)}
.archive .hint a{color:var(--neon2)}
.arch-row{
  display:grid; grid-template-columns:110px 1fr auto; gap:1.2rem; align-items:center;
  padding:1rem .2rem; border-bottom:1px solid #3a2a1a;
}
@media(max-width:640px){.arch-row{grid-template-columns:84px 1fr}}
.arch-row img{width:110px; height:110px; object-fit:cover; border-radius:2px; transform:rotate(-1.4deg);
  box-shadow:0 2px 5px rgba(0,0,0,.5); border:1px solid rgba(255,240,200,.14)}
@media(max-width:640px){.arch-row img{width:84px; height:84px}}
.arch-row .when{font-family:'Courier Prime',monospace; font-size:.64rem; letter-spacing:.22em;
  color:var(--neon2); text-transform:uppercase}
.arch-row h4{font-size:1.05rem; color:var(--text); margin:.15rem 0 .3rem}
.arch-row h4 a{color:inherit}
.arch-row .desc{font-size:.86rem; color:var(--text-dim); line-height:1.45}
.arch-row .mini-chips{display:flex; gap:.4rem; flex-wrap:wrap; margin-top:.5rem}
.arch-row .mini-chips .chip{font-size:.58rem; padding:.18rem .48rem}
.arch-row .go{font-family:'Courier Prime',monospace; font-size:.66rem; letter-spacing:.12em;
  text-transform:uppercase; white-space:nowrap}
.stats-row{
  display:flex; gap:3.2rem; flex-wrap:wrap; justify-content:center;
  margin:1.4rem 0 1.8rem; padding:.9rem 1.2rem;
  background:linear-gradient(180deg,#1c1108,#120a04);
  border:1px solid #3a2a1a; border-radius:6px;
}
.stats-row .stat{text-align:center}
.stat .n{font-family:'Alfa Slab One',serif; font-size:1.8rem; color:#f2e7cf; line-height:1}
.stat .l{font-family:'Courier Prime',monospace; font-size:.6rem; letter-spacing:.26em;
  color:var(--text-dim); text-transform:uppercase; margin-top:.3rem}

/* ============ EXPLORE ============ */
.viewtoggle{display:flex; gap:.6rem; margin:1.6rem 0 2rem}
.vtab{
  font-family:'Courier Prime',monospace; font-size:.72rem; font-weight:700; letter-spacing:.18em;
  text-transform:uppercase; padding:.55rem 1.1rem; border-radius:999px; cursor:pointer;
  border:1px solid #3a2a1a; color:var(--text-dim); background:transparent;
}
.vtab.on{border-color:var(--neon2); color:var(--neon2); background:rgba(89,230,179,.08)}
.gsec{margin:2.6rem 0}
.gsec > h3{font-family:'Alfa Slab One',serif; font-weight:400; color:#f2e7cf; font-size:1.25rem;
  margin-bottom:.2rem}
.gsec .gcount{font-family:'Courier Prime',monospace; font-size:.64rem; letter-spacing:.24em;
  color:var(--text-dim); text-transform:uppercase; margin-bottom:1rem}
.taggroup{margin:.2rem 0 1.4rem}
.taggroup .tagname{
  font-family:'Courier Prime',monospace; font-size:.72rem; font-weight:700; letter-spacing:.16em;
  text-transform:uppercase; color:var(--sticker); padding:.25rem .7rem; border-radius:3px;
  background:var(--sticker); color:var(--ink); display:inline-block; transform:rotate(-.8deg);
  box-shadow:0 2px 5px rgba(0,0,0,.4);
}
.trow{display:flex; gap:.9rem; align-items:flex-start; padding:.7rem .2rem; border-bottom:1px solid #2c2012; flex-wrap:wrap}
.trow img{width:56px; height:56px; border-radius:2px; object-fit:cover; transform:rotate(-1.2deg);
  box-shadow:0 2px 5px rgba(0,0,0,.5); flex:0 0 auto}
.trow .who{min-width:180px; flex:1}
.trow .who b{color:var(--text); font-size:.95rem}
.trow .who .t{font-style:italic; color:var(--text-dim); font-size:.88rem}
.trow .which{font-family:'Courier Prime',monospace; font-size:.62rem; letter-spacing:.18em;
  text-transform:uppercase; white-space:nowrap}
.trow .which a{color:var(--neon2)}
.arow{padding:1rem .2rem; border-bottom:1px solid #2c2012}
.arow .top{display:flex; gap:1rem; align-items:center; flex-wrap:wrap}
.arow img{width:72px; height:72px; border-radius:3px; object-fit:cover; transform:rotate(-1.4deg);
  box-shadow:0 3px 6px rgba(0,0,0,.5)}
.arow h4{font-family:'Alfa Slab One',serif; font-weight:400; color:#f2e7cf; font-size:1.15rem; flex:1}
.alinks{display:flex; gap:.5rem; flex-wrap:wrap}
.alinks a{
  font-family:'Courier Prime',monospace; font-size:.66rem; font-weight:700; letter-spacing:.1em;
  text-transform:uppercase; padding:.34rem .7rem; border-radius:999px;
  border:1px dashed var(--text-dim); color:var(--text-dim);
}
.alinks a.bc{border-color:#1da9c4; color:#39c8e0}
.alinks a.ws{border-color:var(--neon); color:var(--neon)}
.alinks a:hover{background:rgba(255,255,255,.06)}
.arow .meta{font-size:.84rem; color:var(--text-dim); margin-top:.55rem; line-height:1.6}
.arow .meta .chip{font-size:.58rem; padding:.16rem .5rem; margin-right:.25rem}
.arow .meta .srcs a{border-bottom:1px dotted var(--neon2); color:var(--text-dim)}
.alpha{
  font-family:'Courier Prime',monospace; font-size:.72rem; letter-spacing:.14em; color:var(--neon2);
  text-transform:uppercase; margin:2.2rem 0 .4rem; border-bottom:1px solid #3a2a1a; padding-bottom:.3rem;
}

/* ============ ABOUT / COLOPHON ============ */
.about{
  margin-top:3rem; background:var(--paper); color:var(--ink); padding:1.4rem 1.5rem;
  transform:rotate(-.5deg); box-shadow:0 14px 30px rgba(0,0,0,.5); max-width:44rem;
  clip-path:polygon(0 1%,60% 0,100% 2%,99% 100%,1% 98%);
}
.about h4{font-family:'Alfa Slab One',serif; font-weight:400; font-size:1rem;
  letter-spacing:.06em; margin-bottom:.5rem; color:#8a2d18}
.about p{font-size:.9rem; line-height:1.55; color:#3a3020}
.colophon{
  margin-top:3.4rem; text-align:center; font-family:'Courier Prime',monospace;
  font-size:.64rem; letter-spacing:.28em; color:#6f5f4a; text-transform:uppercase;
}
.colophon .dot{color:var(--neon)}
"""

JS = """
(function(){
  function open(id){
    var m=document.getElementById('modal-'+id);
    if(!m) return;
    m.classList.add('open');
    var d=m.querySelector('.disc');
    if(d){d.classList.add('spin');}
    document.body.style.overflow='hidden';
    var f=m.querySelector('.sleeve-big'); if(f){f.setAttribute('tabindex','-1'); f.focus({preventScroll:true});}
  }
  function close(m){
    m.classList.remove('open');
    var d=m.querySelector('.disc'); if(d){d.classList.remove('spin');}
    document.body.style.overflow='';
  }
  document.addEventListener('click',function(e){
    var sl=e.target.closest('.sleeve[data-tid]');
    if(sl){open(sl.getAttribute('data-tid'));}
    if(e.target.closest('[data-close]')){close(e.target.closest('.modal-back'));}
    if(e.target.classList.contains('modal-back')){close(e.target);}
  });
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape'){
      var open_m=document.querySelector('.modal-back.open');
      if(open_m){close(open_m);}
    }
  });
  // Explore view toggle
  document.querySelectorAll('.vtab').forEach(function(tab){
    tab.addEventListener('click',function(){
      document.querySelectorAll('.vtab').forEach(function(t){t.classList.remove('on');});
      document.querySelectorAll('.viewpane').forEach(function(p){p.style.display='none';});
      tab.classList.add('on');
      var pane=document.getElementById(tab.getAttribute('data-pane'));
      if(pane){pane.style.display='block';}
    });
  });
})();
"""

TAG_COLORS = ["var(--sticker)", "var(--sticker-blue)", "var(--sticker-green)",
              "var(--sticker-purple)", "var(--sticker-red)", "var(--sticker-tan)"]

def tag_color(tag):
    h = sum(ord(c) for c in tag)
    c = TAG_COLORS[h % len(TAG_COLORS)]
    dark = c == "var(--sticker-tan)"
    return f"background:{c}; color:{'#f6ecd6' if dark else '#241c12'}"

def chip(tag, count=None, href=None):
    inner = f"{esc(tag)} <b>{count}</b>" if count is not None else esc(tag)
    if href:
        return f'<a class="chip" href="{esc(href)}">{inner}</a>'
    return f'<span class="chip">{inner}</span>'

def vintage(track):
    try:
        return int(year(track.get("release_date")) or 0) < 2015
    except ValueError:
        return False

def artist_name(tr):
    return tr["artists"][0] if tr.get("artists") else tr.get("artist", "")

def sleeve_html(tr, ed, tag, is_pick):
    b = ed["blurbs"].get(tr["uri"], {})
    uri_id = tr["uri"].rsplit(":", 1)[-1]
    art = esc(tr.get("album_art") or "")
    artist = esc(artist_name(tr))
    title = esc(tr.get("name") or tr.get("track"))
    hype = dur(tr.get("duration_ms")) or "—"
    vint = " vintage" if vintage(tr) else ""
    tag_html = (f'<div class="starburst">EDITOR’S<br>PICK</div>' if is_pick
                else f'<div class="tag" style="{tag_color(tag)}">{esc(tag)}</div>')
    hand = ""
    if b.get("quote") and len(b["quote"]) < 70:
        frag = b["quote"].split("—")[0].strip().strip('"“”')[:38]
        hand = f'<div class="hand-note">“{esc(frag)}”</div>'
    return f'''<div class="sleeve{vint}" data-tid="{uri_id}" tabindex="0" role="button"
     aria-label="{artist} {title}">
  {tag_html}
  <img loading="lazy" src="{art}" alt="{artist} — {title} album art">
  <div class="hype">{hype}</div>
  {hand}
  <div class="spine">
    <div class="artist">{artist}</div>
    <div class="title">{title}</div>
  </div>
</div>'''

def modal_html(tr, ed, tag, pos, is_pick, ed_date, artist_links=None):
    b = ed["blurbs"].get(tr["uri"], {})
    src = ed["sources"].get(b.get("src", ""), {})
    uri_id = tr["uri"].rsplit(":", 1)[-1]
    art = esc(tr.get("album_art") or "")
    artist = esc(artist_name(tr))
    title = esc(tr.get("name") or tr.get("track"))
    album = esc(tr.get("album"))
    y = year(tr.get("release_date"))
    d = dur(tr.get("duration_ms"))
    facts = []
    if is_pick: facts.append("<b>EDITOR’S PICK</b>")
    if album: facts.append(f"<b>{album}</b>" + (f" · {y}" if y else ""))
    if d: facts.append(d)
    if tag: facts.append(esc(tag))
    label = f"NOW<br>SPINNING<br>{ed_date}"
    quote = f'<blockquote class="press">{esc(b["quote"])}</blockquote>' if b.get("quote") else ""
    clip = ""
    if src and src.get("url"):
        clip = f'''<div class="clipping">
  <div class="from">✂ source — where this was found</div>
  <a href="{esc(src['url'])}" target="_blank" rel="noopener">{esc(src.get('name','source'))}</a>
  <span class="outlet">{esc(src.get('outlet',''))}</span>
</div>'''
    elif src:
        clip = f'''<div class="clipping">
  <div class="from">✂ source</div>
  {esc(src.get('name','source'))}
  <span class="outlet">{esc(src.get('outlet',''))}</span>
</div>'''
    play = (f'<a class="spotify-btn" href="{esc(tr["url"])}" target="_blank" rel="noopener">▶ Play on Spotify</a>'
            if tr.get("url") else "")
    bc = ""
    if artist_links and artist_links.get("bandcamp"):
        bc = (f'<a class="ghost-btn" href="{esc(artist_links["bandcamp"])}" target="_blank" rel="noopener">'
              f'◆ Bandcamp</a>')
    return f'''<div class="modal-back" id="modal-{uri_id}">
  <div class="modal" role="dialog" aria-label="{artist} {title}">
    <button class="closer" data-close aria-label="close">✕</button>
    <div class="vinyl-side">
      <div class="the-record">
        <div class="disc" data-label="{label}"></div>
        <div class="sleeve-big"><img src="{art}" alt=""><div class="corner"></div></div>
      </div>
    </div>
    <div class="notes-side">
      <div class="kick">№ {pos:02d} · {esc(ed_date)}</div>
      <h3>{artist}<span class="t">{title}</span></h3>
      <div class="facts">{" &nbsp;·&nbsp; ".join(facts)}</div>
      <p class="body">{esc(b.get("text", ""))}</p>
      {quote}
      {clip}
      <div class="playrow">{play}{bc}</div>
    </div>
  </div>
</div>'''

def page(title, body, desc="", nav_active="", pre_nav=""):
    nav = [("THE LOG", "/", "log"), ("EXPLORE", "/explore/", "explore")]
    parts = []
    for label, href, key in nav:
        cls = ' class="nav-active"' if key == nav_active else ""
        parts.append(f'<a href="{href}"{cls}>{label}</a>')
    nav_html = f'<span class="navlinks">{" ".join(parts)}</span>'
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='46' fill='%23111114'/><circle cx='50' cy='50' r='14' fill='%23c8442e'/><circle cx='50' cy='50' r='4' fill='%23111114'/></svg>">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Monoton&family=Alfa+Slab+One&family=Caveat:wght@500;700&family=Courier+Prime:wght@400;700&family=Libre+Franklin:wght@400;600;700&display=swap" rel="stylesheet">
<style>
{CSS}
</style>
</head>
<body>
<div class="wrap">
<header class="masthead">
  <div class="monday-note hand" style="color:#59e6b3; font-size:1.05rem; transform:rotate(-4deg); text-shadow:0 0 8px rgba(89,230,179,.7)">♪ new edition every monday ♪</div>
  <div class="tube">NOW SPINNING</div>
  <div class="under"><span>{TAGLINE.upper()}</span><span class="dot">●</span><span>EST. 2026</span></div>
</header>
{pre_nav}
<nav class="blogstrip">
  {nav_html}
  <span>CRATE-DIGGING, DOCUMENTED</span>
  <span>NO ALGORITHMS · EVER</span>
</nav>
{body}
<footer>
  <div class="about">
    <h4>ABOUT THIS LOG</h4>
    <p>Every Monday: one playlist of new and lesser-known prog, fusion and fringe,
    assembled from the week’s writing. Nothing over 500k monthly listeners; no artist
    twice in eight weeks; no track ever repeats. Every entry credits the article that
    found it, and <a href="/explore/">Explore</a> indexes the whole growing collection —
    by genre and by artist. The archive grows forever.</p>
  </div>
  <div class="colophon">NOW SPINNING <span class="dot">●</span> COMPILED WEEKLY <span class="dot">●</span> EVERY SLEEVE SOURCED</div>
</footer>
</div>
<script>{JS}</script>
</body>
</html>'''

def load_all():
    artists = {}
    ap = DATA / "artists.json"
    if ap.exists():
        artists = json.loads(ap.read_text())
    editions = []
    for d in sorted(DATA.iterdir(), reverse=True) if DATA.exists() else []:
        if not (d / "edition.json").exists() or not (d / "tracks.json").exists():
            continue
        ed = json.loads((d / "edition.json").read_text())
        tk = json.loads((d / "tracks.json").read_text())
        lanes = {}
        try:
            for t in json.loads((Path.home() / ".hermes/prog-discovery/draft.json").read_text()).get("tracks", []):
                lanes[t["uri"]] = t.get("lane", "")
        except Exception:
            pass
        tracks = []
        for t in tk["tracks"]:
            t2 = dict(t)
            t2["tag"] = ed.get("tags", {}).get(t["uri"]) or "unclassified"
            t2["lane"] = lanes.get(t["uri"], "")
            tracks.append(t2)
        editions.append({"dir": d.name, "ed": ed, "tk": tk, "tracks": tracks})
    return editions, artists

def build_edition(e, artists):
    ed, tk, tracks = e["ed"], e["tk"], e["tracks"]
    cover = (tk.get("images") or [{}])[0].get("url", "")
    n = len(tracks)
    date = ed["date"]
    title_bit = ed["playlist_title"].split("— ")[-1]
    theme = ed.get("theme", {})
    deep = theme.get("deep", {})
    deep_block = ""
    if deep:
        art_of = {}
        for tr in tracks:
            an = artist_name(tr)
            if an not in art_of and tr.get("album_art"):
                art_of[an] = tr["album_art"]
        paras = "".join(f'<p class="dpara">{esc(p)}</p>' for p in deep.get("paras", []))
        trees = []
        for t in deep.get("trees", []):
            items = []
            for it in t.get("items", []):
                mark = '<span class="here-mark">◆ THIS EDITION</span>' if it.get("here") else ""
                art = art_of.get(it["name"].split(" (")[0].split(" →")[0].strip())
                img = (f'<img loading="lazy" src="{esc(art)}" alt="">' if art else
                       '<span class="node-blank"></span>')
                items.append(f'''<li>{img}<span class="node"><b>{esc(it["name"])}</b> — {esc(it["note"])}{mark}</span></li>''')
            trees.append(f'''<div class="tree">
  <div class="tree-title">{esc(t["title"])}</div>
  <div class="tree-root mono">{esc(t["root"])}</div>
  <ul class="tree-items">{"".join(items)}</ul>
  <div class="tree-cap hand">{esc(t.get("caption", ""))}</div>
</div>''')
        deep_block = f'''<section class="deepdive">
  <h2>THE DEEP DIVE — {esc(theme.get("name", "").upper())}</h2>
  <p class="lead">{esc(deep.get("intro", ""))}</p>
  {paras}
  <div class="trees">{"".join(trees)}</div>
  <p class="outro">{esc(deep.get("outro", ""))}</p>
</section>'''
    shelf_map = {}
    for tr in tracks:
        shelf_map.setdefault(shelf_for(tr["tag"]), []).append(tr)
    order = {"prog-metal": 0, "prog-rock": 1, "post-psych": 2, "jazz-fusion": 3, "jazz": 4, "zeuhl-cant": 5, "fringe": 6}
    parts = [f'''<div class="edhead">
  <img class="cover" src="{esc(cover)}" alt="playlist cover mosaic">
  <div>
    <div class="kick" style="font-family:'Courier Prime',monospace;font-size:.66rem;letter-spacing:.3em;color:var(--neon2)">EDITION {ed["week"]} · {esc(date)} · {n} TRACKS</div>
    <h2>{esc(title_bit)}</h2>
    <p class="sub">The full log for this week — every entry annotated and sourced.
    <a href="{esc(ed['playlist_url'])}" style="white-space:nowrap">▶ play the whole edition on Spotify</a></p>
    <span class="ednote">{esc(ed["editor_note"].split(". ")[0])}. — ed.</span>
  </div>
</div>''']
    parts.append(deep_block)
    modals = []
    i = 1
    spotlight_uris = set()
    if ed.get("scene"):
        sc = [t for t in tracks if t.get("lane") == "scene"]
        spotlight_uris = {t["uri"] for t in sc}
        sleeves = "".join(sleeve_html(t, ed, t["tag"], False) for t in sc)
        parts.append(f'''<section class="spotlight" id="spotlight">
  <h2>★ SPOTLIGHT · FEATURED SCENE ★</h2>
  <div class="name">{esc(ed["scene"])}</div>
  <p class="note">Each edition tips the hat to one scene — a geography, a family tree, a moment. This week: {esc(ed["scene"])}.</p>
  <div class="crate" style="margin-top:1.1rem"><div class="sleeves">{sleeves}</div></div>
</section>''')
        for tr in sc:
            modals.append(modal_html(tr, ed, tr["tag"], i, False, date, artists.get(artist_name(tr)))); i += 1
    for key in sorted(shelf_map, key=lambda k: order.get(k, 9)):
        items = [t for t in shelf_map[key] if t["uri"] not in spotlight_uris]
        label = SHELF_LABEL[key]
        subs = " · ".join(sorted({t["tag"] for t in items}))
        sleeves = "".join(sleeve_html(t, ed, t["tag"], t.get("lane") == "wildcard") for t in items)
        parts.append(f'''<section class="shelf-section" id="shelf-{esc(key)}">
  <div class="shelf-head">
    <div class="divider">{esc(label)}<span class="count">{len(items)} TRACKS</span></div>
    <div class="bin-sub">{esc(subs)}</div>
  </div>
  <div class="crate"><div class="sleeves">{sleeves}</div></div>
</section>''')
        for tr in items:
            modals.append(modal_html(tr, ed, tr["tag"], i, tr.get("lane") == "wildcard", date, artists.get(artist_name(tr)))); i += 1
    parts.append("".join(modals))
    return page(f'{title_bit} — {SITE_NAME}', "\n".join(parts),
                desc=f'Liner notes for the {date} edition: {n} tracks, every source linked.', nav_active="log")

def build_front(editions, artists):
    e = editions[0]
    ed, tk, tracks = e["ed"], e["tk"], e["tracks"]
    cover = (tk.get("images") or [{}])[0].get("url", "")
    total_tracks = sum(len(x["tracks"]) for x in editions)
    all_artists = {artist_name(t) for x in editions for t in x["tracks"]}
    tag_count = {}
    for x in editions:
        for t in x["tracks"]:
            tag_count[t["tag"]] = tag_count.get(t["tag"], 0) + 1
    theme = ed.get("theme", {})
    src_seen = {}
    for key, s in ed["sources"].items():
        if s.get("url"):
            src_seen.setdefault(s.get("outlet", s["name"]),
                                f'<a href="{esc(s["url"])}" target="_blank" rel="noopener">{esc(s.get("outlet", s["name"]))}</a>')
    src_str = " · ".join(src_seen.values()) or "the standing pool"

    hero = f'''<section class="hero">
  <div class="hero-grid">
    <a href="{esc(e['dir'])}/"><img class="cover" src="{esc(cover)}" alt="latest edition cover"></a>
    <div>
      <div class="kick">LATEST EDITION · {esc(ed["date"])} · {len(tracks)} TRACKS</div>
      <h2><a href="{esc(e['dir'])}/">{esc(ed["playlist_title"].split("— ")[-1])}</a></h2>
      <div class="actions">
        <a class="spotify-btn" href="{esc(ed['playlist_url'])}">▶ Spotify</a>
        <a href="{esc(e['dir'])}/" class="ghost-btn">Read the edition →</a>
      </div>
    </div>
  </div>
</section>'''

    stats = f'''<div class="stats-row">
  <div class="stat"><div class="n">{len(editions)}</div><div class="l">editions</div></div>
  <div class="stat"><div class="n">{total_tracks}</div><div class="l">tracks logged</div></div>
  <div class="stat"><div class="n">{len(all_artists)}</div><div class="l">artists</div></div>
  <div class="stat"><div class="n">{len(tag_count)}</div><div class="l">genre tags</div></div>
</div>'''

    theme_block = ""
    if theme and theme.get("paras"):
        plist = []
        for i, p in enumerate(theme["paras"]):
            cls = ' class="lead"' if i == 0 else ""
            plist.append(f"<p{cls}>{esc(p)}</p>")
        paras = "".join(plist)
        theme_block = f'''<section class="themeessay">
  <div class="t-kick">★ {esc(theme.get("kicker", "THE THEME THIS WEEK"))} — {esc(theme.get("origin", ""))}</div>
  <h3>{esc(theme.get("name", ""))}</h3>
  {paras}
  <div class="srcs mono">Sourced from the week’s writing: {src_str}</div>
</section>'''
    else:
        theme_block = f'''<section class="themeessay">
  <div class="t-kick">★ {esc(ed["editor_note"].split(". ")[0])}</div>
  <p class="lead">{esc(ed["editor_note"])}</p>
  <div class="srcs mono">Sourced from the week’s writing: {src_str}</div>
</section>'''

    rows = []
    for x in editions[1:]:
        cov = (x["tk"].get("images") or [{}])[0].get("url", "")
        xtheme = x["ed"].get("theme", {})
        theme_line = esc((xtheme.get("paras") or [""])[0])[:170] + "…"
        rows.append(f'''<div class="arch-row">
  <a href="{esc(x['dir'])}/"><img src="{esc(cov)}" alt=""></a>
  <div>
    <div class="when">EDITION {x["ed"]["week"]} · {esc(x["ed"]["date"])}</div>
    <h4><a href="{esc(x['dir'])}/">{esc(xtheme.get("name", x["ed"]["playlist_title"].split("— ")[-1]))}</a></h4>
    <div class="desc">{theme_line}</div>
  </div>
  <div class="go"><a href="{esc(x['dir'])}/">READ →</a></div>
</div>''')
    archive = f'''<section class="archive">
  <div class="archive-head">
    <h3>The Archive</h3>
    <span class="hint">EVERY EDITION, FOREVER · <a href="/explore/">EXPLORE THE COLLECTION →</a></span>
  </div>
  {"".join(rows) if rows else '<p class="desc" style="color:var(--text-dim)">Older editions will collect here as the weeks go on.</p>'}
</section>'''
    return page(f'{SITE_NAME} — {TAGLINE}', hero + theme_block + archive,
                nav_active="log", pre_nav=stats)

def build_explore(editions, artists):
    # ---- genre pane ----
    shelf_map = {}
    for x in editions:
        for tr in x["tracks"]:
            shelf_map.setdefault(shelf_for(tr["tag"]), {}).setdefault(tr["tag"], []).append((tr, x))
    order = {"prog-metal": 0, "prog-rock": 1, "post-psych": 2, "jazz-fusion": 3, "jazz": 4, "zeuhl-cant": 5, "fringe": 6}
    gsecs = []
    for key in sorted(shelf_map, key=lambda k: order.get(k, 9)):
        tags = shelf_map[key]
        total = sum(len(v) for v in tags.values())
        groups = []
        for tag in sorted(tags, key=lambda t: -len(tags[t])):
            rows = []
            for (tr, x) in tags[tag]:
                art = esc(tr.get("album_art") or "")
                rows.append(f'''<div class="trow">
  {f'<img loading="lazy" src="{art}" alt="">' if art else ''}
  <div class="who"><b>{esc(artist_name(tr))}</b> — <span class="t">{esc(tr.get("name") or tr.get("track"))}</span></div>
  <div class="which"><a href="/{esc(x['dir'])}/">ED. {x["ed"]["week"]} · {esc(x["ed"]["date"])}</a></div>
</div>''')
            groups.append(f'''<div class="taggroup" id="g-{esc(tag)}">
  <span class="tagname">{esc(tag)} · {len(tags[tag])}</span>
  {"".join(rows)}
</div>''')
        gsecs.append(f'''<section class="gsec">
  <h3>{esc(SHELF_LABEL[key])}</h3>
  <div class="gcount">{total} tracks · {len(tags)} tags</div>
  {"".join(groups)}
</section>''')
    genre_pane = "".join(gsecs)
    # ---- artist pane ----
    artist_map = {}
    for x in editions:
        for tr in x["tracks"]:
            an = artist_name(tr)
            artist_map.setdefault(an, {"tracks": [], "editions": [], "tags": set(), "srcs": []})
            artist_map[an]["tracks"].append(tr)
            if x not in artist_map[an]["editions"]:
                artist_map[an]["editions"].append(x)
            artist_map[an]["tags"].add(tr["tag"])
            b = x["ed"]["blurbs"].get(tr["uri"], {})
            s = x["ed"]["sources"].get(b.get("src", ""))
            if s and s.get("url") and not any(old.get("url") == s.get("url") for old in artist_map[an]["srcs"]):
                artist_map[an]["srcs"].append(s)
    letters = {}
    for an in sorted(artist_map, key=str.casefold):
        L = an[0].upper()
        if not L.isalpha(): L = "#"
        letters.setdefault(L, []).append(an)
    arows = []
    for L in sorted(letters):
        arows.append(f'<div class="alpha">{L}</div>')
        for an in letters[L]:
            info = artist_map[an]
            tr0 = info["tracks"][0]
            art = esc(tr0.get("album_art") or "")
            links = artists.get(an, {})
            la = []
            if links.get("bandcamp"):
                la.append(f'<a class="bc" href="{esc(links["bandcamp"])}" target="_blank" rel="noopener">◆ Bandcamp</a>')
            if links.get("website"):
                la.append(f'<a class="ws" href="{esc(links["website"])}" target="_blank" rel="noopener">⌂ Website</a>')
            if tr0.get("artist_spotify"):
                la.append(f'<a href="{esc(tr0["artist_spotify"])}" target="_blank" rel="noopener">▶ Spotify</a>')
            tag_chips = "".join(chip(t, href=f"/explore/#g-{t}") for t in sorted(info["tags"]))
            ed_links = " · ".join(
                f'<a href="/{esc(x["dir"])}/">ED. {x["ed"]["week"]}</a>' for x in sorted(info["editions"], key=lambda z: z["ed"]["week"]))
            src_html = ""
            if info["srcs"]:
                src_html = ' Found via ' + " · ".join(
                    f'<a href="{esc(s["url"])}" target="_blank" rel="noopener">{esc(s["name"])}</a>'
                    for s in info["srcs"][:3])
            arows.append(f'''<div class="arow" id="a-{esc(an)}">
  <div class="top">
    {f'<img loading="lazy" src="{art}" alt="">' if art else ''}
    <h4>{esc(an)}</h4>
    <div class="alinks">{"".join(la)}</div>
  </div>
  <div class="meta">
    {len(info["tracks"])} track{"s" if len(info["tracks"])>1 else ""} · appeared in {ed_links}{src_html}
    <div class="mini-chips" style="margin-top:.45rem">{tag_chips}</div>
  </div>
</div>''')
    artist_pane = "".join(arows)
    body = (f'''<div class="kick" style="font-family:'Courier Prime',monospace;font-size:.66rem;
  letter-spacing:.3em;color:var(--neon2);margin-bottom:.4rem">THE WHOLE COLLECTION · GROWS EVERY MONDAY</div>
<h2 style="font-family:'Alfa Slab One',serif;font-weight:400;color:#f2e7cf;font-size:2.1rem;margin-bottom:.3rem">Explore</h2>
<p style="color:var(--text-dim);font-size:.92rem;max-width:44rem">Every track ever logged, indexed two ways.
Genres are the fine tags the editors assign; artists carry their verified pages and the articles that
introduced them.</p>
<div class="viewtoggle">
  <button class="vtab on" data-pane="pane-genres">Genres</button>
  <button class="vtab" data-pane="pane-artists">Artists A–Z</button>
</div>
<div class="viewpane" id="pane-genres">{genre_pane}</div>
<div class="viewpane" id="pane-artists" style="display:none">{artist_pane}</div>''')
    return page(f'Explore — {SITE_NAME}', body, nav_active="explore")

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    editions, artists = load_all()
    if not editions:
        print("no editions under", DATA); sys.exit(1)
    for e in editions:
        (OUT / e["dir"]).mkdir(parents=True, exist_ok=True)
        (OUT / e["dir"] / "index.html").write_text(build_edition(e, artists))
        print(f"built edition {e['dir']}")
    (OUT / "index.html").write_text(build_front(editions, artists))
    (OUT / "explore").mkdir(parents=True, exist_ok=True)
    (OUT / "explore" / "index.html").write_text(build_explore(editions, artists))
    # retire the old /genres/ page — Explore replaces it
    old = OUT / "genres"
    if old.exists():
        import shutil; shutil.rmtree(old)
    print(f"built front + explore ({len(editions)} editions)")

if __name__ == "__main__":
    main()
