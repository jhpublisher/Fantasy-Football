"""Build the GitHub site pages (Rich). Never touches curated data.
Usage: python3 mksite.py --bi <front-office-bi.html> --briefing <ceo-briefing.html> --site <legal-troubles dir>
                         [--mkgithub <mkgithub.py>] [--returns-tab <dir with build_rg.py + returns_tab.js>]
Writes ONLY <site>/index.html and <site>/briefing.html.
- index.html is derived from the claude.ai dashboard source by claude/tools/mkgithub.py (the page engineer's
  converter: bundle loader, data/validation.json banner, league/sections/returns wiring), so the two pages never drift.
  The old hand-written loader is gone. claude/tools/github-index.html is that same output, kept for review.
- --returns-tab adds the Returns tab (returns/build_rg.py github mode, which outputs a full page). Leave it off until Joe approves the tab going live.
- briefing.html = ceo-briefing.html wrapped in the page skeleton, with the dashboard link pointed at ./
- Curated files (tags/claims/needs/rumors/watchlist/memos) are staff-edited and never written here.
- Any missing input or failed step exits non-zero instead of writing a half-built page."""
import argparse, os, sys, subprocess, tempfile, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--bi", required=True, help="dashboard source html (claude/tools/front-office-bi.html)")
ap.add_argument("--briefing", required=True, help="CEO briefing source html (claude/tools/ceo-briefing.html)")
ap.add_argument("--site", required=True, help="site folder (legal-troubles/) to write index.html and briefing.html into")
ap.add_argument("--mkgithub", default=os.path.join(HERE, "mkgithub.py"))
ap.add_argument("--returns-tab", help="folder holding build_rg.py and returns_tab.js; adds the Returns tab")
A = ap.parse_args()
for f in (A.bi, A.briefing, A.mkgithub):
    if not os.path.isfile(f): sys.exit(f"mksite: input not found: {f}")
if not os.path.isdir(A.site): sys.exit(f"mksite: site folder not found: {A.site}")
def run(cmd):
    r = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
    if r.returncode: sys.exit(f"mksite: {' '.join(cmd)} failed:\n{r.stdout}{r.stderr}")
    return r.stdout.strip()
tmp = tempfile.mkdtemp()
idx = os.path.join(tmp, "index.html")
print(run([A.mkgithub, A.bi, idx]))
if A.returns_tab:
    brg = os.path.join(A.returns_tab, "build_rg.py")
    if not os.path.isfile(brg) or not os.path.isfile(os.path.join(A.returns_tab, "returns_tab.js")): sys.exit(f"mksite: build_rg.py/returns_tab.js not in {A.returns_tab}")
    idx2 = os.path.join(tmp, "index_rg.html"); print(run([brg, idx, idx2, "github"])); idx = idx2
head = '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n</head><body>\n'
h = open(idx, encoding="utf-8").read()
if not h.lstrip().lower().startswith("<!doctype") or "[hidden]{display:none!important}" not in h:
    sys.exit("mksite: generated index.html is not a complete page (missing doctype or [hidden] rule)")
for must in ("data/bundle.json", "data/validation.json"):
    if must not in h: sys.exit(f"mksite: generated index.html does not reference {must}")
shutil.copy(idx, os.path.join(A.site, "index.html"))
br = open(A.briefing, encoding="utf-8").read()
br = br.replace("https://claude.ai/artifact/9bVL3ymquPCAGnqZKxYRYE", "./").replace('target="_blank" rel="noopener">BI dashboard and GM notes', ">BI dashboard and GM notes")
if not br.lstrip().lower().startswith("<!doctype"): br = head + br + "\n</body></html>\n"
open(os.path.join(A.site, "briefing.html"), "w", encoding="utf-8").write(br)
shutil.rmtree(tmp, ignore_errors=True)
print("mksite ok:", os.path.join(A.site, "index.html"), os.path.join(A.site, "briefing.html"), "(returns tab: %s; curated/ untouched)" % ("on" if A.returns_tab else "off"))
