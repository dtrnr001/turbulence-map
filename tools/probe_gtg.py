import re, urllib.request, time, sys
UA = "turbulence-map probe"
def get(u, rng=None):
    h = {"User-Agent": UA}
    if rng: h["Range"] = rng
    t = time.time()
    with urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=90) as r:
        b = r.read()
    print(f"GET {u} {rng or ''} -> {len(b)} bytes in {time.time()-t:.1f}s", flush=True)
    return b
def ls(u):
    s = get(u).decode()
    return re.findall(r'href="([^"]+)"[^\n]*?</a>\s*([^\n<]*)', s)
base = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/"
for sub in ["gtgn/", "gtgn/prod/"]:
    try: print(sub, ls(base + sub)[-6:])
    except Exception as e: print(sub, "ERR", e)
day = ls(base + "dafs/prod/")[-1][0]
d = base + "dafs/prod/" + day
cyc = ls(d); print(cyc)
cd = d + [c for c, _ in cyc if re.match(r"\d\d/", c)][-1]
files = ls(cd); print(len(files)); [print(f) for f in files if "gtg" in f[0]][:5]
gtg = [f for f, _ in files if "gtg" in f and f.endswith(".grib2")]
print("gtg files:", gtg[:40])
f0 = cd + gtg[0]
idx = get(f0 + ".idx").decode().splitlines()
print(len(idx), "records"); print("\n".join(idx[:200]))
