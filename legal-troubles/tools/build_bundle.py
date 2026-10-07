"""Merge bi_refresh + news_sweep output (+ curated memos, + Return Game data) into one data/bundle.json for the GitHub site.
Usage: python3 build_bundle.py <out_dir> <bundle.json> [curated_dir] [--prev last_good_bundle.json] [--returns returns.json] [--status run_status.json]
  --prev: the last good (published) bundle to fall back on; default = <bundle.json> itself
  --returns (or env LT_RETURNS): the returns builder's returns.json (keys weeks, checked, teams, players) -> bundle.returns.current
  --status  (or env LT_RUN_STATUS): optional {"bi_refresh": exitCode, "news_sweep": exitCode, "returns": exitCode} written by the workflow
  Returns: freshness = returns.json `updatedAt` (never file mtime). If the returns chain failed (status "returns" != 0) the last
  good returns.json is kept and marked stale. If returns has never existed (no file, nothing in --prev), the section is absent.
Never drops a section silently. Every required section is either fresh from this run, or the last good copy
from the previous bundle marked {stale: true, staleSince, reason}. A section with no fresh data and no
previous copy is written as {"error": reason}. Per-section status is in bundle.sections.
Keeps history: old odds weeks and memos already in the bundle are preserved."""
import json, os, sys, glob, argparse, copy
from datetime import datetime, timezone
ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("dst"); ap.add_argument("curated", nargs="?")
ap.add_argument("--prev"); ap.add_argument("--returns", default=os.environ.get("LT_RETURNS")); ap.add_argument("--status", default=os.environ.get("LT_RUN_STATUS"))
A = ap.parse_args()
src, dst, cur = A.src, A.dst, A.curated
now = datetime.now(timezone.utc).isoformat(timespec="minutes")
def load(p): return json.load(open(p))
prev_path = A.prev or dst
old = load(prev_path) if os.path.exists(prev_path) else {}
old_sections = old.get("sections") or {}
run = load(A.status) if A.status and os.path.exists(A.status) else {}
def run_note(tool):
    c = run.get(tool)
    return f" ({tool} exit {c})" if c not in (None, 0) else ""
# ---- this run's raw output ----
new = {}
for f in glob.glob(f"{src}/*/*.json"):
    coll, did = f.split(os.sep)[-2], os.path.basename(f)[:-5]
    try: new.setdefault(coll, {})[did] = load(f)
    except Exception as e: new.setdefault("_bad", {})[f] = str(e)
SINGLE = ("meta", "waivers", "practice")  # stored as one doc, not a {id: doc} map
b = {"builtAt": now, "sections": {}}
def is_err(x): return isinstance(x, dict) and set(x) >= {"error"} and len(x) <= 2
def mark(doc, since, reason):
    if isinstance(doc, dict) and not is_err(doc): doc.update({"stale": True, "staleSince": since, "reason": reason})
    return doc
def unmark(doc):
    if isinstance(doc, dict):
        for k in ("stale", "staleSince", "reason"): doc.pop(k, None)
    return doc
def fresh(name, value, updated):
    b["sections"][name] = {"ok": True, "stale": False, "updatedAt": updated}; return value
def keep_old(name, oldval, reason):
    """Last good copy from the previous bundle, marked stale; or an explicit error if there is none."""
    prev = old_sections.get(name) or {}
    since = prev.get("staleSince") or prev.get("updatedAt") or old.get("builtAt")
    if oldval in (None, {}, []) or is_err(oldval):
        b["sections"][name] = {"ok": False, "stale": False, "error": reason}
        return {"error": reason}
    v = copy.deepcopy(oldval)
    if name in SINGLE + ("nfl", "curated", "extras", "returns") or name.startswith("news."): mark(v, since, reason)
    else:
        for d in v.values(): mark(d, since, reason)
    b["sections"][name] = {"ok": False, "stale": True, "staleSince": since, "reason": reason, "updatedAt": prev.get("updatedAt")}
    print(f"STALE {name}: {reason} (last good {since})", file=sys.stderr)
    return v
# ---- meta + league block ----
meta = (new.get("meta") or {}).get("current")
bi_stamp = meta.get("updatedAt") if meta else None
b["meta"] = fresh("meta", unmark(meta), bi_stamp) if meta else keep_old("meta", old.get("meta"), "meta/current not produced" + run_note("bi_refresh"))
b["league"] = (b["meta"] or {}).get("league") if not is_err(b["meta"]) else None
week = (b["meta"] or {}).get("week") if not is_err(b["meta"]) else None
# ---- map sections from bi_refresh ----
for name in ("players", "scores"):
    d = new.get(name)
    b[name] = fresh(name, d, bi_stamp) if d else keep_old(name, old.get(name), f"no {name} in this run" + run_note("bi_refresh"))
odds = dict(old.get("odds") or {})
for k, v in odds.items(): unmark(v)
cur_key = f"w{week:02d}" if isinstance(week, int) else None
if new.get("odds") and cur_key in new["odds"]:
    odds.update(new["odds"]); b["odds"] = fresh("odds", odds, bi_stamp)
else:
    b["odds"] = keep_old("odds", old.get("odds"), f"no odds/{cur_key} in this run" + run_note("bi_refresh"))
for name in ("waivers",):
    d = (new.get(name) or {}).get("current")
    b[name] = fresh(name, unmark(d), bi_stamp) if d else keep_old(name, old.get(name), f"{name}/current not produced" + run_note("bi_refresh"))
for name in ("nfl", "curated"):
    d = (new.get(name) or {}).get("current")
    if d and not is_err(d): b[name] = {"current": fresh(name, d, bi_stamp)}
    else:
        oc = (old.get(name) or {}).get("current")
        b[name] = {"current": keep_old(name, oc, (d or {}).get("error") or f"{name}/current not produced" + run_note("bi_refresh"))}
# ---- extras: per feature (one failed feature keeps its last good value, the rest stay fresh) ----
ex_new = (new.get("extras") or {}).get("current")
ex_old = (old.get("extras") or {}).get("current") or {}
if not ex_new:
    b["extras"] = {"current": keep_old("extras", ex_old or None, "extras/current not produced" + run_note("bi_refresh"))}
else:
    ex = dict(ex_new); stale_f = {}
    for k, v in ex_new.items():
        if is_err(v):
            ov = ex_old.get(k); prev = old_sections.get(f"extras.{k}") or {}
            since = prev.get("staleSince") or prev.get("updatedAt") or ex_old.get("updatedAt")
            if ov is not None and not is_err(ov):
                ex[k] = ov; stale_f[k] = {"stale": True, "staleSince": since, "reason": v["error"]}
                b["sections"][f"extras.{k}"] = {"ok": False, "stale": True, "staleSince": since, "reason": v["error"], "updatedAt": prev.get("updatedAt")}
                print(f"STALE extras.{k}: {v['error']}", file=sys.stderr)
            else:
                b["sections"][f"extras.{k}"] = {"ok": False, "stale": False, "error": v["error"]}
        elif k not in ("week", "updatedAt", "builtAt", "errors", "staleFeatures", "regWeeks"):
            b["sections"][f"extras.{k}"] = {"ok": True, "stale": False, "updatedAt": ex_new.get("updatedAt")}
    ex["staleFeatures"] = stale_f
    b["extras"] = {"current": fresh("extras", ex, ex_new.get("updatedAt"))}
    if stale_f or ex_new.get("errors"): b["sections"]["extras"].update({"ok": False, "partial": True})
# ---- news + practice ----
nw = new.get("news") or {}; on = old.get("news") or {}
desk = nw.get("desk"); news_stamp = desk.get("updatedAt") if desk else None
b["news"] = {}
desk_err = "; ".join(desk.get("errors") or []) if desk else ""
for k in ("ours", "league", "desk"):
    d = nw.get(k)
    if d and not (desk_err and k in ("ours", "league")): b["news"][k] = fresh(f"news.{k}", unmark(d), d.get("updatedAt"))
    else:
        reason = desk_err if (d and desk_err) else f"news/{k} not produced" + run_note("news_sweep")
        b["news"][k] = keep_old(f"news.{k}", on.get(k), reason)
b["sections"]["news"] = {"ok": all(b["sections"][f"news.{k}"].get("ok") for k in ("ours", "league", "desk")),
                         "stale": any(b["sections"][f"news.{k}"].get("stale") for k in ("ours", "league", "desk")), "updatedAt": news_stamp}
pr = (new.get("practice") or {}).get("current")
b["practice"] = fresh("practice", unmark(pr), pr.get("updatedAt")) if pr else keep_old("practice", old.get("practice"), "practice/current not produced" + run_note("news_sweep"))
# ---- memos (curated; history kept) ----
memos = dict(old.get("memos") or {})
for v in memos.values(): unmark(v)
got = 0
if cur:
    for f in glob.glob(f"{cur}/memos/*.json"): memos[os.path.basename(f)[:-5]] = load(f); got += 1
if got: b["memos"] = fresh("memos", memos, now)
else: b["memos"] = keep_old("memos", old.get("memos"), f"no memos in curated dir ({cur})")
# ---- returns (Return Game data) ----
old_rt = (old.get("returns") or {}).get("current")
rt_rc = run.get("returns")
if A.returns and os.path.exists(A.returns):
    try:
        rt = load(A.returns)
        miss = [k for k in ("weeks", "checked", "teams", "players") if k not in rt]
        if miss: raise ValueError(f"returns.json missing keys {miss}")
        unmark(rt)
        if rt_rc not in (None, 0):  # chain failed this run: the file is the last good build, shown stale
            since = rt.get("updatedAt") or (old_sections.get("returns") or {}).get("staleSince")
            reason = f"returns chain failed this run (exit {rt_rc}); showing last good build"
            mark(rt, since, reason)
            b["sections"]["returns"] = {"ok": False, "stale": True, "staleSince": since, "reason": reason, "updatedAt": rt.get("updatedAt")}
            print(f"STALE returns: {reason}", file=sys.stderr); b["returns"] = {"current": rt}
        else:
            b["returns"] = {"current": fresh("returns", rt, rt.get("updatedAt"))}
            if not rt.get("updatedAt"): b["sections"]["returns"]["note"] = "returns.json has no updatedAt"
    except Exception as e:
        b["returns"] = {"current": keep_old("returns", old_rt, f"returns.json unreadable: {e}")}
elif old_rt:
    b["returns"] = {"current": keep_old("returns", old_rt, f"returns file not found ({A.returns or 'no --returns/LT_RETURNS given'})" + run_note("returns"))}
else:
    print("note: no returns data yet (never built); returns section omitted", file=sys.stderr)
lgb = b.get("league")
if isinstance(lgb, dict) and not lgb.get("waiverProcessET"):  # dates feature failed this run: fall back to the last good waiver time, flagged
    dd = ((b.get("extras") or {}).get("current") or {}).get("dates") or {}
    if dd.get("waiversET"): lgb["waiverProcessET"] = dd["waiversET"]; lgb["waiverProcessETStale"] = True
KNOWN = {"meta", "players", "scores", "odds", "waivers", "nfl", "curated", "extras", "news", "practice", "validation", "_bad"}
for coll, docs in new.items():  # anything else a tool writes is carried through, never silently dropped
    if coll in KNOWN: continue
    b[coll] = docs; b["sections"][coll] = {"ok": True, "stale": False, "updatedAt": now}
    print(f"note: passing through unknown collection {coll!r}", file=sys.stderr)
b["run"] = {"status": run, "badFiles": new.get("_bad", {})}
b["validation"] = None  # written by validate_bundle.py
os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
json.dump(b, open(dst, "w"), separators=(",", ":"))
stale = [k for k, v in b["sections"].items() if v.get("stale")]; errs = [k for k, v in b["sections"].items() if v.get("error")]
print("bundle:", {k: (len(v) if isinstance(v, dict) else bool(v)) for k, v in b.items() if k not in ("sections", "run")})
print(f"sections: {sum(1 for v in b['sections'].values() if v.get('ok'))} fresh, stale {stale or 'none'}, error {errs or 'none'}")
