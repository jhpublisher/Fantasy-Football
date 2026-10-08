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
