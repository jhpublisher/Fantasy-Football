# Shared helpers for the Return Game store (Oct 7 redesign). One immutable file per week: weeks/<season>-wNN.json.
import json,csv,os,hashlib,io
TABLES=['kick_returns','team_game_kick_totals','punt_returns','team_game_punt_totals','kickoff_coverage']
NONSTAT={'owner','fantasy_pos'}   # current state; never stored in a week file
def canon(tables): return json.dumps({t:tables[t] for t in TABLES},sort_keys=True,separators=(',',':'),ensure_ascii=False)
def sha(tables): return hashlib.sha256(canon(tables).encode()).hexdigest()
def tables_from_csv(d,week):
    out={}
    for t in TABLES:
        out[t]=[{k:v for k,v in r.items() if k not in NONSTAT} for r in csv.DictReader(open(os.path.join(d,t+'.csv'),newline='',encoding='utf-8')) if int(r['week'])==week]
    return out
def week_path(store,season,w): return os.path.join(store,'weeks',f'{season}-w{w:02d}.json')
def load_index(store):
    p=os.path.join(store,'index.json')
    return json.load(open(p)) if os.path.exists(p) else {'season':2026,'weeks':{}}
def check_week_file(store,season,w,entry):
    W=json.load(open(week_path(store,season,w),encoding='utf-8'))
    if sha(W['tables'])!=W['sha256'] or W['sha256']!=entry['sha256']: raise SystemExit(f'FAIL: week {w} file does not match its recorded fingerprint')
    return W
