# League database – ESPN league 293318, season 2026

Built Oct 8, 2026. Source: ESPN fantasy API (lm-api-reads), read-only pulls.

- `weeks/wNN/` – frozen, create-only. Weeks 1–4 complete.
  - `pool.json` – player pool with weekly actuals (1,052 players)
  - `matchups_all.json` – full schedule and scores as of the pull
  - `roster.json` – each team's roster and lineup slots for that week
  - `boxscore.json` – team totals for that week
- `league/` – settings, teams, standings, nav, status, transactions, draft, positional ratings, NFL schedule (snapshot, overwritten on refresh)
- `current/` – week 5 in progress (not frozen): roster and boxscore
- `MANIFEST.json` – file sizes and sha256 for every file
- `manifest*.json` – per-week pull log

Rule: ESPN corrections after a week is frozen are ignored (Joe, Oct 8).

## Notes (Oct 8, 2026)
- `players_week.json` per week: every player's actual (and ESPN projection as returned Oct 8) in league scoring. Starter actuals reconcile to ESPN's team score for all 56 team-games in weeks 1–4.
- Known defect: `pool.json` for weeks 1 and 2 carries almost no weekly stats (pulled with too short a stats window). Fixed by adding `pool_full.json` to w01 and w02 (668 and 671 players with that week's actuals, identical to `players_week.json`). The original `pool.json` files are frozen and left as they were. `players_week.json` is the easiest file to use.
- ESPN's stats filter `value=N` returns the N most recent scoring periods, so `db_pull.py` now asks for all periods up to the current one.
- Projections for weeks 1–3 are ESPN's current stored values, not necessarily the pre-game projections.
- Per-game box scores and play-by-play for weeks 1–4: `../rg/raw/2026-wNN-summaries.json.gz`.
- `plans.json`: Joe's plan picks (empty).
- Weekly freeze: `../../tools/db/db_pull.py <week>` (create-only, fails if team scores don't reconcile).
