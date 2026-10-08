#!/usr/bin/env python3
"""League transaction log (league 293318): every claim (won, lost, canceled), free-agent add, drop and trade, with names.
Usage: python3 tools/db/transactions_pull.py [--dry]      Run from legal-troubles/. Exit 1 on any failure.
- Pulls ESPN mTransactions2 and MERGES it into data/db/transactions/raw.json by transaction id. Nothing is ever deleted:
  if ESPN drops old rows from its feed, our copy keeps them (the script reports how many it has that ESPN no longer shows).
- Builds data/db/transactions/log.json (readable rows, overwritten each run, derived only from raw.json + live names).
- Lost claims carry the reason and, when it can be proven from the same feed, which team won the player.
- Lineup moves (bench/start swaps) are counted but not listed; they stay in raw.json.
- Pending (not yet processed) claims are NOT visible to anyone in ESPN's feed; the feed only shows a claim after the 3 AM ET run.
"""
import json, os, sys, time, datetime as dt, urllib.request
from zoneinfo import ZoneInfo
B = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/293318"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "db")
OUT = os.path.join(ROOT, "transactions")
ET = ZoneInfo("America/New_York")
POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}
dry = "--dry" in sys.argv

def get(url, filt=None):
    h = {"User-Agent": "Mozilla/5.0"}
    if filt: h["X-Fantasy-Filter"] = json.dumps(filt)
    for k in range(3):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=120).read())
        except Exception:
            if k == 2: raise
            time.sleep(2 * (k + 1))
fails = []
def fail(m): fails.append(m)

# ---- 1) live feed merged into raw.json (never delete)
live = get(B + "?view=mTransactions2")["transactions"]
if len(live) < 50: print("FAIL: feed returned only", len(live), "transactions"); sys.exit(1)
rp = os.path.join(OUT, "raw.json")
raw = json.load(open(rp)) if os.path.exists(rp) else {}
new = [t for t in live if t["id"] not in raw]
live_ids = {t["id"] for t in live}
aged = [i for i in raw if i not in live_ids]
changed = 0
for t in live:
    if t["id"] in raw and raw[t["id"]] != t: changed += 1   # e.g. a pending row that later processed
    raw[t["id"]] = t

# ---- 2) names
teams_j = get(B + "?view=mTeam")
TEAM = {t["id"]: {"name": t["name"], "abbrev": t["abbrev"], "owner": t["primaryOwner"]} for t in teams_j["teams"]}
MEM = {m["id"]: (m.get("firstName", "") + " " + m.get("lastName", "")).strip() or m.get("displayName", "") for m in teams_j["members"]}
for v in TEAM.values(): v["ownerName"] = MEM.get(v["owner"], "")
PRO = {0: "FA"}
for p in get("https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026?view=proTeamSchedules_wl")["settings"]["proTeams"]:
    PRO[p["id"]] = p["abbrev"].upper()
NAME = {}
wd = os.path.join(ROOT, "weeks")
if os.path.isdir(wd):
    for w in sorted(os.listdir(wd)):
        f = os.path.join(wd, w, "players_week.json")
        if os.path.exists(f):
            for k, v in json.load(open(f))["players"].items(): NAME.setdefault(int(k), v)
need = set()
for t in raw.values():
    for i in t.get("items", []):
        if i.get("type") in ("ADD", "DROP", "TRADE") and i["playerId"] not in NAME: need.add(i["playerId"])
need = sorted(need)
for a in range(0, len(need), 50):
    chunk = need[a:a + 50]
    r = get(B + "?view=kona_player_info", {"players": {"filterIds": {"value": chunk}, "limit": len(chunk) + 5, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}})
    for x in r.get("players", []):
        pl = x["player"]; NAME[x["id"]] = {"name": pl["fullName"], "pos": pl.get("defaultPositionId"), "proTeam": pl.get("proTeamId")}
def P(pid):
    v = NAME.get(pid)
    if not v: fail(f"player id {pid} has no name"); return {"id": pid, "name": f"#{pid}", "pos": "?", "nfl": "?"}
    return {"id": pid, "name": v["name"], "pos": POS.get(v.get("pos"), "?"), "nfl": PRO.get(v.get("proTeam"), "?")}
def T(tid):
    v = TEAM.get(tid)
    if not v: fail(f"team id {tid} unknown"); return {"id": tid, "name": f"Team {tid}", "owner": ""}
    return {"id": tid, "name": v["name"], "owner": v["ownerName"]}
def iso(ms): return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def et(ms): return dt.datetime.fromtimestamp(ms / 1000, ET).strftime("%a %b %-d, %-I:%M %p ET")
def etd(ms): return dt.datetime.fromtimestamp(ms / 1000, ET).strftime("%Y-%m-%d")

# ---- 3) rows
rows = []; lineup = 0; skipped = {}
claims = [t for t in raw.values() if t["type"] == "WAIVER"]
won = {}   # (run date, player id) -> team id that won
for t in claims:
    if t.get("status") == "EXECUTED":
        for i in t["items"]:
            if i["type"] == "ADD": won[(etd(t.get("processDate") or t["proposedDate"]), i["playerId"])] = t["teamId"]
for t in sorted(raw.values(), key=lambda x: x["proposedDate"]):
    ty, st = t["type"], t.get("status")
    items = t.get("items", [])
    ms = t.get("processDate") or t["proposedDate"]
    base = {"id": t["id"], "ts": iso(ms), "when": et(ms), "week": t["scoringPeriodId"], "type": ty, "status": st, "team": T(t["teamId"])}
    if ty in ("ROSTER", "FUTURE_ROSTER") and all(i.get("type") == "LINEUP" for i in items):
        lineup += 1; continue
    add = next((i for i in items if i.get("type") == "ADD"), None)
    drop = next((i for i in items if i.get("type") == "DROP"), None)
    if ty == "WAIVER":
        r = dict(base, kind="claim", run=etd(ms), add=P(add["playerId"]) if add else None, drop=P(drop["playerId"]) if drop else None, bid=t.get("bidAmount", 0))
        if st == "EXECUTED": r["result"] = "won"
        elif st == "CANCELED": r["result"] = "canceled"; r["reason"] = "Claim canceled before it processed (by the owner or the league)"
        elif st and st.startswith("FAILED"):
            r["result"] = "lost"
            if st == "FAILED_INVALIDPLAYERSOURCE":
                w = won.get((r["run"], add["playerId"])) if add else None
                if w is not None and w != t["teamId"]:
                    r["wonBy"] = T(w); r["reason"] = "Lost: another team won this player in the same run"
                elif w is not None:
                    r["reason"] = "Failed: this team had already won this player with another claim in the same run"
                else:
                    r["reason"] = "Failed: player was no longer available when the claim processed (not won by any claim in this feed)"; r["unproven"] = True
            elif st == "FAILED_PLAYERALREADYDROPPED":
                used = any(o["teamId"] == t["teamId"] and o.get("status") == "EXECUTED" and etd(o.get("processDate") or o["proposedDate"]) == r["run"]
                           and any(j["type"] == "DROP" and drop and j["playerId"] == drop["playerId"] for j in o["items"]) for o in claims)
                r["reason"] = ("Failed: the player to drop was already released by this team's earlier claim in the same run" if used
                               else "Failed: the player to drop was already off the roster")
                if not used: r["unproven"] = True
            else: r["reason"] = "Failed: " + st; r["unproven"] = True
        elif t.get("isPending"): r["result"] = "pending"; r["reason"] = "Not processed yet"
        else: r["result"] = (st or "unknown").lower(); r["unproven"] = True
        rows.append(r)
    elif ty == "FREEAGENT":
        rows.append(dict(base, kind="fa_add", result="added" if st == "EXECUTED" else (st or "").lower(), add=P(add["playerId"]) if add else None, drop=P(drop["playerId"]) if drop else None))
    elif ty == "ROSTER" and drop and not add:
        rows.append(dict(base, kind="drop", result="dropped", drop=P(drop["playerId"])))
    elif ty == "TRADE_PROPOSAL":
        mv = [{"player": P(i["playerId"]), "from": T(i["fromTeamId"]), "to": T(i["toTeamId"])} for i in items if i.get("type") == "TRADE"]
        dropped = [P(i["playerId"]) for i in items if i.get("type") == "DROP"]
        rows.append(dict(base, kind="trade", result=(st or "").lower(), moves=mv, drops=dropped,
                         related=[o["type"] for o in raw.values() if o.get("relatedTransactionId") == t["id"]]))
    elif ty in ("TRADE_ACCEPT", "TRADE_UPHOLD", "TRADE_DECLINE"):
        rows.append(dict(base, kind="trade_event", result=ty.replace("TRADE_", "").lower(), relatedTo=t.get("relatedTransactionId")))
    else:
        skipped[ty] = skipped.get(ty, 0) + 1
        rows.append(dict(base, kind="other", result=(st or "").lower()))
rows.sort(key=lambda r: r["ts"], reverse=True)

# ---- 4) checks
kinds = {}
for r in rows: kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
n_in = sum(1 for t in raw.values() if t["type"] not in ("ROSTER", "FUTURE_ROSTER") or any(i.get("type") != "LINEUP" for i in t.get("items", [])))
if len(rows) != n_in: fail(f"row count {len(rows)} != non-lineup transactions {n_in}")
if len(rows) + lineup != len(raw): fail("rows + lineup moves != raw transactions")
nclaims = sum(1 for r in rows if r["kind"] == "claim")
if nclaims != len(claims): fail("claim rows != WAIVER transactions")
unproven = [r for r in rows if r.get("unproven")]
trade_ids = {t["id"] for t in raw.values() if t["type"] == "TRADE_PROPOSAL"}
orphans = [r for r in rows if r["kind"] == "trade_event" and r.get("relatedTo") not in trade_ids]
for r in unproven: print("  unproven:", r["when"], r["team"]["name"], r["add"] and r["add"]["name"], r["status"], r["reason"])
if skipped: print("note: unclassified types listed as 'other':", skipped)
log = {"season": 2026, "leagueId": 293318, "asOf": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
       "source": "ESPN mTransactions2, merged into raw.json by transaction id; nothing deleted", "feedCount": len(live), "rawCount": len(raw),
       "newThisRun": len(new), "agedOutOfEspnFeed": len(aged), "lineupMovesNotListed": lineup, "kinds": kinds,
       "claims": {k: sum(1 for r in rows if r["kind"] == "claim" and r["result"] == k) for k in ("won", "lost", "canceled", "pending")},
       "lostWithoutProvenWinner": len(unproven), "tradeEventsWithoutProposalInFeed": len(orphans),
       "notes": ["Pending claims are invisible until the 3 AM ET run processes them.",
                 "Claim priority / waiver order at the time of the run is not in the feed.",
                 "No FAAB in this league (traditional waivers), so bid is always 0.",
                 "ESPN removes a trade proposal from its feed once it is accepted or declined; accept/uphold/decline events show the team and time only, not the players."],
       "teams": {str(k): v["name"] for k, v in TEAM.items()}, "rows": rows}
print(f"feed {len(live)} | raw {len(raw)} (+{len(new)} new, {len(aged)} no longer in ESPN's feed, {changed} changed) | rows {len(rows)} | lineup moves not listed {lineup}")
print("kinds", kinds, "| claims", log["claims"], "| lost without proven winner:", len(unproven), "| trade events w/o proposal:", len(orphans))
if fails: print("FAIL:"); [print(" -", m) for m in sorted(set(fails))]; sys.exit(1)
if dry: sys.exit(0)
os.makedirs(OUT, exist_ok=True)
json.dump(raw, open(rp, "w"), separators=(",", ":"))
json.dump(log, open(os.path.join(OUT, "log.json"), "w"), separators=(",", ":"))
print("wrote", OUT)
