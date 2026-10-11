#!/usr/bin/env python3
"""Write data/db/transactions/dashboard.json: log.json limited to the current and previous NFL week.
The dashboard DB doc (transactions/current) has a 262,144-byte cap; full history stays in raw.json/log.json (GitHub)."""
import json, os, collections
d = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'db', 'transactions')
L = json.load(open(os.path.join(d, 'log.json')))
cur = max(r['week'] for r in L['rows'] if r.get('week') is not None)
keep = [r for r in L['rows'] if r.get('week') is not None and r['week'] >= cur - 1]
out = dict(L, rows=keep)
out['kinds'] = dict(collections.Counter(r['kind'] for r in keep))
cl = collections.Counter(r['result'] for r in keep if r['kind'] == 'claim')
out['claims'] = {k: cl.get(k, 0) for k in ('won', 'lost', 'canceled', 'pending')}
out['lostWithoutProvenWinner'] = sum(1 for r in keep if r['kind']=='claim' and r['result']=='lost' and not r.get('wonBy'))
out['windowWeeks'] = [cur - 1, cur]
out['notes'] = list(L['notes']) + [f"Dashboard copy holds weeks {cur-1}-{cur} only. Full history is kept in GitHub (raw.json/log.json) and answered on request."]
json.dump(out, open(os.path.join(d, 'dashboard.json'), 'w'), separators=(',', ':'))
print('weeks', cur-1, cur, 'rows', len(keep), 'of', len(L['rows']), out['claims'], out['kinds'])
