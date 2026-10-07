"""Legal Troubles bundle validator (Rich). Run before ANY publish or commit of data/bundle.json.
Usage: python3 validate_bundle.py <bundle.json> [--out validation.json] [--max-age-hours 6] [--no-write]
Writes bundle.validation = {ok, failures[], warnings[], checkedAt, staleData, staleSections[], summary}
into the bundle (unless --no-write) and, with --out, into a separate small file the page can read even when
the bundle itself is not published. Exit code 1 if any failure (publish must stop), 0 otherwise.
Failures stop the publish; warnings publish with a banner."""
import json, sys, argparse, re
from datetime import datetime, timezone, timedelta
ap = argparse.ArgumentParser()
ap.add_argument("bundle"); ap.add_argument("--out"); ap.add_argument("--max-age-hours", type=float, default=6.0)
ap.add_argument("--no-write", action="store_true"); ap.add_argument("--league-teams", type=int, default=14)
A = ap.parse_args()
F, Wn = [], []
def fail(m): F.append(m)
def warn(m): Wn.append(m)
now = datetime.now(timezone.utc)
try: b = json.load(open(A.bundle))
except Exception as e:
    b = None; fail(f"bundle unreadable: {type(e).__name__}: {e}")
def ts(s):
    if not s: return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception: return None
def is_err(x): return isinstance(x, dict) and "error" in x and len(x) <= 2
stale_sections = []
if b is not None:
    S = b.get("sections") or {}
    lg = b.get("league") or {}
    meta = b.get("meta") or {}
    # ---------- required sections ----------
    req = ["meta", "players", "odds", "scores", "waivers", "extras", "news.ours", "news.league", "news.desk", "practice", "memos", "nfl", "curated"]
    if "returns" in b or "returns" in S: req.append("returns")
    for k in req:
        st = S.get(k)
        top = k.split(".")[0]
        if top not in b or b[top] in (None, {}, []): fail(f"section {k}: missing" + (f" ({st.get('error')})" if st and st.get("error") else " with no error reason"))
        elif st is None: fail(f"section {k}: no status entry in bundle.sections")
        elif st.get("error"): fail(f"section {k}: no data, error: {st['error']}")
        elif st.get("stale"): warn(f"section {k}: STALE since {st.get('staleSince')}: {st.get('reason')}"); stale_sections.append(k)
    for k, st in S.items():
        if k.startswith("extras.") and st.get("error"): fail(f"{k}: error: {st['error']}")
        elif k.startswith("extras.") and st.get("stale"): warn(f"{k}: STALE since {st.get('staleSince')}: {st.get('reason')}"); stale_sections.append(k)
    # ---------- data age ----------
    for k, st in S.items():
        u = ts(st.get("updatedAt"))
        if st.get("ok") and u and now - u > timedelta(hours=A.max_age_hours):
            warn(f"section {k}: updatedAt {st['updatedAt']} is older than {A.max_age_hours:g}h"); stale_sections.append(k)
        if st.get("stale"):
            u = ts(st.get("staleSince"))
            if u and now - u > timedelta(hours=A.max_age_hours) and k not in stale_sections: stale_sections.append(k)
    # ---------- league block ----------
    for k in ("playoffTeams", "regSeasonWeeks", "playoffWeeks", "starters", "currentWeek", "avgWeeksRange"):
        if lg.get(k) in (None, [], ""): fail(f"league.{k} missing")
    if not lg.get("waiverProcessET"): warn("league.waiverProcessET missing (no players on waivers right now?)")
    wk = lg.get("currentWeek") or meta.get("week"); REG = lg.get("regSeasonWeeks") or 0
    NT = A.league_teams
    if lg.get("teams") not in (None, NT): fail(f"league has {lg.get('teams')} teams, expected {NT}")
    # ---------- NFL teams ----------
    nfl = (b.get("nfl") or {}).get("current") or {}
    teams32 = set(nfl.get("teams") or [])
    if len(teams32) != 32: fail(f"NFL teams: {len(teams32)} (expected 32)")
    okab = teams32 | {"FA"}
    def chk_ab(where, code):
        if not teams32: return  # already failed above; don't cascade
        c = (code or "").lstrip("@")
        if c not in okab and c != "BYE": fail(f"unknown NFL abbreviation {code!r} in {where}")
    # ---------- NFL games per week ----------
    if nfl.get("weeksError"): fail(f"NFL game counts unavailable: {nfl['weeksError']}")
    for w, x in sorted((nfl.get("weeks") or {}).items(), key=lambda z: int(z[0])):
        if x.get("scoreboard") != x.get("scheduled"): fail(f"NFL week {w}: scoreboard has {x.get('scoreboard')} games, schedule has {x.get('scheduled')}")
        if x.get("final") and x.get("completed") != x.get("scheduled"): fail(f"NFL week {w}: {x.get('completed')}/{x.get('scheduled')} games completed but week is over")
    if wk and nfl and str(wk) not in (nfl.get("weeks") or {}): fail(f"NFL week {wk}: no game counts")
    # ---------- league teams in odds / standings ----------
    if isinstance(wk, int):
        od = (b.get("odds") or {}).get(f"w{wk:02d}") or {}
        n = len(od.get("teams") or [])
        if n != NT: fail(f"odds w{wk:02d}: {n} teams (expected {NT})")
        wo = (b.get("waivers") or {}).get("order") or []
        if len(wo) != NT: fail(f"waivers: {len(wo)} teams (expected {NT})")
        race = ((b.get("extras") or {}).get("current") or {}).get("race")
        if isinstance(race, list) and len(race) != NT: fail(f"standings/race: {len(race)} teams (expected {NT})")
        # ---------- scores ----------
        sc = b.get("scores") or {}
        for w in range(1, min(wk, REG + 1) if REG else wk):
            d = sc.get(f"w{w:02d}")
            if not d: fail(f"scores: completed week {w} missing"); continue
            m = d.get("matchups", len(d.get("scores") or {}) // 2)
            if m != NT // 2 or len(d.get("scores") or {}) != NT: fail(f"scores w{w:02d}: {m} matchups / {len(d.get('scores') or {})} teams (expected {NT // 2} / {NT})")
    # ---------- players ----------
    P = b.get("players") or {}
    for i in meta.get("rosterIds") or []:
        if str(i) not in P: fail(f"rostered player {i} not resolved in players")
    if not meta.get("rosterIds"): fail("meta.rosterIds missing: cannot check our roster is complete")
    for i in meta.get("unresolvedRoster") or []: fail(f"rostered player {i} unresolved (bi_refresh)")
    for t in meta.get("unresolvedTags") or []: warn(f"tagged player {t!r} not found in ESPN pull")
    for pid, p in P.items():
        if not isinstance(p, dict): continue
        if not p.get("name") or p.get("pos") in (None, "", "?"): fail(f"player {pid}: unresolved name/position ({p.get('name')!r}, {p.get('pos')!r})")
        chk_ab(f"players/{pid}", p.get("nfl"))
        for o in p.get("playoffs") or []: chk_ab(f"players/{pid} playoffs", o)
        if p.get("tagExpired"): warn(f"tag for {p.get('name')} expired (week {p.get('tagExpiresWeek')}); page must not show it as current")
    ex = (b.get("extras") or {}).get("current") or {}
    mu = ex.get("matchup")
    if isinstance(mu, dict) and not is_err(mu):
        for s_ in (mu.get("usStarters") or []) + (mu.get("oppStarters") or []): chk_ab("matchup starters", s_.get("nfl"))
        if lg.get("starters") and len(mu.get("usStarters") or []) != lg["starters"]: warn(f"our lineup has {len(mu.get('usStarters') or [])} starters, league uses {lg['starters']}")
    fa = ex.get("freeAgents")
    if isinstance(fa, dict) and not is_err(fa):
        for v in fa.values():
            for x in v: chk_ab("freeAgents", x.get("nfl"))
    # ---------- news health ----------
    desk = (b.get("news") or {}).get("desk") or {}
    srcs = desk.get("sources") or {}; health = desk.get("health") or {}
    if not health: fail("news: desk.health missing (no per-source item counts)")
    for k in srcs:
        if k not in health: fail(f"news source {k!r} has no health entry")
    if "ESPN player news" not in health: fail("news: no health entry for ESPN player news")
    for k, h in health.items():
        if not isinstance(h.get("items"), int): fail(f"news source {k!r}: no item count")
        if h.get("status") == "error": (fail if k == "ESPN player news" else warn)(f"news source {k!r}: error: {h.get('error') or h.get('note')}")
        elif h.get("status") == "warning": warn(f"news source {k!r}: {h.get('note')}")
    for e in desk.get("errors") or []: fail(f"news_sweep: {e}")
    for r in desk.get("rumors") or []:
        if r.get("expired"): warn(f"rumor {r.get('player')} expired (week {r.get('expiresWeek')})")
        if r.get("legacy"): warn(f"rumor {r.get('player')}: old format (no asOf/expiresWeek), shown as current until week {r.get('expiresWeek')}")
    # ---------- practice ----------
    pr = b.get("practice") or {}
    for nm, x in (pr.get("players") or {}).items():
        chk_ab(f"practice/{nm}", x.get("nfl"))
        win = x.get("window")
        for lab, d in (x.get("days") or {}).items():
            if not win or not d.get("date") or not (win[0] <= d["date"] <= win[1]): warn(f"practice {nm} {lab}: not inside the team's practice window {win}")
    # ---------- curated freshness ----------
    cs = (b.get("curated") or {}).get("current") or {}
    for k in ("tags", "claims", "needs"):
        x = cs.get(k) or {}
        if x.get("error"): fail(f"curated {k}: {x['error']}")
        if x.get("legacy"): warn(f"curated {k}: {x['legacy']} old-format entries (no asOf/expiresWeek) shown as current until week {(lg.get('currentWeek') or 0) + 1}: {', '.join(x.get('legacyNames') or [])}. Re-save them with asOf + expiresWeek")
        if x.get("expired"): warn(f"curated {k}: {x['expired']} expired: {', '.join(x.get('expiredNames') or [])}")
    # ---------- returns ----------
    rt = (b.get("returns") or {}).get("current")
    if rt is not None and not is_err(rt):
        if not rt.get("updatedAt"): warn("returns: no updatedAt (cannot judge freshness)")
        T = rt.get("teams") or {}
        if len(T) != 32: fail(f"returns: {len(T)} teams (expected 32)")
        for t, x in T.items():
            if t not in teams32: fail(f"returns: unknown team {t!r}")
            sts = [(k, v) for k, v in x.items() if isinstance(v, dict) and "status" in v]
            if "status" in x: sts.append(("team", x))
            if not sts: fail(f"returns {t}: no read status")
            for k, v in sts:
                s_ = v.get("status")
                if s_ not in ("ok", "no_kr_row", "no_chart", "unread"): fail(f"returns {t} {k}: status {s_!r} (must be ok / no_kr_row / no_chart / unread)")
                if s_ == "unread" and not (v.get("reason") or "").strip(): fail(f"returns {t} {k}: unread with no reason")
                for n in v.get("kr") or []:
                    if not str(n or "").strip(): fail(f"returns {t} {k}: empty returner name")
        for p in rt.get("players") or []:
            if not str(p.get("name") or "").strip(): fail(f"returns players: empty name (team {p.get('team')})")
            for k in ("team", "pos", "owner"):
                if not str(p.get(k) or "").strip() or p.get(k) == "—": fail(f"returns player {p.get('name')}: blank {k}")
    elif rt is not None: fail(f"returns: {rt.get('error')}")
    if (b.get("run") or {}).get("badFiles"): fail(f"unreadable output files: {list(b['run']['badFiles'])}")
stale_sections = sorted(set(stale_sections))
v = {"ok": not F, "failures": F, "warnings": Wn, "checkedAt": now.isoformat(timespec="minutes"), "staleData": bool(stale_sections),
     "staleSections": stale_sections, "maxAgeHours": A.max_age_hours, "bundleBuiltAt": (b or {}).get("builtAt")}
if b is not None and not A.no_write:
    b["validation"] = v; json.dump(b, open(A.bundle, "w"), separators=(",", ":"))
if A.out: json.dump(v, open(A.out, "w"), indent=1)
print(f"validation: {'OK' if not F else 'FAILED'} | {len(F)} failures, {len(Wn)} warnings | stale: {stale_sections or 'none'}")
for m in F: print("  FAIL", m)
for m in Wn: print("  warn", m)
sys.exit(0 if not F else 1)
