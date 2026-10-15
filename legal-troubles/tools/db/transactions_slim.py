#!/usr/bin/env python3
"""Write data/db/transactions/dashboard.json: log.json limited to the last 7 days (by row timestamp, counted back from log asOf).
The dashboard DB doc (transactions/current) shows only this window. Complete history is stored in the DB as per-week docs
(transactions/week-N + archive-meta, from transactions_weeks.py) and in GitHub (raw.json/log.json), pulled on request."""
import json, os, collections, datetime
d = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'db', 'transactions')
L = json.load(open(os.path.join(d, 'log.json')))
F = '%Y-%m-%dT%H:%M:%SZ'
cut = (datetime.datetime.strptime(L['asOf'], F) - datetime.timedelta(days=7)).strftime(F)
keep = [r for r in L['rows'] if r.get('ts') and r['ts'] >= cut]
out = dict(L, rows=keep)
out['kinds'] = dict(collections.Counter(r['kind'] for r in keep))
cl = collections.Counter(r['result'] for r in keep if r['kind'] == 'claim')
out['claims'] = {k: cl.get(k, 0) for k in ('won', 'lost', 'canceled', 'pending')}
out['lostWithoutProvenWinner'] = sum(1 for r in keep if r['kind'] == 'claim' and r['result'] == 'lost' and not r.get('wonBy'))
out['windowDays'] = 7
out['windowFrom'] = cut
out['notes'] = list(L['notes']) + [f"Dashboard shows the last 7 days only (from {cut}). Complete history is stored in the database as week docs and in GitHub; ask the front office for older moves."]
json.dump(out, open(os.path.join(d, 'dashboard.json'), 'w'), separators=(',', ':'))
print('last 7 days from', cut, 'rows', len(keep), 'of', len(L['rows']), out['claims'], out['kinds'])
