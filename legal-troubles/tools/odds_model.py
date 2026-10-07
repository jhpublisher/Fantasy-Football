"""Legal Troubles playoff-odds model v2 (Rich; Maya owns the numbers). Shared by bi_refresh.py and playoff_odds.py.

Model (Oct 7, 2026; outside review item 1):
  - Team strength is built week by week for every remaining regular-season week from each rostered player's
    ESPN per-game projection in our scoring:
      * current week: ESPN's own weekly projection (statSourceId 1, split 1, this week) – it already knows byes,
        injuries and matchups;
      * later weeks: ESPN rest-of-season projection (statSourceId 1, split 0, period 0) divided by the games the
        player is expected to play (his NFL team's remaining games from the week he is available);
        0 in his NFL team's bye week and before his return week.
  - Return weeks: INJURY_RESERVE = the 5th NFL team game after his last game played (IR is a 4-game minimum),
    never earlier than next week; OUT / SUSPENSION / DOUBTFUL = back next week; a curated override
    (LT_CURATED/ir_returns.json {"Player": {"returnWeek", "asOf", "expiresWeek", "note"}}) beats the inference.
  - Best legal lineup each week from the league's own slot counts; unlimited adds, so any hole (bye, injury) is
    filled by a free-agent streamer at replacement level (3rd-best free agent's projection this week, per position).
  - Calibration: c = league actual mean - league full-strength projection mean (global bias); each team also gets
    a shrunk share of its own actual-vs-projection gap: n/(n+K) with K = 8 games.
  - Uncertainty: each simulation draws one strength offset per team, N(0, SD/sqrt(n+K)), held for the whole
    season, plus a weekly score N(mu + offset, SD). SD = pooled within-team weekly SD, shrunk toward 21.
  - Seeding (project-instructions): record (ties = half a win); two-team tie = head-to-head, then points for;
    multi-team tie: a team that beat every other tied team head-to-head goes first (the rest re-ranked the same
    way), otherwise points for. Matches ESPN's live playoffSeed (checked Oct 7: all 14 seeds).
Rosters are held fixed (no future pickups or trades)."""
import math, random, statistics
from collections import defaultdict

MODEL = "v2 per-game projections week by week (byes, IR returns), strength uncertainty, record/H2H/PF"
SD_PRIOR, SD_PRIOR_GAMES, K_SHRINK = 21.0, 20, 8
POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}
SLOT_POS = {0: ("QB",), 2: ("RB",), 4: ("WR",), 6: ("TE",), 16: ("D/ST",), 17: ("K",), 3: ("RB", "WR"), 5: ("WR", "TE"),
            23: ("RB", "WR", "TE"), 7: ("QB", "RB", "WR", "TE")}


def stats_map(p, yr):
    return {(s["statSourceId"], s["statSplitTypeId"], s["scoringPeriodId"]): s.get("appliedTotal", 0) or 0
            for s in p.get("stats", []) if s.get("seasonId", yr) == yr}


def best_lineup(slot_counts, pl):
    """pl = [(pos, pts)] -> best legal lineup total. Fixed slots first, then flex slots."""
    for k in slot_counts:
        if k not in SLOT_POS and k not in (20, 21): raise KeyError(f"unknown lineup slot id {k} in league settings")
    by = defaultdict(list)
    for p, v in pl: by[p].append(v)
    for k in by: by[k].sort(reverse=True)
    tot = 0.0
    for sid in sorted(slot_counts, key=lambda s: len(SLOT_POS.get(s, ())) or 99):
        if sid in (20, 21): continue
        for _ in range(slot_counts[sid]):
            cand = [(by[p][0], p) for p in SLOT_POS[sid] if by[p]]
            if not cand: continue
            v, p = max(cand); tot += v; by[p].pop(0)
    return tot


def nfl_game_weeks(pro):
    """proTeamId -> sorted list of NFL weeks (scoring periods) with a game."""
    out = {}
    for t in pro["settings"]["proTeams"]:
        if t["id"] == 0: continue
        out[t["id"]] = sorted(int(w) for w, gl in t.get("proGamesByScoringPeriod", {}).items() if gl)
    return out


def played_weeks(player, yr):
    """NFL weeks with an actual stat line (ESPN writes stats only when the player was active; GP alone counts)."""
    return {s["scoringPeriodId"] for s in player.get("stats", []) if s.get("seasonId", yr) == yr
            and s["statSourceId"] == 0 and s["statSplitTypeId"] == 1 and s.get("stats")}


def return_week(player, wk, game_weeks, yr, overrides, played=None):
    """(week the player is next available for future weeks, reason). played = set of weeks he played (from the
    weekly-stats pull; mRoster alone only carries the last week)."""
    name = player["fullName"]; st = player.get("injuryStatus") or "ACTIVE"
    o = overrides.get(name)
    if o and o.get("returnWeek") is not None and not o.get("expired"):
        return max(int(o["returnWeek"]), wk), "curated"
    if st == "INJURY_RESERVE":
        pw = sorted(played if played is not None else played_weeks(player, yr))
        last = pw[-1] if pw else 0
        gw = [w for w in game_weeks.get(player.get("proTeamId"), []) if w > last]
        r = gw[4] if len(gw) > 4 else 99
        return max(r, wk + 1), f"IR: 5th team game after last played week {last or 'none'}"
    if st in ("OUT", "SUSPENSION", "DOUBTFUL"):
        return wk + 1, f"{st}: back next week"
    return wk, "active"


def replacement_candidates(slot_counts, repl):
    """Unlimited adds: every team can stream a free agent at replacement level (repl = {pos: weekly pts})."""
    out = []
    for pos, v in (repl or {}).items():
        n = min(3, sum(c for sid, c in slot_counts.items() if pos in SLOT_POS.get(sid, ())))
        out += [(pos, v)] * n
    return out


def team_week_projections(roster_entries, wk, reg, slot_counts, game_weeks, yr, overrides, played=None, repl=None, last_nfl_week=18):
    """{week: projected best-lineup points} for weeks wk..reg (free-agent streamers fill holes at replacement level),
    the full-strength lineup, and the non-active players with their assumed return weeks."""
    rows = []; detail = []; played = played or {}; rc = replacement_candidates(slot_counts, repl)
    for e in roster_entries:
        p = e["playerPoolEntry"]["player"]; pos = POS.get(p["defaultPositionId"])
        if not pos: continue
        st = stats_map(p, yr); gw = game_weeks.get(p.get("proTeamId"), [])
        rw, why = return_week(p, wk, game_weeks, yr, overrides, played.get(p["id"]))
        ros = st.get((1, 0, 0)) or st.get((1, 0, yr)) or 0
        avail = [w for w in gw if max(rw, wk) <= w <= last_nfl_week]
        rate = ros / len(avail) if ros and avail else (st.get((1, 1, wk), 0) if st.get((1, 1, wk)) else 0.0)
        rows.append((pos, p.get("proTeamId"), set(gw), rw, rate, st.get((1, 1, wk), 0) or 0))
        if why != "active": detail.append({"name": p["fullName"], "status": p.get("injuryStatus"), "returnWeek": rw if rw < 99 else None, "why": why, "rate": round(rate, 1)})
    out = {}
    for w in range(wk, reg + 1):
        if w == wk: pl = [(pos, cur) for pos, _, _, _, _, cur in rows]
        else: pl = [(pos, rate) for pos, _, gws, rw, rate, _ in rows if w in gws and w >= rw]
        out[w] = best_lineup(slot_counts, pl + rc)
    full = best_lineup(slot_counts, [(pos, rate) for pos, _, _, _, rate, _ in rows] + rc)
    return out, full, detail


def weekly_sd(scores):
    res = [x - statistics.mean(v) for v in scores.values() if len(v) > 1 for x in v]
    dof = sum(len(v) - 1 for v in scores.values() if len(v) > 1)
    if dof <= 0: return SD_PRIOR
    pooled = sum(r * r for r in res) / dof
    return math.sqrt((dof * pooled + SD_PRIOR_GAMES * SD_PRIOR ** 2) / (dof + SD_PRIOR_GAMES))


def strengths(team_ids, weekproj, full, scores):
    """mu[team][week], plus summary numbers. scores = {team: [actual weekly points]}."""
    played = [x for v in scores.values() for x in v]
    lg_act = statistics.mean(played) if played else statistics.mean(full.values())
    c = lg_act - statistics.mean(full[k] for k in team_ids)
    mu = {}; adj = {}
    for k in team_ids:
        n = len(scores.get(k, []))
        gap = (statistics.mean(scores[k]) - (full[k] + c)) if n else 0.0
        adj[k] = n / (n + K_SHRINK) * gap
        mu[k] = {w: v + c + adj[k] for w, v in weekproj[k].items()}
    return mu, {"bias": round(c, 2), "adj": {k: round(v, 2) for k, v in adj.items()}, "leagueActualMean": round(lg_act, 2)}


def order_group(g, pf, hh):
    g = list(g)
    if len(g) <= 1: return g
    if len(g) == 2:
        a, b = g; d = hh.get((a, b), 0) - hh.get((b, a), 0)
        if d: return [a, b] if d > 0 else [b, a]
        return sorted(g, key=lambda k: -pf.get(k, 0))
    sweep = [k for k in g if all(hh.get((k, o), 0) > hh.get((o, k), 0) for o in g if o != k)]
    if len(sweep) == 1:
        return sweep + order_group([k for k in g if k != sweep[0]], pf, hh)
    return sorted(g, key=lambda k: -pf.get(k, 0))


def rank(team_ids, w, pf, hh):
    """w = win-equivalents (wins + 0.5 ties). Returns team ids in seed order."""
    gr = defaultdict(list)
    for k in team_ids: gr[w.get(k, 0)].append(k)
    o = []
    for x in sorted(gr, reverse=True): o += order_group(gr[x], pf, hh)
    return o


def simulate(team_ids, me, po, Wd, Td, PFd, Hd, remaining, mu, sd, games_played, n, rng):
    """remaining = [(week, home, away)]. Returns made, top, cushion list, seed counts."""
    made = defaultdict(int); top = defaultdict(int); cush = []; seeds = defaultdict(lambda: defaultdict(int))
    s_team = sd / math.sqrt(games_played + K_SHRINK)
    for _ in range(n):
        off = {k: rng.gauss(0, s_team) for k in team_ids}
        w = {k: Wd.get(k, 0) + 0.5 * Td.get(k, 0) for k in team_ids}; pf = dict(PFd); hh = dict(Hd)
        for wk_, h, a in remaining:
            hs = rng.gauss(mu[h][wk_] + off[h], sd); as_ = rng.gauss(mu[a][wk_] + off[a], sd)
            pf[h] = pf.get(h, 0) + hs; pf[a] = pf.get(a, 0) + as_
            x, y = (h, a) if hs > as_ else (a, h); w[x] += 1; hh[(x, y)] = hh.get((x, y), 0) + 1
        o = rank(team_ids, w, pf, hh)
        for k in o[:po]: made[k] += 1
        top[o[0]] += 1
        for i, k in enumerate(o): seeds[k][i + 1] += 1
        if me is not None: cush.append(w[me] - w[o[po]])
    return made, top, cush, seeds
