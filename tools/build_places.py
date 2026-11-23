#!/usr/bin/env python3
"""Build site/places.json: named airports used to describe where a report is
("near El Paso Intl, TX"). Run occasionally via the build-places workflow.
AWC stationinfo returns at most 400 stations per request, so we tile the area.
"""
import json, time, urllib.request, urllib.error
from pathlib import Path

UA = "turbulence-map/1.0 (places builder)"
STEP = 4
places = {}
for lat in range(14, 74, STEP):
    for lon in range(-180, -48, STEP):
        bbox = f"{lat},{lon},{lat+STEP},{lon+STEP}"
        url = f"https://aviationweather.gov/api/data/stationinfo?bbox={bbox}&format=json"
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=40) as r:
                    body = r.read()
                rows = json.loads(body) if body.strip() else []
                break
            except urllib.error.HTTPError as e:
                rows = [] if e.code == 204 else None
                if rows is not None:
                    break
            except Exception:
                rows = None
            time.sleep(3)
        if rows is None:
            print("failed", bbox)
            continue
        if len(rows) >= 400:
            print("capped", bbox)
        for s in rows:
            if not s.get("icaoId") or not s.get("site") or "METAR" not in (s.get("siteType") or []):
                continue
            places[s["icaoId"]] = [round(s["lat"], 3), round(s["lon"], 3), s["site"].strip(), s.get("state") or "", s.get("priority") or 9]
        time.sleep(0.7)

out = Path(__file__).resolve().parent.parent / "site" / "places.json"
out.write_text(json.dumps(places, separators=(",", ":")))
print(f"wrote {len(places)} places to {out}")
