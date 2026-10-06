"""Merge bi_refresh + news_sweep output (+ curated memos) into one data/bundle.json for the GitHub site.
Usage: python3 build_bundle.py <out_dir> <bundle.json> [curated_dir]
Keeps history: old odds weeks and memos already in the bundle are preserved."""
import json, os, sys, glob
from datetime import datetime, timezone
src, dst = sys.argv[1], sys.argv[2]; cur = sys.argv[3] if len(sys.argv) > 3 else None
old = json.load(open(dst)) if os.path.exists(dst) else {}
b = {"meta": None, "odds": old.get("odds", {}), "scores": {}, "players": {}, "waivers": None, "news": {}, "practice": None, "memos": old.get("memos", {})}
def load(p): return json.load(open(p))
for f in glob.glob(f"{src}/*/*.json"):
    coll, did = f.split(os.sep)[-2], os.path.basename(f)[:-5]; d = load(f)
    if coll in ("meta", "waivers", "practice"): b[coll] = d
    else: b.setdefault(coll, {})[did] = d
if cur:
    for f in glob.glob(f"{cur}/memos/*.json"): b["memos"][os.path.basename(f)[:-5]] = load(f)
b["builtAt"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
json.dump(b, open(dst, "w"), separators=(",", ":"))
print("bundle:", {k: (len(v) if isinstance(v, dict) else bool(v)) for k, v in b.items()})
