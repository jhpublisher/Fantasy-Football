"""Legal Troubles news + practice sweep (Sam owns news, Frank practice; Rich owns the code). Run: python3 news_sweep.py <out_dir> [hours=72]
Pulls ESPN/Rotowire player news for every fantasy-relevant player (rostered in our league or >=3% owned) + the watch list,
the multi-source desk (RSS, Google News insider/transaction searches, Sleeper trending), classifies what matters to us,
and parses practice participation (DNP / Limited / Full) by day.
Writes dashboard docs: news/ours, news/league, news/desk, practice/current.
Env: LT_TEAM_ID (default 31 = Legal Troubles), LT_CURATED (rumors.json, required; watchlist.json fallback), LT_WATCHLIST.
Fail-loudly rules (Oct 6 org review; Oct 7 roadmap items 2-5):
  - no swallowed errors: every source (each RSS feed, Google News query, Sleeper, ESPN player news, ESPN teams) gets a health
    entry with item counts, unreadable dates (badDates) and future-dated items; a fetch error is "error", an empty or all-stale
    feed is "warning"; nothing is silently []
  - quality gates (exit 2, outputs still written): ESPN player news 0 items in a game week; no news source with recent items;
    missing curated rumors.json or watch list; empty player pool; Sleeper player map unavailable (the matcher needs it)
  - dead Rotoworld feed removed (Oct 6)
News matcher (Oct 7):
  - ESPN player news is fetched by ESPN id (exact). Text sources (RSS, Google News) are matched against the full NFL player
    list from Sleeper (espn_id links to ESPN ids): a full-name mention of a different NFL player (Tyson Bagent, Scotty Miller)
    blocks a last-name match; a last-name-only match needs the last name to be unique among active NFL players at fantasy
    positions, or team context (city / nickname / abbreviation of the player's team) in the same item
  - names are normalized (accents, punctuation, Jr./Sr./II/III/IV/V): "Marvin Harrison" = "Marvin Harrison Jr."
  - story grouping: near-duplicate items about the same player within 48h are one story with a source count, the source that
    broke it first, and up to 5 other links (stops one signing flooding the feed)
  - real date parsing with time zones: RFC 822 incl. RotoWire's 12-hour "7:56:00 AM PDT" form, US zone names, ISO 8601
    (email.utils dropped AM/PM and the zone: a 4:18 PM PDT item read as 04:18 UTC, 19 hours early)
Curated freshness: curated rumors carry asOf/expiresWeek (expired:true past it; legacy entries current until next week);
  curated + automatic rumors are merged (curated first, auto with reviewed:false); a curated rumor with a newer Confirmed
  report gets needsReview:true + newerConfirmed so Sam re-checks it.
Practice grid: current game only: a report is kept only if it belongs to the team's next game from now (12h grace) AND that game
  is in the current fantasy week (each record carries the NFL week); byes get none; days in America/New_York;
  window = day after the team's previous game (at most 6 days before kickoff) through the day before kickoff, Mon-Sat;
  a report naming several days ("didn't practice Wednesday or Thursday", "limited Wednesday, full Thursday") fills each day."""
import json, os, re, sys, unicodedata, urllib.request, concurrent.futures as cf
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
LG = 293318; YR = 2026; NY = ZoneInfo("America/New_York")  # not "ET": xml.etree is imported as ET below
TEAM_ID = int(os.environ.get("LT_TEAM_ID", "31"))
B = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{YR}/segments/0/leagues/{LG}"
out = sys.argv[1] if len(sys.argv) > 1 else "news_out"; HRS = int(sys.argv[2]) if len(sys.argv) > 2 else 72
_cur = os.environ.get("LT_CURATED")
WATCH_FILE = os.environ.get("LT_WATCHLIST") or next((f for f in (os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.json"),
                                                                 os.path.join(_cur or "", "watchlist.json")) if os.path.exists(f)), None)
UA = {"User-Agent": "Mozilla/5.0 (LegalTroubles NewsDesk)"}
NOW = datetime.now(timezone.utc)
fatal = []
def get(url, hdr=None, timeout=60): return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=hdr or {}), timeout=timeout))
# ---------- dates: real parsing with time zones ----------
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
TZABBR = {"UT": 0, "UTC": 0, "GMT": 0, "Z": 0}
# US zone labels are read as that region's local wall time: ESPN's RSS labels Eastern daylight times "EST" (Quinn, Oct 7),
# so "EST"/"EDT" both mean America/New_York local time, whichever offset applies on that date
TZREGION = {"EST": "America/New_York", "EDT": "America/New_York", "ET": "America/New_York", "CST": "America/Chicago", "CDT": "America/Chicago",
            "MST": "America/Denver", "MDT": "America/Denver", "PST": "America/Los_Angeles", "PDT": "America/Los_Angeles", "PT": "America/Los_Angeles"}
FUTURE_SLACK = timedelta(minutes=10)
def parse_date(s, default_tz=timezone.utc):
    """RFC 822 (also 12-hour 'AM/PM' and US zone names), or ISO 8601. Naive times use default_tz. Raises if unreadable."""
    s = (s or "").strip()
    if not s: raise ValueError("empty date")
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=default_tz)).astimezone(timezone.utc)
    except ValueError: pass
    m = re.match(r"^(?:[A-Za-z]{3},?\s*)?(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp][Mm])?\s*([A-Za-z]{1,4}|[+-]\d{4})?$", s)
    if not m: raise ValueError(f"unreadable date {s!r}")
    day, mon, yr, hh, mi, ss, ampm, tz = m.groups(); hh = int(hh)
    if ampm: hh = hh % 12 + (12 if ampm.upper() == "PM" else 0)
    if mon[:3].title() not in MONTHS: raise ValueError(f"unknown month in {s!r}")
    if tz is None: tzi = default_tz
    elif tz[0] in "+-": tzi = timezone((1 if tz[0] == "+" else -1) * timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5])))
    elif tz.upper() in TZREGION: tzi = ZoneInfo(TZREGION[tz.upper()])
    elif tz.upper() in TZABBR: tzi = timezone(timedelta(hours=TZABBR[tz.upper()]))
    else: raise ValueError(f"unknown time zone {tz!r} in {s!r}")
    return datetime(int(yr), MONTHS.index(mon[:3].title()) + 1, int(day), hh, int(mi), int(ss or 0), tzinfo=tzi).astimezone(timezone.utc)
def iso(ts): return ts.astimezone(timezone.utc).isoformat(timespec="minutes").replace("+00:00", "Z")
# ---------- names ----------
SUFFIX = re.compile(r"\s+(jr|sr|ii|iii|iv|v)\.?$", re.I)
def norm(n):
    n = re.sub(r"['\u2019]s\b", "", n or "")  # possessive: "Jackson's" / "Jackson\u2019s" = Jackson
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
    n = SUFFIX.sub("", n.strip()); n = re.sub(r"[^A-Za-z ]", "", n.replace("-", " "))
    return re.sub(r"\s+", " ", n).strip().lower()
# ---------- league + NFL ----------
t = get(f"{B}?view=mTeam&view=mStatus"); names = {x["id"]: x["name"].strip() for x in t["teams"]}
if TEAM_ID not in names: raise SystemExit(f"team id {TEAM_ID} not in league teams {sorted(names)}")
me = TEAM_ID; wk = t["status"]["currentMatchupPeriod"]
pro = get(f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/{'ffl'}/seasons/{YR}?view=proTeamSchedules_wl")
ab = {p["id"]: p["abbrev"].upper() for p in pro["settings"]["proTeams"] if p["id"] != 0}
if len(ab) != 32: raise SystemExit(f"expected 32 NFL teams, got {len(ab)}")
def abbr(tid):
    if tid in (0, None): return "FA"
    if tid not in ab: raise KeyError(f"unknown NFL proTeamId {tid}")
    return ab[tid]
ALIAS = {"WSH": "WAS", "WAS": "WSH", "JAX": "JAC", "JAC": "JAX", "LAR": "LA", "LA": "LAR"}
# every NFL kickoff per team (ET) with its NFL week, for practice windows
GAMES = {ab[p["id"]]: sorted((datetime.fromtimestamp(x["date"] / 1000, NY), int(w)) for w, gl in p.get("proGamesByScoringPeriod", {}).items() for x in gl)
         for p in pro["settings"]["proTeams"] if p["id"] != 0}
GAME_WEEK = any(str(wk) in p.get("proGamesByScoringPeriod", {}) for p in pro["settings"]["proTeams"])
def practice_window(team, ts_et):
    """(kickoff, nfl_week, first_day, last_day) of the team's next game after ts_et. Practice days run from the day after
    its previous game (at most 6 days before kickoff) through the day before kickoff; Sundays are dropped later (Mon-Sat)."""
    gl = GAMES.get(team, [])
    i = next((j for j, (k, _) in enumerate(gl) if k > ts_et), None)
    if i is None: return None
    ko, w = gl[i]; first = ko.date() - timedelta(days=6)
    if i > 0: first = max(first, gl[i - 1][0].date() + timedelta(days=1))
    return ko, w, first, ko.date() - timedelta(days=1)
# this week's practice window per team = the team's next game from now (12h grace so a game-night run keeps that game); bye/no game -> none
CUR_WIN = {t: practice_window(t, datetime.now(NY) - timedelta(hours=12)) for t in GAMES}
health = {}  # source -> {status, items, recent, ...}
try:
    _teams = get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams")["sports"][0]["leagues"][0]["teams"]
    TEAMCTX = {}
    for x in _teams:
        tm = x["team"]; a = tm["abbreviation"].upper()
        words = {tm.get("location", ""), tm.get("name", ""), tm.get("shortDisplayName", ""), tm.get("displayName", ""), a}
        TEAMCTX[a] = TEAMCTX[ALIAS.get(a, a)] = [w for w in words if w]
    health["ESPN teams"] = {"status": "ok" if len(_teams) == 32 else "error", "items": len(_teams), "recent": len(_teams), **({} if len(_teams) == 32 else {"error": f"{len(_teams)} teams, expected 32"})}
    if len(_teams) != 32: fatal.append("ESPN teams list incomplete (team context for name matching)")
except Exception as e:
    TEAMCTX = {}; health["ESPN teams"] = {"status": "error", "items": 0, "recent": 0, "error": f"{type(e).__name__}: {str(e)[:80]}"}
    fatal.append("ESPN teams list unavailable (team context for name matching)")
flt = {"players": {"limit": 900, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
allp = get(f"{B}?scoringPeriodId={wk}&view=kona_player_info", {"X-Fantasy-Filter": json.dumps(flt)})["players"]
if WATCH_FILE: watch = set(json.load(open(WATCH_FILE))["names"])
else: watch = set(); fatal.append("watch list missing (LT_WATCHLIST, tools/watchlist.json or LT_CURATED/watchlist.json)")
health["Watch list"] = {"status": "ok" if watch else "error", "items": len(watch), "recent": len(watch), **({"file": WATCH_FILE} if WATCH_FILE else {"error": "no watch list file"})}
POS = {1:"QB",2:"RB",3:"WR",4:"TE",5:"K",16:"D/ST"}
pool = []
for pe in allp:
    p = pe["player"]; own = pe.get("onTeamId", 0); pct = p.get("ownership", {}).get("percentOwned", 0)
    if POS.get(p["defaultPositionId"]) in (None, "K", "D/ST"): continue
    if own or pct >= 3 or p["fullName"] in watch:
        pool.append({"id": p["id"], "name": p["fullName"], "pos": POS[p["defaultPositionId"]], "nfl": abbr(p.get("proTeamId")),
                     "owner": names.get(own, "Free agent"), "ours": own == me, "watch": p["fullName"] in watch, "status": p.get("injuryStatus") or "ACTIVE", "pct": round(pct)})
if not pool: fatal.append("player pool empty (ESPN kona_player_info returned no fantasy-relevant players)")
missing_watch = sorted(watch - {p["name"] for p in pool})
our_nfl = {p["nfl"] for p in pool if p["ours"]}
# ---------- ESPN player news (by ESPN id) + practice ----------
def news(p):
    err = None
    for _ in range(3):  # transient ESPN errors: retry twice, then count the failure (never silent)
        try: return p, get(f"https://site.api.espn.com/apis/fantasy/v2/games/ffl/news/players?playerId={p['id']}&limit=6").get("feed", []), None
        except Exception as e: err = f"{type(e).__name__}: {str(e)[:60]}"
    return p, [], err
cut = NOW - timedelta(hours=HRS)
KEY = re.compile(r"\b(sign|signed|signing|release|released|waive|trade|traded|injured reserve|activated|designated to return|suspen|physical|practice squad|ruled out|out for|week-to-week|season-ending|torn|surgery|concussion|depth chart|starting|starter|benched|demoted|promoted|lead back|bell-cow|reached out|visit|workout|expected to)\w*", re.I)
PRAC = [(re.compile(r"\b(did not practice|didn't practice|did not participate|didn't participate|not practicing|sat out (?:of )?practice|held out of practice|missed practice|absent from practice|DNP)\b", re.I), "DNP"),
        (re.compile(r"\b(limited|limited participant|limited basis)\b", re.I), "Limited"),
        (re.compile(r"\b(practiced in full|full participant|full practice|full session|fully participated|practiced fully|full participation|without limitations|full go|full(?=\s+(?:on\s+)?(?:mon|tues|wednes|thurs|fri|satur)day)|(?:was|were|been|as) (?:a )?full)\b", re.I), "Full")]
PRACWORD = re.compile(r"practic|session|participa|\bDNP\b|walkthrough", re.I)
INTENT = re.compile(r"\b(aim|aiming|expect|expected|expects|hope|hopes|hoping|plan|plans|planning|should|could|would|will|won't|might|may|likely|projected|anticipat|scheduled|set to|on track)\w*", re.I)  # plans are not reports
PRSTAT = Counter()
DAYN = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
DAYRX = re.compile(r"\b(mon|tues|wednes|thurs|fri|satur|sun)day\b", re.I)
def strip_html(s): return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()
def practice_entries(text, posted_et, win, last=None):
    """[(date, status, clause)] for each practice day the text reports. Days named in a clause map to the latest such
    weekday on or before the posting date; a clause with a status but no day = the posting day (before 10 AM ET: the day before)."""
    out_ = []
    for cl in re.split(r"[.;]|\bbut\b|\bwhile\b|\bafter\b|,\s*(?=[a-z]*\s*(?:full|limited|did|didn't|was|is|sat|practiced)\b)", text):
        st = next((lab for rx, lab in PRAC if rx.search(cl)), None)
        if not st: continue
        if INTENT.search(cl): PRSTAT["skippedIntent"] += 1; continue
        if last and not re.search(rf"\b{re.escape(last)}\b|\b(he|his)\b", cl, re.I) and re.search(r"\b[A-Z][a-z]+ [A-Z][a-z'\-]+\b", cl):
            PRSTAT["otherPlayer"] += 1; continue  # "Tee Higgins (groin) was limited" inside Ja'Marr Chase's note
        days = [DAYN[m.group(0).lower()] for m in DAYRX.finditer(cl)]
        if days:
            ds = []
            for dw in days:
                back = (posted_et.weekday() - dw) % 7
                ds.append(posted_et.date() - timedelta(days=back))
        elif PRACWORD.search(cl) or st != "Limited":
            ds = [posted_et.date() - timedelta(days=1 if posted_et.hour < 10 else 0)]
        else: continue
        for d in ds:
            if win[2] <= d <= win[3] and d.weekday() <= 5: out_.append((d, st, cl.strip()[:160]))
            else: PRSTAT["outsideWindow"] += 1
    return out_
ours, league, practice = [], [], {}
pn = {"players": len(pool), "fetched": 0, "failures": 0, "items": 0, "rotowire": 0, "recent": 0, "badDates": 0, "futureDates": 0, "droppedByType": Counter(), "errors": Counter()}
with cf.ThreadPoolExecutor(16) as ex:
    for p, feed, err in ex.map(news, pool):
        if err: pn["failures"] += 1; pn["errors"][err[:40]] += 1; continue
        pn["fetched"] += 1; pn["items"] += len(feed)
        for f in feed:
            if f.get("type") != "Rotowire": pn["droppedByType"][f.get("type") or "unknown"] += 1; continue
            pn["rotowire"] += 1
            try: ts = parse_date(f.get("published"))
            except ValueError: pn["badDates"] += 1; continue
            if ts > NOW + FUTURE_SLACK: pn["futureDates"] += 1; continue
            if ts < cut - timedelta(days=5): continue
            hl = f["headline"]; low = hl.lower(); body = strip_html(f.get("story"))
            item = {"player": p["name"], "pos": p["pos"], "nfl": p["nfl"], "owner": p["owner"], "time": iso(ts), "headline": hl, "playerId": p["id"], "source": "RotoWire via ESPN"}
            text = hl + " " + body
            if (p["ours"] or p["watch"]) and PRACWORD.search(text):
                loc = ts.astimezone(NY); win = practice_window(p["nfl"], loc - timedelta(hours=12))  # a report the night after a game still belongs to that week
                cur = CUR_WIN.get(p["nfl"])  # only this week's game: last week's reports never carry over (Joe, Oct 7)
                PRSTAT["candidates"] += 1
                ok_ = bool(win and cur and win[0] == cur[0] and win[1] == wk)
                if not ok_: PRSTAT["otherWeek"] += 1
                if ok_:
                    for d, st, cl in practice_entries(text, loc, win, norm(p["name"]).split(" ")[-1]):
                        rec = practice.setdefault(p["name"], {"pos": p["pos"], "nfl": p["nfl"], "ours": p["ours"], "watch": p["watch"], "days": {}})
                        rec["kickoffET"] = win[0].isoformat(); rec["week"] = win[1]; rec["window"] = [win[2].isoformat(), win[3].isoformat()]
                        lab = d.strftime("%a %m/%d"); prev = rec["days"].get(lab); PRSTAT["entries"] += 1
                        if not prev or prev["reportedAt"] < iso(ts):  # newest report for that day wins
                            rec["days"][lab] = {"status": st, "note": cl, "date": d.isoformat(), "reportedAt": iso(ts), "source": "RotoWire via ESPN"}
            if ts < cut: continue
            pn["recent"] += 1
            if p["ours"]: ours.append(item | {"why": "Our player"}); continue
            why = None
            if p["watch"]: why = "On our watch list"
            elif p["nfl"] in our_nfl and KEY.search(hl): why = f"Affects our {p['nfl']} players"
            elif p["owner"] == "Free agent" and KEY.search(hl): why = "Free agent with a role change"
            elif KEY.search(hl) and p["pct"] >= 50: why = "Major news, league-wide"
            if why: league.append(item | {"why": why})
# ---------- Sleeper: full NFL player list (ID links + name matching) and trending adds ----------
import xml.etree.ElementTree as ET, html, urllib.parse, urllib.error
try:
    SP = get("https://api.sleeper.app/v1/players/nfl", UA, timeout=90)
    health["Sleeper players"] = {"status": "ok" if len(SP) > 1000 else "error", "items": len(SP), "recent": 0, **({} if len(SP) > 1000 else {"error": f"only {len(SP)} players"})}
except Exception as e:
    SP = {}; health["Sleeper players"] = {"status": "error", "items": 0, "recent": 0, "error": f"{type(e).__name__}: {str(e)[:80]}"}
if not SP: fatal.append("Sleeper player map unavailable: name matching would fall back to guessing")
FANTASY = {"QB", "RB", "WR", "TE", "K", "FB"}
nfl_full = defaultdict(list); nfl_last = defaultdict(list)  # normalized full / last name -> active NFL players (any position)
all_full = {norm(q["full_name"]) for q in SP.values() if q.get("full_name")}  # everyone Sleeper knows, with or without a team
first_names = {norm(q["first_name"]) for q in SP.values() if q.get("first_name")}  # "Allen Iverson": a surname that is also a first name
for sid, q in SP.items():
    if not q.get("team") or not q.get("full_name"): continue
    rec_ = {"sid": sid, "espn": int(q["espn_id"]) if str(q.get("espn_id") or "").isdigit() else None, "team": q["team"].upper(), "pos": q.get("position"), "name": q["full_name"]}
    nfl_full[norm(q["full_name"])].append(rec_)
    if q.get("position") in FANTASY: nfl_last[norm(q["full_name"]).split(" ")[-1]].append(rec_)
by_id = {p["id"]: p for p in pool}
by_norm = defaultdict(list)
for p in pool: by_norm[norm(p["name"])].append(p)
# every rostered player (any position) by ESPN id/name, so trending never calls a rostered player a free agent
by_own = {}
for pe in allp:
    _p = pe["player"]; _o = pe.get("onTeamId", 0)
    if _o:
        rec = {"id": _p["id"], "name": _p["fullName"], "owner": names.get(_o, "Free agent")}; by_id.setdefault(_p["id"], rec); by_own[norm(_p["fullName"])] = rec
def team_ctx(p, text):
    ws = TEAMCTX.get(p["nfl"], []) or TEAMCTX.get(ALIAS.get(p["nfl"], ""), [])
    return any(re.search(rf"(?<![A-Za-z]){re.escape(w)}(?![A-Za-z])", text) for w in ws)
CAPWORD = r"[A-Z][A-Za-z.'\-]+"
# capitalized words that can sit in front of a surname without being a first name ("Bills RB Cook", "Report: Mixon")
NONFIRST = {"Bears","Bengals","Bills","Broncos","Browns","Buccaneers","Bucs","Cardinals","Chargers","Chiefs","Colts","Commanders","Cowboys","Dolphins","Eagles","Falcons","49ers","Niners","Giants","Jaguars","Jags","Jets","Lions","Packers","Panthers","Patriots","Raiders","Rams","Ravens","Saints","Seahawks","Steelers","Texans","Titans","Vikings",
  "Report","Reports","Source","Sources","Rookie","Veteran","Star","Coach","Signing","Signs","Sign","Release","Released","Waived","Waive","Activated","Injured","Free","Agent","Former","Ex","Back","Watch","Update","Breaking","Fantasy","Why","How","What","When","Will","Could","Should","Is","Are","Has","Have","With","Without","For","And","But","After","Before","On","In","At","To","As","Of","The","A","An","If","Not","No","Yes","Mr","Week","Sunday","Monday","Thursday","Saturday","Tuesday","Wednesday","Friday","NFL","Per","Sources:","Report:","Did","Does","Do","Can","Lead","Trade","Traded","Sit","Start","Stash","Add","Drop","Buy","Sell","Hold","Ruled","Out","Questionable","Doubtful","Limited","Full","Practice","Expect","Expected","Expect:","Fantasy:","Update:"}
SUFFIXW = re.compile(r"^\s*(Jr|Sr|II|III|IV|V)\b\.?")
# surnames that are also common words or places ("in London", "Boston Herald", "Likely Out"): need team context in the item
COMMONSUR = {"london","boston","likely","love","price","hill","brown","white","green","king","young","washington","houston","denver","dallas","miami","jackson","carter","hunt","rice","worthy","moore","bell","hall","waters","person","cook","banks","golden","sterling","winter","summer","may","march","august","rich","strong","long","little","small","street","case","booth","wilson","phillips","pierce","coleman","mason","diggs","reed","house","field","hurts","parks","ford","lincoln","cleveland","charlotte","tennessee","jordan","chase","walker"}
def match_players(title, desc):
    """Pool players an item is about. Full names first (normalized, Jr./Sr. tolerant, same-name players need team
    context); then last-name-only mentions in the title that no other NFL player's full name explains."""
    text = f"{title} {desc}"; ntext = " " + norm(text) + " "
    hits = []; blocked_spans = []
    for nn, ps in by_norm.items():
        if f" {nn} " not in ntext: continue
        same = nfl_full.get(nn, [])
        for p in ps:
            if len(same) > 1 and not team_ctx(p, text): continue  # two NFL players share the name: need the team
            hits.append(p)
    # spans in the title covered by any player's full name in Sleeper's list, with or without a team (Gabe Davis)
    ws = list(re.finditer(CAPWORD, title))  # every adjacent capitalized pair (overlapping: "Coach Scotty Miller")
    for a, b_ in zip(ws, ws[1:]):
        if title[a.end():b_.start()].strip(): continue
        if norm(title[a.start():b_.end()]) in all_full: blocked_spans.append((a.start(), b_.end(), norm(title[a.start():b_.end()])))
    if hits: return hits
    for p in pool:
        nn = norm(p["name"]); ln = nn.split(" ")[-1]
        if len(ln) < 4: continue
        for mt in re.finditer(rf"(?<![A-Za-z]){re.escape(ln)}(?![A-Za-z])", title, re.I):
            if not title[mt.start()].isupper(): continue
            covering = [s for s in blocked_spans if s[0] <= mt.start() < s[1] and s[2] != nn]
            if covering: continue  # "Tyson Bagent", "Scotty Miller", "Gabe Davis": another player's full name
            before = re.search(r"([A-Za-z][A-Za-z.'\-]*)\s+$", title[:mt.start()]); bw = before.group(1) if before else ""
            first = nn.split(" ")[0]
            if bw and bw[0].isupper() and not bw.isupper() and not bw.endswith(("'s", "'")) and bw.rstrip(".:") not in NONFIRST and norm(bw) != first:
                continue  # "Kay Adams", "Scotty Miller": a different first name in front
            after = re.match(r"\s+([A-Z][a-z][A-Za-z'\-]+)", title[mt.end():])
            if after and ln in first_names and after.group(1) not in NONFIRST and not SUFFIXW.match(title[mt.end():]): continue  # "Allen Iverson", "Tyson Bagent"
            suf = SUFFIXW.match(title[mt.end():])
            if suf and not re.search(rf"\b{suf.group(1)}\b", p["name"]): continue  # "Washington Jr." is not Malik Washington
            if ln in COMMONSUR and not team_ctx(p, text): continue  # "in London", "Boston Herald", "Likely Out"
            others = [q for q in nfl_last.get(ln, []) if q["espn"] != p["id"] and norm(q["name"]) != nn]
            if others and not team_ctx(p, text): continue  # last name shared by another active NFL player: need team context
            hits.append(p); break
    return hits
if os.environ.get("LT_SELFTEST"):  # matcher / date / practice regression checks (Oct 6 false positives), live player lists
    pn_ = {p["name"] for p in pool}
    def names_(t_, d_=""): return [p["name"] for p in match_players(t_, d_)]
    chk = []
    if "Jordyn Tyson" in pn_: chk.append(("Bears QB Tyson Bagent to start Sunday", "Jordyn Tyson", False))
    if "Kendre Miller" in pn_: chk.append(("Coach says Scotty Miller will return kicks", "Kendre Miller", False))
    if "Marvin Harrison Jr." in pn_: chk.append(("Cardinals' Marvin Harrison expected to play", "Marvin Harrison Jr.", True))
    if "Bryce Young" in pn_: chk.append(("Panthers bench Bryce Young for Week 5", "Bryce Young", True))
    if "Joe Mixon" in pn_: chk.append(("Seahawks decide not to sign Mixon after physical", "Joe Mixon", True))
    for t_, who in [("Dolphins waive Washington Jr.", "Malik Washington"), ("NFL Week 5 picks, odds: Jaguars bludgeon Eagles in London, Colts get exposed", "Drake London"),
                    ("Patriots notes – Boston Herald", "Denzel Boston"), ("Vikings G Donovan Jackson Suffered Torn Meniscus, Likely Out", "Isaiah Likely"),
                    ("NFL sportscaster Kay Adams reacts to Week 4", "Davante Adams"), ("Why Gabe Davis is Still a Free Agent", "Ray Davis")]:
        if who in pn_: chk.append((t_, who, False))
    if "Davante Adams" in pn_: chk.append(("Rams WR Adams questionable for Week 5", "Davante Adams", True))
    if "Josh Allen" in pn_: chk.append(("Kevin Byard: Mike Vrabel used Allen Iverson video to get Patriots going", "Josh Allen", False))
    for t_, who in [("Josh Allen's big day carries Bills", "Josh Allen"), ("Ian Rapoport on Lamar Jackson\u2019s injury ahead of Falcons game - Yardbarker", "Lamar Jackson"),
                    ("Tyreek Hill\u2019s Agent Drew Rosenhaus Reveals Timeline", "Tyreek Hill"), ("Seahawks RB Charbonnet Practices Fully, Nears Return", "Zach Charbonnet"),
                    ("Giants TE Likely Returns To Practice", "Isaiah Likely")]:
        if who in pn_: chk.append((t_, who, True))
    for t_, who, want in chk:
        got = who in names_(t_); print(("ok  " if got == want else "FAIL"), f"{t_!r} -> {names_(t_)} (want {who} {'in' if want else 'out'})")
    for s_, want in [("Wed, 07 Oct 2026 7:56:00 AM PDT", "2026-10-07T14:56Z"), ("Tue, 06 Oct 2026 4:18:00 PM PDT", "2026-10-06T23:18Z"),
                     ("Tue, 06 Oct 2026 18:07:00 GMT", "2026-10-06T18:07Z"), ("Mon, 05 Oct 2026 22:36:00 +0000", "2026-10-05T22:36Z"), ("2026-10-07T12:22:00Z", "2026-10-07T12:22Z"), ("Wed, 7 Oct 2026 11:10:20 EST", "2026-10-07T15:10Z"), ("Wed, 07 Jan 2026 11:10:20 EST", "2026-01-07T16:10Z")]:
        print("ok  " if iso(parse_date(s_)) == want else "FAIL", s_, "->", iso(parse_date(s_)))
    _w = (datetime(2026, 10, 11, 13, 0, tzinfo=NY), 5, datetime(2026, 10, 5).date(), datetime(2026, 10, 10).date())
    for txt, at, want in [("Smith didn't practice Wednesday or Thursday.", datetime(2026, 10, 8, 17, tzinfo=NY), {"Wed 10/07": "DNP", "Thu 10/08": "DNP"}),
                          ("Smith was limited Wednesday, full Thursday.", datetime(2026, 10, 8, 17, tzinfo=NY), {"Wed 10/07": "Limited", "Thu 10/08": "Full"}),
                          ("Smith did not practice.", datetime(2026, 10, 9, 8, tzinfo=NY), {"Thu 10/08": "DNP"}),
                          ("Coach said Monday they are aiming for a full practice week.", datetime(2026, 10, 5, 18, tzinfo=NY), {}),
                          ("Chase remains in the league's concussion protocol Wednesday. It's also notable that Tee Higgins (groin) was limited in Wednesday's practice.", datetime(2026, 10, 7, 17, tzinfo=NY), {}),
                          ("Chase (concussion) was limited in Wednesday's practice.", datetime(2026, 10, 7, 17, tzinfo=NY), {"Wed 10/07": "Limited"})]:
        got = {d.strftime("%a %m/%d"): st for d, st, _ in practice_entries(txt, at, _w, "chase")}
        print("ok  " if got == want else "FAIL", repr(txt), got)
    sys.exit(0)
# ---------- multi-source desk: RSS + Google News insider search ----------
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
        for i_ in range(3):  # Google News answers 503 to some parallel queries: back off and retry before calling it an error
            try: raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25).read(); break
            except urllib.error.HTTPError as e_:
                if e_.code not in (429, 503) or i_ == 2: raise
                import time; time.sleep(2 + 3 * i_)
        root = ET.fromstring(raw); out_ = []; bad = []; fut = 0
        for it in root.iter("item"):
            title = re.sub(r"\s+", " ", html.unescape(it.findtext("title") or "")).strip(); link = (it.findtext("link") or "").strip()
            pd = it.findtext("pubDate"); desc = html.unescape(re.sub("<[^>]+>", "", it.findtext("description") or ""))[:300]
            try: ts = parse_date(pd)
            except ValueError as e: bad.append(str(e)[:60]); continue
            if ts > NOW + FUTURE_SLACK: fut += 1; continue
            out_.append({"src": src, "title": title, "link": link, "ts": ts, "desc": desc})
        meta_ = {"badDates": len(bad), "badDateExample": bad[0] if bad else None, "futureDates": fut}
        if not out_: return [{"src": src, "empty": True, "note": f"{len(bad)} items, none with a readable date ({bad[0] if bad else ''})" if bad else "feed returned 0 items", **meta_}]
        out_[0]["_meta"] = meta_
        return out_
    except Exception as e:
        return [{"src": src, "error": f"{type(e).__name__}: {str(e)[:80]}"}]
desk_items = []
with cf.ThreadPoolExecutor(12) as ex:
    for items in ex.map(rss, FEEDS.items()):
        src = items[0]["src"]
        if "error" in items[0]: health[src] = {"status": "error", "items": 0, "recent": 0, "error": items[0]["error"]}; continue
        if items[0].get("empty"): health[src] = {"status": "warning", "items": 0, "recent": 0, "note": items[0]["note"], "badDates": items[0]["badDates"]}; continue
        meta_ = items[0].pop("_meta"); rc = sum(1 for it in items if it["ts"] >= cut)
        notes = []
        if not rc: notes.append(f"0 items in the last {HRS}h (newest {max(it['ts'] for it in items).isoformat(timespec='minutes')})")
        if meta_["badDates"]: notes.append(f"{meta_['badDates']} items with unreadable dates (e.g. {meta_['badDateExample']})")
        if meta_["futureDates"]: notes.append(f"{meta_['futureDates']} items dated in the future (time-zone error at the source)")
        health[src] = {"status": "ok" if rc and not notes else "warning", "items": len(items), "recent": rc, "badDates": meta_["badDates"], "futureDates": meta_["futureDates"], **({"note": "; ".join(notes)} if notes else {})}
        desk_items += [it for it in items if it["ts"] >= cut]
seen = set(); match_stats = Counter()
for it in desk_items:
    hits = match_players(it["title"], it["desc"]); match_stats["matched" if hits else "unmatched"] += 1
    for p in hits[:2]:
        k = (p["name"], it["title"][:60].lower())
        if k in seen: continue
        seen.add(k)
        rel = "Our player" if p["ours"] else "On our watch list" if p["watch"] else f"Affects our {p['nfl']} players" if p["nfl"] in our_nfl else "Free agent" if p["owner"] == "Free agent" else "League-wide"
        if rel in ("League-wide",) and not KEY.search(it["title"]): continue
        if rel == "Free agent" and not KEY.search(it["title"]): continue
        item = {"player": p["name"], "pos": p["pos"], "nfl": p["nfl"], "owner": p["owner"], "playerId": p["id"], "time": iso(it["ts"]), "headline": it["title"], "source": it["src"], "link": it["link"], "why": rel}
        (ours if p["ours"] else league).append(item)
# Sleeper trending: what the fantasy world is adding right now (crowd signal), matched by espn_id first
try:
    tr = get("https://api.sleeper.app/v1/players/nfl/trending/add?lookback_hours=24&limit=25", UA, timeout=25)
    health["Sleeper trending"] = {"status": "ok" if tr else "warning", "items": len(tr), "recent": len(tr), **({} if tr else {"note": "0 trending adds"})}
except Exception as e: tr = []; health["Sleeper trending"] = {"status": "error", "items": 0, "recent": 0, "error": f"{type(e).__name__}: {str(e)[:80]}"}
trending = []; tr_match = Counter()
for t_ in tr:
    q = SP.get(t_["player_id"], {}); nm = q.get("full_name") or (f'{q.get("team") or t_["player_id"]} D/ST' if q.get("position") == "DEF" or str(t_["player_id"]).isalpha() else "")
    eid = q.get("espn_id"); p = by_id.get(int(eid)) if str(eid or "").isdigit() else None
    how = "espn_id" if p else None
    if not p and nm:
        c = by_norm.get(norm(nm), []) or ([by_own[norm(nm)]] if norm(nm) in by_own else [])
        c = [x for x in c if not x.get("nfl") or (q.get("team") or "").upper() in (x.get("nfl"), ALIAS.get(x.get("nfl", ""), ""))] or c[:1]
        p = c[0] if c else None; how = "name+team" if p else None
    tr_match[how or "not in our pool"] += 1
    if p: nm = p["name"]
    if not nm: nm = f"Sleeper player {t_['player_id']} (no name in Sleeper's list)"
    trending.append({"player": nm, "pos": q.get("position") or "n/a", "nfl": q.get("team") or "FA", "adds24h": t_["count"], "owner": p["owner"] if p else "Free agent (not in our pool)", "matchedBy": how or "none"})
if "Sleeper players" in health: health["Sleeper players"]["recent"] = len(trending)
# ---------- classify: Rumor / Confirmed / Analysis / News ----------
RUMOR = re.compile(r"\b(rumou?r|reportedly|expected to|plan(s|ning)? to|in talks|interest(ed)? in|reached out|linked|considering|eyeing|could|potential|possible|visit|work(ed|ing)? out|workout|pending|candidate|would|trade idea|sweepstakes|inevitable|urged|monitor|likely|might)\w*", re.I)
CONF = re.compile(r"\b(signed|signs|has signed|agree[sd]? to terms|agreed|finalized|announced|placed on|released|waived|traded to|acquired|activated|elevated|claimed|officially|ruled out|will miss|underwent|decided not to|decides? not to|declined to|passed on)\b", re.I)
NOISE = re.compile(r"(waiver wire|fantasy football|start\W*sit|best bets|player props|picks,|rankings|grades?|grading|mock|quotes|FAAB|DFS|winners and losers|power rankings)", re.I)
MOVE = re.compile(r"\b(sign|trade|release|waive|cut|claim|acquire|deal|contract|visit|work(out| out)|reunion|interest|practice squad|IR|injured reserve|suspen|starter|starting|demot|promot|lead back)\w*", re.I)
def kind(h):
    if NOISE.search(h): return "Analysis"
    hedge = RUMOR.search(h); conf = CONF.search(h)
    if conf and not (hedge and hedge.start() < conf.start()): return "Confirmed"  # "X signs ..." is confirmed; "expected to sign" is not
    if hedge: return "Rumor"
    return "News"
for lst in (ours, league):
    for i in lst: i["kind"] = kind(i["headline"])
# ---------- story grouping: one story per player + event, with a source count ----------
STOP = {"with", "from", "that", "this", "after", "before", "over", "into", "will", "have", "about", "their", "week", "says", "said", "report", "reports", "sources", "source", "news", "update", "latest", "nfl"}
TEAMWORDS = {w2 for v in TEAMCTX.values() for w in v for w2 in norm(w).split()}
NEG = re.compile(r"\b(not|against|fail\w*|revers\w*|falls? apart|won't|wont|drop\w*|backs? out|chang\w* (?:their|its) minds?|scrap\w*|nixe?d?)\b|n't\b", re.I)
STEM = lambda w: re.sub(r"(ing|ed|es|s)$", "", w)
EVENTS = [("ir", r"\bIR\b|injured reserve"), ("sign", r"\bsign|practice squad|\bjoin"), ("trade", r"\btrad"), ("release", r"releas|waive|\bcut\b"),
          ("physical", r"physical"), ("visit", r"visit|workout|work out"), ("injury", r"injur|ankle|knee|hamstring|concussion|surgery|sprain|shoulder|groin|foot"),
          ("activate", r"activat|designated to return"), ("suspend", r"suspen")]
def event(h): return next((k for k, rx in EVENTS if re.search(rx, h, re.I)), None)  # canonical event: "to IR" = "on injured reserve"
def toks(p, h):
    nm = set(norm(p).split())
    return {STEM(w) for w in re.findall(r"[a-z]{4,}", norm(h)) if w not in STOP and w not in nm and w not in TEAMWORDS}
def group(items):
    items = sorted(items, key=lambda x: x["time"]); groups = []
    for it in items:
        tk = toks(it["player"], it["headline"]); ts = parse_date(it["time"]); ng = bool(NEG.search(it["headline"])); ev = event(it["headline"]); an = it.get("kind") == "Analysis"
        def same(g):
            if g["player"] != it["player"] or ts - g["_last"] > timedelta(hours=48): return False
            if norm(it["headline"])[:60] == g["_h"]: return True
            if g["_neg"] != ng or g["_an"] != an: return False
            if norm(it["headline"])[:60] == g["_h"]: return True  # the same headline from two feeds
            if ev and g["_ev"] == ev: return True  # same event, same direction ("signs" vs "won't sign" stay apart)
            return bool(g["_tok"] and tk and len(g["_tok"] & tk) >= min(2, len(tk)) and len(g["_tok"] & tk) / min(len(g["_tok"]), len(tk)) >= 0.5)
        g = next((g for g in groups if same(g)), None)
        if g is None:
            groups.append(dict(it, sources=1, firstSource=it.get("source", "RotoWire via ESPN"), firstTime=it["time"], also=[], _tok=tk, _last=ts, _neg=ng, _ev=ev, _an=an, _h=norm(it["headline"])[:60])); continue
        g["also"].append({"source": g.get("source", "RotoWire via ESPN"), "time": g["time"], "headline": g["headline"], "link": g.get("link", "")})
        g["also"] = g["also"][-5:]
        for k in ("time", "headline", "source", "link", "kind"):
            if k in it: g[k] = it[k]
        g["sources"] += 1; g["_tok"] |= tk; g["_last"] = ts
    for g in groups:
        for k in ("_tok", "_last", "_neg", "_ev", "_an", "_h"): g.pop(k)
    return sorted(groups, key=lambda x: x["time"], reverse=True)
raw_counts = {"ours": len(ours), "league": len(league)}
ours = group(ours); league = group(league)
# ---------- rumor mill: curated (Sam) first, then automatic ----------
rum = {}
for i in sorted(league + ours, key=lambda x: x["time"], reverse=True):
    if i["kind"] != "Rumor" or not MOVE.search(i["headline"]): continue
    if i["why"] in ("League-wide",) and not re.search(r"\b(sign|trade|release|reunion|deal|contract|visit|workout)\w*", i["headline"], re.I): continue
    r = rum.setdefault(i["player"], {"player": i["player"], "pos": i["pos"], "nfl": i["nfl"], "owner": i["owner"], "why": i["why"], "latest": i["headline"], "link": i.get("link", ""), "source": i.get("source", "RotoWire via ESPN"), "time": i["time"], "sources": 0})
    r["sources"] += i.get("sources", 1)
rumors = sorted(rum.values(), key=lambda r: (r["why"] not in ("Our player", "On our watch list"), -r["sources"], r["time"]))[:12]
rumor_status = {"curated": 0, "auto": 0, "expired": 0, "unreviewed": 0, "legacy": 0, "needsReview": 0}
cur_r = []
conf_by = defaultdict(list)
for i in ours + league:
    if i["kind"] == "Confirmed": conf_by[i["player"]].append(i)
if _cur and os.path.exists(os.path.join(_cur, "rumors.json")):  # Sam's curated rumors lead; refresh source counts from today's sweep
    cur_r = json.load(open(os.path.join(_cur, "rumors.json")))
    if not isinstance(cur_r, list): raise SystemExit("curated rumors.json must be a list")
    _fdate = datetime.fromtimestamp(os.path.getmtime(os.path.join(_cur, "rumors.json")), NY).date().isoformat()
    for r in cur_r:
        if r["player"] in rum: r.update({k: rum[r["player"]][k] for k in ("sources", "latest", "link", "source", "time")})
        r["reviewed"] = bool(r.get("action") and r.get("claim") and r.get("impact"))
        if r.get("expiresWeek") is None or not r.get("asOf"):  # old format: current until next week, flagged legacy
            r["legacy"] = True; r["asOf"] = r.get("asOf") or _fdate
            if r.get("expiresWeek") is None: r["expiresWeek"] = wk + 1
        r["expired"] = wk > int(r["expiresWeek"])
        r["origin"] = "curated"
        since = max(filter(None, [r.get("time"), r.get("asOf") and r["asOf"] + "T23:59Z"]), default=None)
        newer = [c for c in conf_by.get(r["player"], []) if not since or c["time"] > since]
        if newer:
            c = max(newer, key=lambda x: x["time"])
            r["needsReview"] = True; r["newerConfirmed"] = {"headline": c["headline"], "time": c["time"], "source": c.get("source"), "link": c.get("link", "")}
        else: r.pop("needsReview", None); r.pop("newerConfirmed", None)
else:
    rumor_status["error"] = f"no curated rumors.json under LT_CURATED ({_cur})"; fatal.append(rumor_status["error"])
have = {r["player"] for r in cur_r}
auto = []
for r in rumors:  # auto rumors merge in after the curated ones; nobody has written why it matters yet
    if r["player"] in have: continue
    x = r | {"origin": "auto", "reviewed": False, "expired": False, "claim": r.get("claim") or "", "impact": r.get("impact") or "", "action": r.get("action") or ""}
    newer = [c for c in conf_by.get(r["player"], []) if c["time"] > r["time"]]
    if newer:
        c = max(newer, key=lambda z: z["time"]); x["needsReview"] = True
        x["newerConfirmed"] = {"headline": c["headline"], "time": c["time"], "source": c.get("source"), "link": c.get("link", "")}
    auto.append(x)
rumors = cur_r + auto
rumor_status.update({"curated": len(cur_r), "auto": len(auto), "expired": sum(1 for r in rumors if r.get("expired")), "unreviewed": sum(1 for r in rumors if not r.get("reviewed")),
                     "legacy": sum(1 for r in rumors if r.get("legacy")), "needsReview": sum(1 for r in rumors if r.get("needsReview")),
                     "needsReviewNames": [r["player"] for r in rumors if r.get("needsReview")]})
key = lambda x: x["time"]
ours.sort(key=key, reverse=True); league.sort(key=key, reverse=True)
os.makedirs(f"{out}/news", exist_ok=True); os.makedirs(f"{out}/practice", exist_ok=True)
stamp = NOW.isoformat(timespec="minutes")
# ESPN player news health: 0 items in a game week is a failure, not "nothing new"
pn_status = "ok"; pn_notes = []
if pn["fetched"] == 0: pn_status = "error"; pn_notes.append(f"all {pn['players']} player-news fetches failed")
elif pn["rotowire"] == 0: pn_status = "error" if GAME_WEEK else "warning"; pn_notes.append(f"0 Rotowire items from {pn['fetched']} players")
if pn["failures"] and pn_status == "ok": pn_status = "warning"
if pn["failures"]: pn_notes.append(f"{pn['failures']} of {pn['players']} fetches failed")
if pn["badDates"] or pn["futureDates"]:
    pn_status = "warning" if pn_status == "ok" else pn_status; pn_notes.append(f"{pn['badDates']} unreadable / {pn['futureDates']} future-dated items")
health["ESPN player news"] = {"status": pn_status, "items": pn["rotowire"], "recent": pn["recent"], "players": pn["players"], "fetched": pn["fetched"], "failures": pn["failures"],
                              "badDates": pn["badDates"], "futureDates": pn["futureDates"], "droppedByType": dict(pn["droppedByType"]),
                              **({"note": "; ".join(pn_notes)} if pn_notes else {}), **({"errors": dict(pn["errors"])} if pn["errors"] else {})}
# quality gates on what we hand the page
# our injured players whose team's usual first practice day (kickoff - 4, ET) has passed with nothing parsed for them
_today = NOW.astimezone(NY).date()
def _due(p):
    w_ = practice_window(p["nfl"], NOW.astimezone(NY))
    return bool(w_ and w_[1] == wk and max(w_[2], w_[0].date() - timedelta(days=4)) < _today)  # the usual first practice day (kickoff - 4) has passed
our_inj = [p["name"] for p in pool if p["ours"] and p["status"] in ("QUESTIONABLE", "DOUBTFUL", "OUT") and p["name"] not in practice and _due(p)]
health["Practice reports"] = {"status": "warning" if our_inj else "ok", "items": sum(len(v["days"]) for v in practice.values()), "recent": len(practice), "parse": dict(PRSTAT),
                              **({"note": f"practice days have passed with no report found for our injured players: {', '.join(our_inj)} (Frank: check the official injury report)"} if our_inj else
                                 {"note": f"0 current-game practice entries: {PRSTAT['candidates']} practice notes read, {PRSTAT['otherWeek']} for another game, {PRSTAT['skippedIntent']} plans not reports, {PRSTAT['otherPlayer']} about another player, {PRSTAT['outsideWindow']} outside the window; teams' first practice report of the week may not be out yet"} if not practice else {})}
health["Name matcher"] = {"status": "ok" if SP else "error", "items": sum(match_stats.values()), "recent": match_stats["matched"], "matched": match_stats["matched"], "unmatched": match_stats["unmatched"],
                          "trendingMatchedBy": dict(tr_match), **({} if SP else {"error": "no Sleeper player list"})}
src_health = {k: v["status"] if v["status"] == "ok" else f'{v["status"]}: {v.get("error") or v.get("note", "")}' for k, v in health.items()}  # legacy string map
counts = {s: sum(1 for v in health.values() if v["status"] == s) for s in ("ok", "warning", "error")}
news_srcs = [k for k in health if k in FEEDS]
health_line = f"sources {counts['ok']} ok / {counts['warning']} warning / {counts['error']} error of {len(health)} | ESPN player news {pn['rotowire']} items ({pn['recent']} recent), {pn['failures']} failed fetches, dropped {dict(pn['droppedByType'])} | stories: ours {raw_counts['ours']} items -> {len(ours)}, league {raw_counts['league']} -> {len(league)}"
if health["ESPN player news"]["status"] == "error": fatal.append("ESPN player news: " + "; ".join(pn_notes))
if not any(health[k]["status"] == "ok" for k in news_srcs): fatal.append("no news source returned recent items")
json.dump({"updatedAt": stamp, "hours": HRS, "items": ours[:60], "rawItems": raw_counts["ours"]}, open(f"{out}/news/ours.json", "w"))
json.dump({"updatedAt": stamp, "hours": HRS, "items": league[:100], "rawItems": raw_counts["league"]}, open(f"{out}/news/league.json", "w"))
json.dump({"updatedAt": stamp, "week": wk, "trending": trending, "sources": src_health, "health": health, "healthLine": health_line, "counts": counts, "insiders": INSIDERS,
           "rumors": rumors, "rumorStatus": rumor_status, "missingWatch": missing_watch, "errors": fatal}, open(f"{out}/news/desk.json", "w"))
json.dump({"updatedAt": stamp, "week": wk, "tz": "America/New_York", "days": "Mon-Sat", "players": practice}, open(f"{out}/practice/current.json", "w"))
print(f"pool {len(pool)} | ours {len(ours)} stories ({raw_counts['ours']} items) | league {len(league)} ({raw_counts['league']}) | practice {len(practice)} | trending {len(trending)} | rumors {len(cur_r)} curated + {len(auto)} auto, {rumor_status['needsReview']} need review")
print("health:", health_line)
for k, v in health.items():
    if v["status"] != "ok": print(f"  {v['status'].upper()} {k}: {v.get('error') or v.get('note')}", file=sys.stderr)
if fatal: print("FAILED: " + "; ".join(fatal), file=sys.stderr); sys.exit(2)
