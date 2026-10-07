"""Legal Troubles news + practice sweep (Frank). Run: python3 news_sweep.py <out_dir> [hours=72]
Pulls ESPN/Rotowire player news for every fantasy-relevant player (rostered in our league or >=3% owned),
classifies what matters to us, and parses practice participation (DNP / Limited / Full) by day.
Writes dashboard docs: news/ours, news/league, news/desk, practice/current.
Env: LT_TEAM_ID (default 31 = Legal Troubles), LT_CURATED (rumors.json), LT_WATCHLIST.
Fail-loudly rules (Oct 6 org review):
  - every source (each RSS feed, Google News query, Sleeper, ESPN player news) gets a health entry with item counts;
    a fetch error is "error", an empty or all-stale feed is "warning"; nothing is silently []
  - ESPN player news returning 0 items in a game week exits non-zero (outputs are still written)
  - ESPN news items that are not type Rotowire are counted in droppedByType, not silently ignored
  - practice days are in America/New_York and derived from each NFL team's next kickoff (4 days before through the day before)
  - curated rumors past expiresWeek are marked expired:true; auto rumors not reviewed by staff get reviewed:false"""
import json, os, re, sys, urllib.request, concurrent.futures as cf
from collections import Counter
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
LG = 293318; YR = 2026; NY = ZoneInfo("America/New_York")  # not "ET": xml.etree is imported as ET below
TEAM_ID = int(os.environ.get("LT_TEAM_ID", "31"))
B = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{YR}/segments/0/leagues/{LG}"
out = sys.argv[1] if len(sys.argv) > 1 else "news_out"; HRS = int(sys.argv[2]) if len(sys.argv) > 2 else 72
WATCH_FILE = os.environ.get("LT_WATCHLIST") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.json")  # optional: {"names": [...]}
def get(url, hdr=None): return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=hdr or {}), timeout=60))
t = get(f"{B}?view=mTeam&view=mStatus"); names = {x["id"]: x["name"].strip() for x in t["teams"]}
if TEAM_ID not in names: raise SystemExit(f"team id {TEAM_ID} not in league teams {sorted(names)}")
me = TEAM_ID; wk = t["status"]["currentMatchupPeriod"]
pro = get(f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{YR}?view=proTeamSchedules_wl")
ab = {p["id"]: p["abbrev"] for p in pro["settings"]["proTeams"] if p["id"] != 0}
if len(ab) != 32: raise SystemExit(f"expected 32 NFL teams, got {len(ab)}")
def abbr(tid):
    if tid in (0, None): return "FA"
    if tid not in ab: raise KeyError(f"unknown NFL proTeamId {tid}")
    return ab[tid]
# every NFL kickoff per team (ET), for practice-day windows
KICK = {ab[p["id"]]: sorted(datetime.fromtimestamp(x["date"] / 1000, NY) for gl in p.get("proGamesByScoringPeriod", {}).values() for x in gl)
        for p in pro["settings"]["proTeams"] if p["id"] != 0}
GAME_WEEK = any(str(wk) in p.get("proGamesByScoringPeriod", {}) for p in pro["settings"]["proTeams"])
def practice_window(team, ts_et):
    """(kickoff, first_day, last_day) for the team's next game after ts_et: practice days = kickoff date -4 .. -1."""
    nxt = next((k for k in KICK.get(team, []) if k > ts_et), None)
    if not nxt: return None
    return nxt, nxt.date() - timedelta(days=4), nxt.date() - timedelta(days=1)
flt = {"players": {"limit": 900, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
allp = get(f"{B}?scoringPeriodId={wk}&view=kona_player_info", {"X-Fantasy-Filter": json.dumps(flt)})["players"]
watch = set(json.load(open(WATCH_FILE))["names"]) if os.path.exists(WATCH_FILE) else set()
POS = {1:"QB",2:"RB",3:"WR",4:"TE",5:"K",16:"D/ST"}
pool = []
for pe in allp:
    p = pe["player"]; own = pe.get("onTeamId", 0); pct = p.get("ownership", {}).get("percentOwned", 0)
    if POS.get(p["defaultPositionId"]) in (None, "K", "D/ST"): continue
    if own or pct >= 3 or p["fullName"] in watch:
        pool.append({"id": p["id"], "name": p["fullName"], "pos": POS[p["defaultPositionId"]], "nfl": abbr(p.get("proTeamId")),
                     "owner": names.get(own, "Free agent"), "ours": own == me, "watch": p["fullName"] in watch, "status": p.get("injuryStatus") or "ACTIVE", "pct": round(pct)})
our_nfl = {p["nfl"] for p in pool if p["ours"]}
def news(p):
    try: return p, get(f"https://site.api.espn.com/apis/fantasy/v2/games/ffl/news/players?playerId={p['id']}&limit=6").get("feed", []), None
    except Exception as e: return p, [], f"{type(e).__name__}: {str(e)[:60]}"
cut = datetime.now(timezone.utc) - timedelta(hours=HRS)
KEY = re.compile(r"\b(sign|signed|signing|release|released|waive|trade|traded|injured reserve|activated|designated to return|suspen|physical|practice squad|ruled out|out for|week-to-week|season-ending|torn|surgery|concussion|depth chart|starting|starter|benched|demoted|promoted|lead back|bell-cow|reached out|visit|workout|expected to)\w*", re.I)
PRAC = [(re.compile(r"\b(did not practice|didn't practice|not practicing|sat out practice|DNP)\b", re.I), "DNP"),
        (re.compile(r"\b(limited|limited participant|limited basis)\b", re.I), "Limited"),
        (re.compile(r"\b(practiced in full|full participant|full practice|full session|fully participated|practiced fully)\b", re.I), "Full")]
ours, league, practice = [], [], {}
pn = {"players": len(pool), "fetched": 0, "failures": 0, "items": 0, "rotowire": 0, "recent": 0, "droppedByType": Counter(), "errors": Counter()}
with cf.ThreadPoolExecutor(16) as ex:
    for p, feed, err in ex.map(news, pool):
        if err: pn["failures"] += 1; pn["errors"][err[:40]] += 1; continue
        pn["fetched"] += 1; pn["items"] += len(feed)
        for f in feed:
            if f.get("type") != "Rotowire": pn["droppedByType"][f.get("type") or "unknown"] += 1; continue
            pn["rotowire"] += 1
            ts = datetime.fromisoformat(f["published"].replace("Z", "+00:00"))
            if ts < cut - timedelta(days=5): continue
            hl = f["headline"]; low = hl.lower()
            item = {"player": p["name"], "pos": p["pos"], "nfl": p["nfl"], "owner": p["owner"], "time": f["published"][:16] + "Z", "headline": f["headline"]}
            if (p["ours"] or p["watch"]) and ("practic" in low or "session" in low or "participant" in low):
                loc = ts.astimezone(NY); win = practice_window(p["nfl"], loc - timedelta(hours=12))  # a report the night after a game still belongs to that week
                for rx, lab in PRAC:
                    if rx.search(hl) and win and win[1] <= loc.date() <= win[2]:
                        rec = practice.setdefault(p["name"], {"pos": p["pos"], "nfl": p["nfl"], "ours": p["ours"], "days": {}})
                        rec["kickoffET"] = win[0].isoformat(); rec["window"] = [win[1].isoformat(), win[2].isoformat()]
                        rec["days"][loc.strftime("%a %m/%d")] = {"status": lab, "note": hl[:160], "date": loc.date().isoformat()}
                        break
            if ts < cut: continue
            pn["recent"] += 1
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
}
gq = lambda q: "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q + " when:2d", "hl": "en-US", "gl": "US", "ceid": "US:en"})
for n in INSIDERS: FEEDS[f"Google News: {n}"] = gq(f'"{n}" NFL')
for q in ["NFL signs free agent", "NFL waived released", "NFL trade rumors", "NFL injured reserve", "NFL practice squad elevated running back"]: FEEDS[f"Google News: {q}"] = gq(q)
def rss(src_url):
    src, url = src_url
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25).read()
        root = ET.fromstring(raw); out_ = []; bad = 0
        for it in root.iter("item"):
            title = html.unescape((it.findtext("title") or "").strip()); link = it.findtext("link") or ""
            pd = it.findtext("pubDate"); desc = html.unescape(re.sub("<[^>]+>", "", it.findtext("description") or ""))[:300]
            try: ts = email.utils.parsedate_to_datetime(pd).astimezone(timezone.utc)
            except Exception: bad += 1; continue
            out_.append({"src": src, "title": title, "link": link, "ts": ts, "desc": desc})
        if not out_: return [{"src": src, "empty": True, "note": f"{bad} items, none with a readable date" if bad else "feed returned 0 items"}]
        return out_
    except Exception as e:
        return [{"src": src, "error": f"{type(e).__name__}: {str(e)[:80]}"}]
by_name = {}
for p in pool: by_name[p["name"]] = p
by_id = {p["id"]: p for p in pool}
# every rostered player (any position) by ESPN id/name, so trending never calls a rostered player a free agent
by_own = {}
for pe in allp:
    _p = pe["player"]; _o = pe.get("onTeamId", 0)
    if _o:
        rec = {"id": _p["id"], "name": _p["fullName"], "owner": names.get(_o, "Free agent")}; by_id.setdefault(_p["id"], rec); by_own[_p["fullName"]] = rec
last = {}  # last-name index for "Mixon" style headlines
for p in pool:
    ln = p["name"].replace(" Jr.", "").replace(" Sr.", "").replace(" III", "").replace(" II", "").split()[-1]
    if len(ln) > 3: last.setdefault(ln, []).append(p)
TITLE_WORDS = {"Bears","Bengals","Bills","Broncos","Browns","Buccaneers","Bucs","Cardinals","Chargers","Chiefs","Colts","Commanders","Cowboys","Dolphins","Eagles","Falcons","49ers","Niners","Giants","Jaguars","Jags","Jets","Lions","Packers","Panthers","Patriots","Raiders","Rams","Ravens","Saints","Seahawks","Steelers","Texans","Titans","Vikings",
  "Report","Reports","Source","Sources","Rookie","Veteran","Star","Coach","Signing","Signs","Sign","Release","Released","Waived","Activated","Injured","Free","Agent","Former","Ex","Back","Watch","Update","Breaking","Fantasy","Why","How","What","When","Will","Could","Should","Is","Are","Has","Have","With","Without","For","And","But","After","Before","On","In","At","To","As","Of","The","A","An","If","Not","No","Yes","Mr","Week","Sunday","Monday","Thursday","Saturday","Tuesday","Wednesday","Friday"}
desk, seen = [], set()
detail = {}  # source -> {status, items, recent, error?, note?}
with cf.ThreadPoolExecutor(12) as ex:
    for items in ex.map(rss, FEEDS.items()):
        src = items[0]["src"]
        if "error" in items[0]: detail[src] = {"status": "error", "items": 0, "recent": 0, "error": items[0]["error"]}; continue
        if items[0].get("empty"): detail[src] = {"status": "warning", "items": 0, "recent": 0, "note": items[0]["note"]}; continue
        rc = sum(1 for it in items if it["ts"] >= cut)
        detail[src] = {"status": "ok" if rc else "warning", "items": len(items), "recent": rc, **({} if rc else {"note": f"0 items in the last {HRS}h (newest {max(it['ts'] for it in items).isoformat(timespec='minutes')})"})}
        for it in items:
            if it["ts"] < cut: continue
            text = it["title"] + " " + it["desc"]
            hits = [p for n, p in by_name.items() if re.search(rf"(?<![A-Za-z.'-]){re.escape(n)}(?![A-Za-z'-])", text)]
            if not hits:
                for ln, ps in last.items():
                    if len(ps) != 1: continue
                    first = ps[0]["name"].split()[0]
                    for mt in re.finditer(rf"\b{re.escape(ln)}\b", it["title"]):
                        before = re.search(r"([A-Z][A-Za-z.'-]+)\s+$", it["title"][:mt.start()])
                        after = re.match(r"\s+([A-Z][a-z][A-Za-z'-]+)", it["title"][mt.end():])
                        if after and after.group(1) not in ("Jr", "Sr"): continue  # "Tyson Bagent": Tyson is a first name here
                        bw = before.group(1) if before else ""
                        looks_first = bw and bw != first and not bw.isupper() and not bw.endswith(("'s", "'")) and bw.rstrip(".") not in TITLE_WORDS
                        if looks_first: continue  # "Scotty Miller" is not Kendre Miller
                        hits.append(ps[0]); break
            for p in hits[:2]:
                k = (p["name"], it["title"][:60].lower())
                if k in seen: continue
                seen.add(k)
                rel = "Our player" if p["ours"] else "On our watch list" if p["watch"] else f"Affects our {p['nfl']} players" if p["nfl"] in our_nfl else "Free agent" if p["owner"] == "Free agent" else "League-wide"
                if rel in ("League-wide",) and not KEY.search(it["title"]): continue
                if rel == "Free agent" and not KEY.search(it["title"]): continue
                item = {"player": p["name"], "pos": p["pos"], "nfl": p["nfl"], "owner": p["owner"], "time": it["ts"].isoformat(timespec="minutes").replace("+00:00", "Z"), "headline": it["title"], "source": it["src"], "link": it["link"], "why": rel}
                (ours if p["ours"] else league).append(item)
_norm = lambda n: re.sub(r"[^a-z]", "", re.sub(r"\b(jr|sr|ii|iii|iv|v)\.?$", "", n.lower().strip()))
by_norm = {_norm(v["name"]): v for v in list(by_own.values()) + pool}
# Sleeper: what the fantasy world is adding right now (crowd signal)
try:
    tr = json.load(urllib.request.urlopen(urllib.request.Request("https://api.sleeper.app/v1/players/nfl/trending/add?lookback_hours=24&limit=25", headers=UA), timeout=25))
    detail["Sleeper trending"] = {"status": "ok" if tr else "warning", "items": len(tr), "recent": len(tr), **({} if tr else {"note": "0 trending adds"})}
except Exception as e: tr = []; detail["Sleeper trending"] = {"status": "error", "items": 0, "recent": 0, "error": f"{type(e).__name__}: {str(e)[:80]}"}
trending = []
if tr:
    try:
        sp = json.load(urllib.request.urlopen(urllib.request.Request("https://api.sleeper.app/v1/players/nfl", headers=UA), timeout=60))
        for t_ in tr:
            q = sp.get(t_["player_id"], {}); nm = q.get("full_name") or (f'{q.get("team") or t_["player_id"]} D/ST' if q.get("position") == "DEF" or str(t_["player_id"]).isalpha() else "")
            eid = q.get("espn_id"); p = by_id.get(int(eid)) if str(eid or "").isdigit() else None
            p = p or by_name.get(nm) or (by_own.get(nm) if nm else None) or (by_norm.get(_norm(nm)) if nm else None)
            if p: nm = p["name"]
            trending.append({"player": nm, "pos": q.get("position"), "nfl": q.get("team") or "FA", "adds24h": t_["count"], "owner": p["owner"] if p else "Free agent (not in our pool)"})
        detail["Sleeper players"] = {"status": "ok", "items": len(sp), "recent": len(trending)}
    except Exception as e: detail["Sleeper players"] = {"status": "error", "items": 0, "recent": 0, "error": f"{type(e).__name__}: {str(e)[:80]}"}
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
_cur = os.environ.get("LT_CURATED"); rumor_status = {"curated": 0, "auto": 0, "expired": 0, "unreviewed": 0, "legacy": 0}
cur_r = []
if _cur and os.path.exists(os.path.join(_cur, "rumors.json")):  # Sam's curated rumors lead; refresh source counts from today's sweep
    cur_r = json.load(open(os.path.join(_cur, "rumors.json")))
    _fdate = datetime.fromtimestamp(os.path.getmtime(os.path.join(_cur, "rumors.json")), NY).date().isoformat()
    for r in cur_r:
        if r["player"] in rum: r.update({k: rum[r["player"]][k] for k in ("sources", "latest", "link", "source", "time")})
        r["reviewed"] = bool(r.get("action") and r.get("claim") and r.get("impact"))
        if r.get("expiresWeek") is None or not r.get("asOf"):  # old format: current until next week, flagged legacy
            r["legacy"] = True; r["asOf"] = r.get("asOf") or _fdate
            if r.get("expiresWeek") is None: r["expiresWeek"] = wk + 1
        r["expired"] = wk > int(r["expiresWeek"])
        r["origin"] = "curated"
else: rumor_status["error"] = f"no curated rumors.json under LT_CURATED ({_cur})"
have = {r["player"] for r in cur_r}
auto = []
for r in rumors:  # auto rumors merge in after the curated ones; nobody has written why it matters yet
    if r["player"] in have: continue
    auto.append(r | {"origin": "auto", "reviewed": False, "expired": False, "claim": r.get("claim") or "", "impact": r.get("impact") or "", "action": r.get("action") or ""})
rumors = cur_r + auto
rumor_status.update({"curated": len(cur_r), "auto": len(auto), "expired": sum(1 for r in rumors if r.get("expired")), "unreviewed": sum(1 for r in rumors if not r.get("reviewed")), "legacy": sum(1 for r in rumors if r.get("legacy"))})
key = lambda x: x["time"]
ours.sort(key=key, reverse=True); league.sort(key=key, reverse=True)
os.makedirs(f"{out}/news", exist_ok=True); os.makedirs(f"{out}/practice", exist_ok=True)
stamp = datetime.now(timezone.utc).isoformat(timespec="minutes")
# ESPN player news health: 0 items in a game week is a failure, not "nothing new"
pn_status = "ok"; pn_note = None
if pn["fetched"] == 0: pn_status, pn_note = "error", f"all {pn['players']} player-news fetches failed"
elif pn["rotowire"] == 0: pn_status, pn_note = ("error" if GAME_WEEK else "warning"), f"0 Rotowire items from {pn['fetched']} players"
elif pn["failures"]: pn_status, pn_note = "warning", f"{pn['failures']} of {pn['players']} fetches failed"
detail["ESPN player news"] = {"status": pn_status, "items": pn["rotowire"], "recent": pn["recent"], "players": pn["players"], "fetched": pn["fetched"], "failures": pn["failures"],
                              "droppedByType": dict(pn["droppedByType"]), **({"note": pn_note} if pn_note else {}), **({"errors": dict(pn["errors"])} if pn["errors"] else {})}
health = {k: v["status"] if v["status"] == "ok" else f'{v["status"]}: {v.get("error") or v.get("note", "")}' for k, v in detail.items()}  # legacy string map
counts = {s: sum(1 for v in detail.values() if v["status"] == s) for s in ("ok", "warning", "error")}
health_line = f"sources {counts['ok']} ok / {counts['warning']} warning / {counts['error']} error of {len(detail)} | ESPN player news {pn['rotowire']} items ({pn['recent']} recent), {pn['failures']} failed fetches, dropped {dict(pn['droppedByType'])}"
fatal = []
if detail["ESPN player news"]["status"] == "error": fatal.append("ESPN player news: " + (pn_note or "error"))
if counts["ok"] == 0: fatal.append("no news source returned recent items")
json.dump({"updatedAt": stamp, "hours": HRS, "items": ours[:60]}, open(f"{out}/news/ours.json", "w"))
json.dump({"updatedAt": stamp, "hours": HRS, "items": league[:100]}, open(f"{out}/news/league.json", "w"))
json.dump({"updatedAt": stamp, "week": wk, "trending": trending, "sources": health, "health": detail, "healthLine": health_line, "counts": counts, "insiders": INSIDERS,
           "rumors": rumors, "rumorStatus": rumor_status, "errors": fatal}, open(f"{out}/news/desk.json", "w"))
json.dump({"updatedAt": stamp, "week": wk, "tz": "America/New_York", "players": practice}, open(f"{out}/practice/current.json", "w"))
print(f"pool {len(pool)} | ours {len(ours)} | league {len(league)} | practice {len(practice)} | trending {len(trending)} | rumors {len(cur_r)} curated + {len(auto)} auto")
print("health:", health_line)
for k, v in detail.items():
    if v["status"] != "ok": print(f"  {v['status'].upper()} {k}: {v.get('error') or v.get('note')}", file=sys.stderr)
if fatal: print("FAILED: " + "; ".join(fatal), file=sys.stderr); sys.exit(2)
