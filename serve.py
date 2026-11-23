#!/usr/bin/env python3
"""Tiny local server for the live turbulence PIREP map.

Serves index.html and proxies /api/pirep to NOAA's Aviation Weather Center
so the browser never has to make a cross-origin request.

    python3 serve.py          # then open http://localhost:8765
    python3 serve.py 9000     # pick another port

Standard library only. Responses are cached for 60 seconds so several open
tabs don't hammer AWC.
"""
import sys, time, urllib.request, urllib.parse, webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

AWC = "https://aviationweather.gov/api/data/pirep"
ALLOWED = {"format", "type", "age", "level", "inten", "id", "distance", "date", "bbox"}
CACHE_SECONDS = 60
HERE = Path(__file__).resolve().parent
_cache = {}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE / "site"), **kw)

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path.rstrip("/") == "/api/pirep":
            return self.proxy(url.query)
        return super().do_GET()

    def proxy(self, query):
        params = {k: v for k, v in urllib.parse.parse_qsl(query) if k in ALLOWED}
        params.setdefault("format", "json")
        qs = urllib.parse.urlencode(sorted(params.items()))
        hit = _cache.get(qs)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            status, body = hit[1], hit[2]
        else:
            req = urllib.request.Request(f"{AWC}?{qs}", headers={"User-Agent": "turbulence-map/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    status, body = r.status, r.read()
            except urllib.error.HTTPError as e:
                status, body = e.code, e.read()
            except Exception as e:  # network error
                status, body = 502, str(e).encode()
            if status in (200, 204):
                _cache[qs] = (time.time(), status, body)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        if "/api/pirep" in (args[0] if args else ""):
            sys.stderr.write("%s  %s\n" % (time.strftime("%H:%M:%S"), fmt % args))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    link = f"http://localhost:{port}"
    print(f"Turbulence map running at {link}  (Ctrl+C to stop)")
    try:
        webbrowser.open(link)
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
