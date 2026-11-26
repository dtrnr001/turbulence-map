#!/usr/bin/env python3
"""Fetch recent turbulence PIREPs, G-AIRMETs and International SIGMETs from
NOAA AWC and write site/pirep.json, site/gairmet.json and site/isigmet.json.

Run by the GitHub Actions workflow every few minutes. AWC returns at most
400 reports per request, so the US area is split into boxes and merged.
"""
import json, sys, time, urllib.request, urllib.error, urllib.parse
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


def get_geojson(product):
    """Fetch a GeoJSON product (gairmet, isigmet). Returns None on failure."""
    req = urllib.request.Request(f"https://aviationweather.gov/api/data/{product}?format=geojson",
                                 headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                body = r.read()
                return json.loads(body) if body.strip() else {"type": "FeatureCollection", "features": []}
        except urllib.error.HTTPError as e:
            if e.code == 204:
                return {"type": "FeatureCollection", "features": []}
            print(f"{product}: HTTP {e.code}", file=sys.stderr)
        except Exception as e:
            print(f"{product}: {e}", file=sys.stderr)
        time.sleep(3 * (attempt + 1))
    return None


def write_overlays(site):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for product in ("gairmet", "isigmet"):
        fc = get_geojson(product)
        if fc is None:
            # Still publish an empty file so the page can say the layer is unavailable.
            fc = {"type": "FeatureCollection", "features": [], "error": "fetch failed"}
        fc["fetchedAt"] = now
        (site / f"{product}.json").write_text(json.dumps(fc, separators=(",", ":")))
        print(f"wrote {len(fc.get('features', []))} {product} features")
        time.sleep(1)


WINDS_MAX_AGE_H = 3
LIVE_WINDS = "https://dtrnr001.github.io/turbulence-map/winds.json"


# Wind levels: key in winds.json -> Open-Meteo variable suffix
WIND_LEVELS = {"250": "250hPa", "700": "700hPa", "sfc": "10m"}


def write_winds(site):
    """Winds at three altitudes on a 3-degree grid from Open-Meteo's GFS
    (free, non-commercial, CC BY 4.0): 250 hPa (about 34,000 ft), 700 hPa
    (about 10,000 ft) and 10 m above the ground. Refetched only every few
    hours to stay well inside the free daily limit; otherwise the live copy
    is reused."""
    out = site / "winds.json"
    try:
        with urllib.request.urlopen(urllib.request.Request(LIVE_WINDS, headers={"User-Agent": UA}), timeout=20) as r:
            prev = json.loads(r.read())
        age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(prev["fetchedAt"])).total_seconds() / 3600
        if age_h < WINDS_MAX_AGE_H and set(prev.get("levels", {})) == set(WIND_LEVELS):
            out.write_text(json.dumps(prev, separators=(",", ":")))
            print(f"reused winds from {age_h:.1f} h ago")
            return
    except Exception as e:
        print(f"no reusable winds ({e})")
    grid = [(lat, lon) for lat in range(24, 52, 3) for lon in range(-126, -64, 3)]
    hourly = ",".join(f"wind_{v}_{suf}" for suf in WIND_LEVELS.values() for v in ("speed", "direction"))
    levels, times = {k: [] for k in WIND_LEVELS}, None
    rnd = lambda a: [None if x is None else round(x) for x in a]  # whole knots and degrees keep the file small
    for i in range(0, len(grid), 60):
        chunk = grid[i:i + 60]
        q = urllib.parse.urlencode({
            "latitude": ",".join(str(a) for a, _ in chunk), "longitude": ",".join(str(b) for _, b in chunk),
            "hourly": hourly, "wind_speed_unit": "kn",
            "forecast_days": 2, "timezone": "UTC",
        })
        try:
            req = urllib.request.Request(f"https://api.open-meteo.com/v1/gfs?{q}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                rows = json.loads(r.read())
        except Exception as e:
            print(f"winds chunk failed: {e}", file=sys.stderr)
            return  # keep the site working without winds rather than publish a partial grid
        rows = rows if isinstance(rows, list) else [rows]
        for (lat, lon), row in zip(chunk, rows):
            h = row["hourly"]
            times = times or h["time"]
            for k, suf in WIND_LEVELS.items():
                levels[k].append([lat, lon, rnd(h[f"wind_speed_{suf}"]), rnd(h[f"wind_direction_{suf}"])])
        time.sleep(1)
    out.write_text(json.dumps({
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": "GFS via Open-Meteo",
        "levelNames": {"250": "250 hPa (about 34,000 ft)", "700": "700 hPa (about 10,000 ft)", "sfc": "10 m above ground"},
        "times": times, "levels": levels,
    }, separators=(",", ":")))
    print(f"wrote winds at {len(levels)} levels for {len(grid)} grid points")


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
    write_overlays(out.parent)
    write_winds(out.parent)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "site/pirep.json")
