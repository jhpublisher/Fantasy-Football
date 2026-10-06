# Legal Troubles front office site
- `index.html`: BI dashboard (reads `data/bundle.json`)
- `briefing.html`: CEO Briefing
- `data/bundle.json`: rebuilt every 3 hours by `.github/workflows/legal-troubles-refresh.yml` (ESPN numbers, playoff odds, news sweep)
- `curated/`: the front office's analysis (Market Watch tags, claim odds, rumor mill, GM memos, watch list). Updated by the team's scheduled runs; any change here triggers a rebuild.
- `tools/`: the Python scripts the workflow runs.
