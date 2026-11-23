# Live turbulence PIREP map

A Leaflet map of recent US pilot reports (PIREPs) of turbulence from NOAA's
[Aviation Weather Center data API](https://aviationweather.gov/data/api/),
colored by intensity, with altitude/time details and filters.

AWC doesn't allow cross-origin browser requests, so a GitHub Actions job
(`.github/workflows/update.yml`) fetches the last 6 hours of turbulence reports
every ~5 minutes (`fetch_pireps.py`), writes `site/pirep.json`, and deploys
`site/` to GitHub Pages. The page re-reads that file every 2 minutes.

Run locally instead: `python3 serve.py`, then open http://localhost:8765
(serves `site/` and proxies `/api/pirep` to AWC).

Scheduled workflows in a public repo pause after 60 days without repository
activity; re-enable from the Actions tab if that happens.
