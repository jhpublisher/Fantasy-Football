"""Legal Troubles news + practice sweep (Frank). Run: python3 news_sweep.py <out_dir> [hours=72]
Pulls ESPN/Rotowire player news for every fantasy-relevant player (rostered in our league or >=3% owned),
classifies what matters to us, and parses practice participation (DNP / Limited / Full) by day.
Writes dashboard docs: news/ours, news/league, practice/current."""
import json, os, re, sys, urllib.request, concurrent.futures as cf
from datetime import datetime, timezone, timedelta
LG = 293318; YR = 2026
B = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{YR}/segments/0/leagues/{LG}"
out = sys.argv[1] if len(sys.argv) > 1 else "news_out"; HRS = int(sys.argv[2]) if len(sys.argv) > 2 else 72
WATCH_FILE = os.environ.get("LT_WATCHLIST") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.json")  # optional: {"names": [...]}
def get(url, hdr=None): return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=hdr or {}), timeout=60))
t = get(f"{B}?view=mTeam&view=mStatus"); names = {x["id"]: x["name"].strip() for x in t["teams"]}
me = [k for k, v in names.items() if "Legal" in v][0]; wk = t["status"]["currentMatchupPeriod"]
pro = get(f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{YR}?view=proTeamSchedules_wl")
ab = {p["id"]: p["abbrev"] for p in pro["settings"]["proTeams"]}
flt = {"players": {"limit": 900, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
allp = get(f"{B}?scoringPeriodId={wk}&view=kona_player_info", {"X-Fantasy-Filter": json.dumps(flt)})["players"]
watch = set(json.load(open(WATCH_FILE))["names"]) if os.path.exists(WATCH_FILE) else set()
POS = {1:"QB",2:"RB",3:"WR",4:"TE",5:"K",16:"D/ST"}
pool = []
for pe in allp:
    p = pe["player"]; own = pe.get("onTeamId", 0); pct = p.get("ownership", {}).get("percentOwned", 0)
    if POS.get(p["defaultPositionId"]) in (None, "K", "D/ST"): continue
    if own or pct >= 3 or p["fullName"] in watch:
        pool.append({"id": p["id"], "name": p["fullName"], "pos": POS[p["defaultPositionId"]], "nfl": ab.get(p.get("proTeamId"), "FA"),
                     "owner": names.get(own, "Free agent"), "ours": own == me, "watch": p["fullName"] in watch, "status": p.get("injuryStatus") or "ACTIVE", "pct": round(pct)})
our_nfl = {p["nfl"] for p in pool if p["ours"]}
def news(p):
    try: return p, get(f"https://site.api.espn.com/apis/fantasy/v2/games/ffl/news/players?playerId={p['id']}&limit=6").get("feed", [])
    except Exception: return p, []
cut = datetime.now(timezone.utc) - timedelta(hours=HRS)
KEY = re.compile(r"\b(sign|signed|signing|release|released|waive|trade|traded|injured reserve|activated|designated to return|suspen|physical|practice squad|ruled out|out for|week-to-week|season-ending|torn|surgery|concussion|depth chart|starting|starter|benched|demoted|promoted|lead back|bell-cow|reached out|visit|workout|expected to)\w*", re.I)
PRAC = [(re.compile(r"\b(did not practice|didn't practice|not practicing|sat out practice|DNP)\b", re.I), "DNP"),
        (re.compile(r"\b(limited|limited participant|limited basis)\b", re.I), "Limited"),
        (re.compile(r"\b(practiced in full|full participant|full practice|full session|fully participated|practiced fully)\b", re.I), "Full")]
ours, league, practice = [], [], {}
with cf.ThreadPoolExecutor(16) as ex:
    for p, feed in ex.map(news, pool):
        for f in feed:
            if f.get("type") != "Rotowire": continue
            ts = datetime.fromisoformat(f["published"].replace("Z", "+00:00"))
            if ts < cut - timedelta(days=5): continue
            hl = f["headline"]; low = hl.lower()
            item = {"player": p["name"], "pos": p["pos"], "nfl": p["nfl"], "owner": p["owner"], "time": f["published"][:16] + "Z", "headline": f["headline"]}
            if (p["ours"] or p["watch"]) and ("practic" in low or "session" in low or "participant" in low):
                for rx, lab in PRAC:
                    loc = ts.astimezone(timezone(timedelta(hours=-4)))
                    if rx.search(hl) and loc.weekday() in (2, 3, 4, 5):
                        rec = practice.setdefault(p["name"], {"pos": p["pos"], "nfl": p["nfl"], "ours": p["ours"], "days": {}})
                        rec["days"][loc.strftime("%a %m/%d")] = {"status": lab, "note": hl[:160]}
                        break
            if ts < cut: continue
            if p["ours"]: ours.append(item | {"why": "Our player"}); continue
            why = None
            if p["watch"]: why = "On our watch list"
            elif p["nfl"] in our_nfl and KEY.search(hl): why = f"Affects our {p['nfl']} players"
            elif p["owner"] == "Free agent" and KEY.search(hl): why = "Free agent with a role change"
            elif KEY.search(hl) and p["pct"] >= 50: why = "Major news, league-wide"
            if why: league.append(item | {"why": why})
# ---------- multi-source desk: RSS + Google News insider search + Sleeper trending ----------
import xml.etree.ElementTree as ET, email.utils, html, urllib.parse
UA = {"User-Agent": "Mozilla/5.0 (LegalTroubles NewsDesk)"}
INSIDERS = ["Adam Schefter", "Ian Rapoport", "Tom Pelissero", "Mike Garafolo", "Jeremy Fowler", "Jordan Schultz", "Mike Silver", "Jay Glazer", "Dianna Russini", "Albert Breer"]
FEEDS = {
 "RotoWire": "https://www.rotowire.com/rss/news.php?sport=NFL",
 "ProFootballTalk": "https://profootballtalk.nbcsports.com/feed/",
 "CBS Sports": "https://www.cbssports.com/rss/headlines/nfl/",
 "ESPN": "https://www.espn.com/espn/rss/nfl/news",
 "Rotoworld": "https://feeds.feedburner.com/rotoworld/nfl",
}
gq = lambda q: "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q + " when:2d", "hl": "en-US", "gl": "US", "ceid": "US:en"})
for n in INSIDERS: FEEDS[f"Google News: {n}"] = gq(f'"{n}" NFL')
for q in ["NFL signs free agent", "NFL waived released", "NFL trade rumors", "NFL injured reserve", "NFL practice squad elevated running back"]: FEEDS[f"Google News: {q}"] = gq(q)
def rss(src_url):
    src, url = src_url
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25).read()
        root = ET.fromstring(raw); out_ = []
        for it in root.iter("item"):
            title = html.unescape((it.findtext("title") or "").strip()); link = it.findtext("link") or ""
            pd = it.findtext("pubDate"); desc = html.unescape(re.sub("<[^>]+>", "", it.findtext("description") or ""))[:300]
            try: ts = email.utils.parsedate_to_datetime(pd).astimezone(timezone.utc)
            except Exception: continue
            out_.append({"src": src, "title": title, "link": link, "ts": ts, "desc": desc})
        return out_
    except Exception as e:
        return [{"src": src, "error": str(e)[:80]}]
by_name = {}
for p in pool: by_name[p["name"]] = p
last = {}  # last-name index for "Mixon" style headlines
for p in pool:
    ln = p["name"].replace(" Jr.", "").replace(" Sr.", "").replace(" III", "").replace(" II", "").split()[-1]
    if len(ln) > 3: last.setdefault(ln, []).append(p)
desk, seen, health = [], set(), {}
with cf.ThreadPoolExecutor(12) as ex:
    for items in ex.map(rss, FEEDS.items()):
        for it in items:
            if "error" in it: health[it["src"]] = "error: " + it["error"]; continue
            health[it["src"]] = "ok"
            if it["ts"] < cut: continue
            text = it["title"] + " " + it["desc"]
            hits = [p for n, p in by_name.items() if n in text]
            if not hits:
                for ln, ps in last.items():
                    if re.search(rf"\b{re.escape(ln)}\b", it["title"]) and len(ps) == 1: hits.append(ps[0])
            for p in hits[:2]:
                k = (p["name"], it["title"][:60].lower())
                if k in seen: continue
                seen.add(k)
                rel = "Our player" if p["ours"] else "On our watch list" if p["watch"] else f"Affects our {p['nfl']} players" if p["nfl"] in our_nfl else "Free agent" if p["owner"] == "Free agent" else "League-wide"
                if rel in ("League-wide",) and not KEY.search(it["title"]): continue
                if rel == "Free agent" and not KEY.search(it["title"]): continue
                item = {"player": p["name"], "pos": p["pos"], "nfl": p["nfl"], "owner": p["owner"], "time": it["ts"].isoformat(timespec="minutes").replace("+00:00", "Z"), "headline": it["title"], "source": it["src"], "link": it["link"], "why": rel}
                (ours if p["ours"] else league).append(item)
# Sleeper: what the fantasy world is adding right now (crowd signal)
try:
    tr = json.load(urllib.request.urlopen(urllib.request.Request("https://api.sleeper.app/v1/players/nfl/trending/add?lookback_hours=24&limit=25", headers=UA), timeout=25))
    health["Sleeper trending"] = "ok"
except Exception as e: tr = []; health["Sleeper trending"] = "error"
trending = []
if tr:
    try:
        sp = json.load(urllib.request.urlopen(urllib.request.Request("https://api.sleeper.app/v1/players/nfl", headers=UA), timeout=60))
        for t_ in tr:
            q = sp.get(t_["player_id"], {}); nm = q.get("full_name") or ""
            p = by_name.get(nm)
            trending.append({"player": nm, "pos": q.get("position"), "nfl": q.get("team") or "FA", "adds24h": t_["count"], "owner": p["owner"] if p else "Free agent (not in our pool)"})
    except Exception: health["Sleeper players"] = "error"
# ---------- classify: Rumor / Confirmed / Analysis / News, and build the rumor mill ----------
RUMOR = re.compile(r"\b(rumou?r|reportedly|expected to|plan(s|ning)? to|in talks|interest(ed)? in|reached out|linked|considering|eyeing|could|potential|possible|visit|work(ed|ing)? out|workout|pending|candidate|would|trade idea|sweepstakes|inevitable|urged|monitor)\w*", re.I)
CONF = re.compile(r"\b(signed|signs|has signed|placed on|released|waived|traded to|acquired|activated|elevated|claimed|officially|ruled out|will miss|underwent)\b", re.I)
NOISE = re.compile(r"(waiver wire|fantasy football|start\W*sit|best bets|player props|picks,|rankings|grades?|grading|mock|quotes|FAAB|DFS|winners and losers|power rankings)", re.I)
MOVE = re.compile(r"\b(sign|trade|release|waive|cut|claim|acquire|deal|contract|visit|work(out| out)|reunion|interest|practice squad|IR|injured reserve|suspen|starter|starting|demot|promot|lead back)\w*", re.I)
def kind(h):
    if NOISE.search(h): return "Analysis"
    if RUMOR.search(h) and not re.search(r"\b(signed|signs)\b", h, re.I): return "Rumor"
    if CONF.search(h): return "Confirmed"
    return "News"
for lst in (ours, league):
    for i in lst: i["kind"] = kind(i["headline"])
rum = {}
for i in sorted(league + ours, key=lambda x: x["time"], reverse=True):
    if i["kind"] != "Rumor" or not MOVE.search(i["headline"]): continue
    if i["why"] in ("League-wide",) and not re.search(r"\b(sign|trade|release|reunion|deal|contract|visit|workout)\w*", i["headline"], re.I): continue
    r = rum.setdefault(i["player"], {"player": i["player"], "pos": i["pos"], "nfl": i["nfl"], "owner": i["owner"], "why": i["why"], "latest": i["headline"], "link": i.get("link", ""), "source": i.get("source", "RotoWire via ESPN"), "time": i["time"], "sources": 0})
    r["sources"] += 1
rumors = sorted(rum.values(), key=lambda r: (r["why"] not in ("Our player", "On our watch list"), -r["sources"], r["time"]))[:12]
_cur = os.environ.get("LT_CURATED")
if _cur and os.path.exists(os.path.join(_cur, "rumors.json")):  # Sam's curated rumor mill wins; refresh source counts
    cur_r = json.load(open(os.path.join(_cur, "rumors.json")))
    for r in cur_r:
        if r["player"] in rum: r.update({k: rum[r["player"]][k] for k in ("sources", "latest", "link", "source", "time")})
    rumors = cur_r
key = lambda x: x["time"]
ours.sort(key=key, reverse=True); league.sort(key=key, reverse=True)
os.makedirs(f"{out}/news", exist_ok=True); os.makedirs(f"{out}/practice", exist_ok=True)
stamp = datetime.now(timezone.utc).isoformat(timespec="minutes")
json.dump({"updatedAt": stamp, "hours": HRS, "items": ours[:60]}, open(f"{out}/news/ours.json", "w"))
json.dump({"updatedAt": stamp, "hours": HRS, "items": league[:100]}, open(f"{out}/news/league.json", "w"))
json.dump({"updatedAt": stamp, "trending": trending, "sources": health, "insiders": INSIDERS, "rumors": rumors}, open(f"{out}/news/desk.json", "w"))
json.dump({"updatedAt": stamp, "week": wk, "players": practice}, open(f"{out}/practice/current.json", "w"))
print(f"pool {len(pool)} | ours {len(ours)} | league {len(league)} | practice {len(practice)} | sources ok {sum(v=='ok' for v in health.values())}/{len(health)} | trending {len(trending)}")
