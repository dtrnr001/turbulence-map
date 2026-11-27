import re, urllib.request, time
UA = "turbulence-map probe"
def get(u, rng=None, n=None):
    h = {"User-Agent": UA}
    if rng: h["Range"] = rng
    t = time.time()
    with urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=60) as r:
        b = r.read() if n is None else r.read(n)
    print(f"GET {u} {rng or ''} -> {len(b)} bytes in {time.time()-t:.1f}s")
    return b
base = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/"
idx = get(base).decode()
print([x for x in re.findall(r'href="([^"]+)"', idx)])
for sub in ["dafs/prod/", "gtg/prod/"]:
    try:
        print(sub, re.findall(r'href="([^"]+)"', get(base + sub).decode())[-10:])
    except Exception as e:
        print(sub, "ERR", e)
