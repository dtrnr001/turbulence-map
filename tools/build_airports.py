#!/usr/bin/env python3
"""Build site/airports.json: airports worldwide with airline service, for "My flight".
Source: OurAirports (public domain), https://ourairports.com/data/
Keeps large and medium airports that have an IATA code and scheduled service.
Format: {"LHR": [lat, lon, name, city, country, icao], ...}
"""
import csv, io, json, urllib.request
from pathlib import Path

URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
req = urllib.request.Request(URL, headers={"User-Agent": "turbulence-map/1.0 (airports builder)"})
with urllib.request.urlopen(req, timeout=60) as r:
    text = r.read().decode("utf-8")

out = {}
for row in csv.DictReader(io.StringIO(text)):
    iata = (row.get("iata_code") or "").strip().upper()
    if len(iata) != 3 or not iata.isalpha():
        continue
    if row["type"] not in ("large_airport", "medium_airport") or row.get("scheduled_service") != "yes":
        continue
    icao = (row.get("icao_code") or row.get("gps_code") or row.get("ident") or "").strip().upper()
    entry = [round(float(row["latitude_deg"]), 3), round(float(row["longitude_deg"]), 3),
             row["name"].strip(), (row.get("municipality") or "").strip(), row["iso_country"], icao]
    # if two airports share an IATA code, keep the large one
    if iata in out and row["type"] != "large_airport":
        continue
    out[iata] = entry

dest = Path(__file__).resolve().parent.parent / "site" / "airports.json"
dest.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
print(f"wrote {len(out)} airports, {dest.stat().st_size // 1024} KB")
for code in ("LHR", "CDG", "NRT", "SYD", "DXB", "GRU", "JFK"):
    print(code, out.get(code))
