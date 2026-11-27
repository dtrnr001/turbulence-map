"""NOAA Graphical Turbulence Guidance (GTG v4) for the Flight profile view.

GTG comes from NCEP's DAFS run every hour as a 3 km CONUS grid with
turbulence (EDR) at every 1,000 ft from the surface to 50,000 ft. Each
forecast hour is about 165 MB, far too big for a phone, so this script:

  * picks the newest run whose forecast hours are all posted,
  * downloads only the "EDPARM" (all turbulence sources combined) records,
    using the .idx inventory and one HTTP byte-range request per hour,
  * shrinks each level onto a 0.5 degree grid (about 30 miles), keeping a
    high percentile of the 3 km points in each box so rough patches stay
    visible without one tiny speck painting the whole box,
  * writes site/gtg.json with one short text string per forecast hour (one
    intensity category per box and level, about 16 KB gzipped per hour).

Altitudes in GTG are heights above mean sea level (not flight levels).
"""
import gzip, json, re, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

NOMADS = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/dafs/prod/"
LIVE = "https://dtrnr001.github.io/turbulence-map/gtg.json"
UA = "turbulence-map/1.0 (github pages snapshot)"
HOURS = 10              # forecast valid times kept: the current hour plus the next 9
LEVEL_STEP_FT = 1000    # every GTG level from the surface ...
TOP_FT = 45000          # ... up to 45,000 ft
LAT0, LAT1, LON0, LON1, D = 24.0, 50.0, -126.0, -65.0, 0.5
# EDR -> category for a medium-size airliner (the thresholds NOAA's GTG
# displays use): 0 smooth < 0.15, 1 light, 2 moderate >= 0.22,
# 3 severe >= 0.34, 4 extreme >= 0.45. One character per box; '.' = no data.
AGG = 0.9               # per 0.5 degree box: 90th percentile of the 3 km points ("max" = strongest point)
CATS = [0.15, 0.22, 0.34, 0.45]
CAT_NAMES = ["smooth", "light", "moderate", "severe", "extreme"]


def _get(url, rng=None, tries=3):
    h = {"User-Agent": UA}
    if rng:
        h["Range"] = f"bytes={rng[0]}-{rng[1]}"
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=120) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            print(f"GTG retry {url[-45:]}: {e}", file=sys.stderr)
            time.sleep(5 * (i + 1))


def _runs():
    """Newest DAFS runs first: [(run datetime, day url), ...]"""
    days = sorted(re.findall(r'href="(dafs\.\d{8}/)"', _get(NOMADS).decode()), reverse=True)[:2]
    runs = []
    for day in days:
        listing = _get(NOMADS + day).decode()
        for hh in sorted(set(re.findall(r"dafs\.t(\d\d)z\.gtg\.3km\.conus\.f000\.grib2\.idx", listing)), reverse=True):
            fhs = set(int(x) for x in re.findall(rf"dafs\.t{hh}z\.gtg\.3km\.conus\.f(\d\d\d)\.grib2\.idx", listing))
            run = datetime.strptime(day[5:13] + hh, "%Y%m%d%H").replace(tzinfo=timezone.utc)
            runs.append((run, NOMADS + day, hh, fhs))
    return runs


def _pick_run():
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for run, url, hh, fhs in _runs():
        first = int((now - run).total_seconds() // 3600)
        need = set(range(first, first + HOURS))
        if first >= 0 and need <= fhs:
            return run, url, hh, sorted(need)
    raise RuntimeError("no GTG run with the needed forecast hours yet")


def write_gtg(site):
    out = Path(site) / "gtg.json"
    try:
        run, url, hh, fhs = _pick_run()
    except Exception as e:
        print(f"GTG: couldn't list runs ({e}); reusing the live copy if there is one")
        return _reuse(out, None)
    if _reuse(out, run):
        return
    try:
        _build(out, run, url, hh, fhs)
    except Exception as e:
        print(f"GTG: couldn't build run {run:%H}Z ({e}); keeping the previous forecast", file=sys.stderr)
        _reuse(out, None)


def _build(out, run, url, hh, fhs):
    import numpy as np, pygrib  # only needed when there's a new run to process

    nlat, nlon = round((LAT1 - LAT0) / D), round((LON1 - LON0) / D)
    levels = list(range(0, TOP_FT + 1, LEVEL_STEP_FT))
    order = starts = cells = counts = sb_sorted = None
    hours = []
    t0 = time.time()
    for fh in fhs:
        f = f"{url}dafs.t{hh}z.gtg.3km.conus.f{fh:03d}.grib2"
        idx = _get(f + ".idx").decode().splitlines()
        offs = [int(l.split(":")[1]) for l in idx] + [None]
        recs = {}
        for i, line in enumerate(idx):
            p = line.split(":")
            m = re.match(r"(\d+) m above mean sea level", p[4])
            if p[3] == "EDPARM" and m:
                recs[int(m.group(1))] = (offs[i], offs[i + 1] - 1)
        # GTG's levels are 1000 ft apart in metres (30, 304, 609 ...): match each wanted ft level to the nearest
        pick = []
        for ft in levels:
            m = min(recs, key=lambda x: abs(x / 0.3048 - ft))
            if abs(m / 0.3048 - ft) > 200:
                raise RuntimeError(f"GTG f{fh:03d} has no level near {ft} ft")
            pick.append(recs[m])
        lo, hi = min(a for a, _ in pick), max(b for _, b in pick)
        blob = _get(f, (lo, hi))
        cols = np.full((len(levels), nlat * nlon), -1.0, dtype=np.float32)
        for k, (a, b) in enumerate(pick):
            g = pygrib.fromstring(blob[a - lo:b - lo + 1])
            v = np.ma.filled(g.values.astype(np.float32), -1.0).ravel()
            if order is None:
                lats, lons = g.latlons()
                lats, lons = lats.ravel(), ((lons.ravel() + 180) % 360) - 180
                i = np.floor((lats - LAT0) / D).astype(int)
                j = np.floor((lons - LON0) / D).astype(int)
                ok = (i >= 0) & (i < nlat) & (j >= 0) & (j < nlon)
                box = np.where(ok, i * nlon + j, -1)
                order = np.argsort(box, kind="stable")
                sb = box[order]
                first = np.searchsorted(sb, 0)
                order, sb = order[first:], sb[first:]
                cells, starts, counts = np.unique(sb, return_index=True, return_counts=True)
                sb_sorted = sb
            if AGG == "max":
                cols[k, cells] = np.maximum.reduceat(v[order], starts)
            else:  # a high percentile: rough patches still show, single 3 km specks don't paint a whole box
                vs = v[order]
                srt = np.lexsort((vs, sb_sorted))
                cols[k, cells] = vs[srt][starts + np.floor(AGG * (counts - 1)).astype(int)]
            # a box only counts if it has data: native points outside the GTG domain are -1
        q = np.where(cols < 0, 5, np.digitize(cols, CATS))
        lut = np.array(list("01234."))
        s = "".join(lut[q.T.ravel()])   # box by box, each box listing its levels bottom to top
        valid = run + timedelta(hours=fh)
        hours.append({"valid": valid.strftime("%Y-%m-%dT%H:%MZ"), "fh": fh, "cat": s})
        print(f"GTG f{fh:03d}: {len(blob)/1e6:.0f} MB in, {len(s)/1e3:.0f} k chars out ({time.time()-t0:.0f}s)")
    data = {
        "source": "NOAA/NWS NCEP Graphical Turbulence Guidance (GTG v4), DAFS 3 km CONUS",
        "run": run.strftime("%Y-%m-%dT%H:%MZ"),
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "field": "EDPARM: eddy dissipation rate, all turbulence sources (m^2/3 s^-1)",
        "boxValue": "strongest 3 km point" if AGG == "max" else f"{round(AGG * 100)}th percentile of the 3 km points",
        "altitude": "feet above mean sea level",
        "grid": {"lat0": LAT0, "lon0": LON0, "d": D, "nlat": nlat, "nlon": nlon},
        "levelsFt": levels, "categories": CAT_NAMES, "edrFrom": CATS, "aircraft": "medium (airliner-size)", "missing": ".",
        "hours": hours,
    }
    txt = json.dumps(data, separators=(",", ":"))
    out.write_text(txt)
    print(f"wrote GTG run {data['run']} with {len(hours)} hours: {len(txt)/1e6:.1f} MB, {len(gzip.compress(txt.encode()))/1e3:.0f} KB gzipped")


def _reuse(out, run):
    """Copy the live gtg.json if it is from this run (or if we can't tell)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(LIVE, headers={"User-Agent": UA}), timeout=20) as r:
            prev = json.loads(r.read())
        if run is None or prev.get("run") == run.strftime("%Y-%m-%dT%H:%MZ"):
            out.write_text(json.dumps(prev, separators=(",", ":")))
            print(f"GTG: reused run {prev.get('run')}")
            return True
    except Exception as e:
        print(f"GTG: no reusable live copy ({e})")
    return False


if __name__ == "__main__":
    write_gtg(sys.argv[1] if len(sys.argv) > 1 else "site")
