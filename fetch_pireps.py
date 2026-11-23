#!/usr/bin/env python3
"""Fetch recent turbulence PIREPs from NOAA AWC and write site/pirep.json.

Run by the GitHub Actions workflow every few minutes. AWC returns at most
400 reports per request, so the US area is split into boxes and merged.
"""
import json, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

AWC = "https://aviationweather.gov/api/data/pirep"
UA = "turbulence-map/1.0 (github pages snapshot)"
AGE_HOURS = 6
LIMIT = 400
# minLat,minLon,maxLat,maxLon covering CONUS, Alaska, Hawaii and nearby oceanic airspace
BOXES = [
    (15, -180, 72, -130),  # Alaska, Hawaii, Pacific
    (15, -130, 40, -105),  # SW
    (40, -130, 60, -105),  # NW
    (15, -105, 40, -90),   # S central
    (40, -105, 60, -90),   # N central
    (15, -90, 36, -50),    # SE + Atlantic
    (36, -90, 60, -50),    # NE + Atlantic
]


def get(box):
    q = f"format=json&type=turb&age={AGE_HOURS}&bbox={','.join(map(str, box))}"
    req = urllib.request.Request(f"{AWC}?{q}", headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                body = r.read()
                return json.loads(body) if body.strip() else []
        except urllib.error.HTTPError as e:
            if e.code == 204:
                return []
            print(f"box {box}: HTTP {e.code}", file=sys.stderr)
        except Exception as e:
            print(f"box {box}: {e}", file=sys.stderr)
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"failed to fetch box {box}")


def main(out):
    seen, reports, truncated, failures = set(), [], False, 0
    for box in BOXES:
        try:
            rows = get(box)
        except RuntimeError:
            failures += 1
            continue
        if len(rows) >= LIMIT:
            truncated = True
        for p in rows:
            key = (p.get("rawOb"), p.get("obsTime"), p.get("lat"), p.get("lon"))
            if key in seen:
                continue
            seen.add(key)
            reports.append(p)
        time.sleep(1)
    if failures == len(BOXES):
        sys.exit("every AWC request failed; keeping the previous snapshot")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ageHours": AGE_HOURS,
        "truncated": truncated,
        "count": len(reports),
        "reports": reports,
    }, separators=(",", ":")))
    if reports:
        print("sample report:", json.dumps(reports[0])[:1500])
    print(f"wrote {len(reports)} reports to {out} (truncated={truncated}, failed boxes={failures})")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "site/pirep.json")
