import re, urllib.request, time, io
UA = "turbulence-map probe"
def get(u, rng=None):
    h = {"User-Agent": UA}
    if rng: h["Range"] = rng
    t = time.time()
    with urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=90) as r:
        b = r.read()
    print(f"GET {u[-50:]} {rng or ''} -> {len(b)} bytes in {time.time()-t:.1f}s", flush=True)
    return b
u = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/dafs/prod/dafs.20261127/dafs.t15z.gtg.3km.conus.f003.grib2"
idx = get(u + ".idx").decode().splitlines()
print(len(idx), "records")
print("\n".join(idx))
# decode two records: first and one around 35000 ft
import pygrib, numpy as np
offs = [int(l.split(":")[1]) for l in idx]
for k in [0, len(idx)//2]:
    a, b = offs[k], offs[k+1]-1
    data = get(u, f"bytes={a}-{b}")
    open("/tmp/r.grb2", "wb").write(data)
    g = pygrib.open("/tmp/r.grb2").read(1)[0]
    print(g)
    print("keys:", g.typeOfLevel, g.level, g.shortName, g.name, g.units, g.Ni, g.Nj, g.gridType)
    v = g.values; print("min/max/mean", np.nanmin(v), np.nanmax(v), np.nanmean(v), "masked" , np.ma.count_masked(v))
    lats, lons = g.latlons(); print("corners", lats[0,0], lons[0,0], lats[-1,-1], lons[-1,-1])
    print("hist", np.histogram(np.ma.filled(v, -1), bins=[-1,0,0.05,0.1,0.15,0.2,0.3,0.5,1,5])[0])
