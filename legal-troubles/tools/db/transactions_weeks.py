#!/usr/bin/env python3
"""Split log.json into one doc per NFL week (data/db/transactions/weeks/week-N.json) + archive-meta.json.
Each doc is far under the DB's 262,144-byte per-document cap. Load: ArtifactData batch, collection transactions, doc ids week-N and archive-meta."""
import json, os, collections
d = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'db', 'transactions')
L = json.load(open(os.path.join(d, 'log.json')))
os.makedirs(os.path.join(d, 'weeks'), exist_ok=True)
by = collections.defaultdict(list)
for r in L['rows']: by[r.get('week')].append(r)
meta = {k: v for k, v in L.items() if k != 'rows'}
meta['weeks'] = {}
for w, rows in sorted(by.items(), key=lambda x: (x[0] is None, x[0])):
    name = f"week-{w}" if w is not None else "week-none"
    doc = {'weekDoc': True, 'week': w, 'asOf': L['asOf'], 'leagueId': L['leagueId'], 'season': L['season'], 'rows': rows}
    json.dump(doc, open(os.path.join(d, 'weeks', name + '.json'), 'w'), separators=(',', ':'))
    meta['weeks'][name] = len(rows)
json.dump(meta, open(os.path.join(d, 'weeks', 'archive-meta.json'), 'w'), separators=(',', ':'))
print({k: v for k, v in meta['weeks'].items()}, 'total', sum(meta['weeks'].values()), 'of', len(L['rows']))
