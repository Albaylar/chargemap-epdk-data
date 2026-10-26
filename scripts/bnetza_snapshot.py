#!/usr/bin/env python3
"""Builds the Germany snapshot (Bundesnetzagentur Ladesäulenregister) as 1°×1° tile files.

Source: https://www.bundesnetzagentur.de/ladeinfrastruktur — "Liste der Ladesäulen",
licensed CC BY 4.0 (attribution: Bundesnetzagentur). The page links dated CSV/XLSX files
(Ladesaeulenregister_BNetzA_YYYY-MM-DD.csv|xlsx); the newest one is used.

Output (same station format as the EPDK snapshot, v1):
    data/de/index.json                {"v":1,"generatedAt":..,"source":"BNetzA","sourceDate":"YYYY-MM-DD",
                                       "sourceURL":..,"tileSize":1,"tiles":{"52_13":812, ...}}
    data/de/tiles/<lat>_<lon>.json    {"v":1,"generatedAt":..,"source":"BNetzA","stations":[...]}
Charging devices at the same spot (≈10 m) of the same operator are merged into one station.
Socket kinds: AC_TYPE2, AC_TYPE2_CABLE, AC_SCHUKO, AC_TYPE1, AC_CEE, DC_CCS, DC_CHADEMO, DC_MCS.

Usage:
    python3 scripts/bnetza_snapshot.py                 # find newest file, skip if already converted
    python3 scripts/bnetza_snapshot.py --input file.csv|file.xlsx [--force]
"""
import argparse
import csv
import datetime
import io
import json
import math
import os
import re
import shutil
import sys
import urllib.request

PAGE_URL = "https://www.bundesnetzagentur.de/DE/Fachthemen/ElektrizitaetundGas/E-Mobilitaet/start.html"
FILE_PATTERN = re.compile(
    r"https://data\.bundesnetzagentur\.de/[^\"'\s]*Ladesaeulenregister_BNetzA_(\d{4}-\d{2}-\d{2})\.(csv|xlsx)")
ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "de")
USER_AGENT = "chargemap-epdk-data (daily snapshot; github.com/Albaylar/chargemap-epdk-data)"

PLUG_KINDS = {
    "AC Typ 2 Steckdose": "AC_TYPE2",
    "AC Typ 2 Fahrzeugkupplung": "AC_TYPE2_CABLE",
    "AC Schuko": "AC_SCHUKO",
    "AC Typ 1 Steckdose": "AC_TYPE1",
    "AC CEE 5-polig": "AC_CEE",
    "AC CEE 3-polig": "AC_CEE",
    "DC Fahrzeugkupplung Typ Combo 2 (CCS)": "DC_CCS",
    "DC CHAdeMO": "DC_CHADEMO",
    "DC Megawatt Charging System (MCS)": "DC_MCS",
    "DC Tesla Fahrzeugkupplung (Typ 2)": "DC_CCS",
}


def fetch(url, binary=True):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=300) as response:
        data = response.read()
    return data if binary else data.decode("utf-8", errors="replace")


def newest_source():
    page = fetch(PAGE_URL, binary=False)
    found = {(m.group(1), m.group(2), m.group(0)) for m in FILE_PATTERN.finditer(page)}
    if not found:
        raise SystemExit("No Ladesäulenregister download link found on the BNetzA page")
    # Newest date wins; on the same date prefer CSV (smaller, no extra dependency)
    date, kind, url = max(found, key=lambda f: (f[0], f[1] == "csv"))
    return date, kind, url


def rows_from_csv(data):
    lines = data.decode("utf-8-sig").splitlines()
    header = next(i for i, line in enumerate(lines) if line.startswith("Ladeeinrichtungs-ID"))
    reader = csv.reader(io.StringIO("\n".join(lines[header:])), delimiter=";")
    names = next(reader)
    for row in reader:
        if row and row[0].strip():
            yield dict(zip(names, row))


def rows_from_xlsx(data):
    import openpyxl  # only needed when the newest file is XLSX
    sheet = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
    names = None
    for row in sheet.iter_rows(values_only=True):
        if names is None:
            if row and row[0] == "Ladeeinrichtungs-ID":
                names = [str(c) if c is not None else "" for c in row]
            continue
        if row and row[0] not in (None, ""):
            yield {n: ("" if v is None else str(v)) for n, v in zip(names, row)}


def number(text):
    try:
        return float(str(text).replace(",", ".").strip())
    except ValueError:
        return None


def sockets_of(row):
    """[(kind, kW)] for every plug of every charge point of one charging device."""
    sockets = []
    for k in range(1, 7):
        plugs = [p.strip() for p in (row.get(f"Steckertypen{k}") or "").split(";") if p.strip()]
        powers = [number(p) for p in (row.get(f"Nennleistung Stecker{k}") or "").split(";") if p.strip()]
        for i, plug in enumerate(plugs):
            power = powers[i] if i < len(powers) else (powers[0] if powers else None)
            sockets.append((PLUG_KINDS.get(plug, "DC_CCS" if plug.startswith("DC") else "AC_TYPE2"), power))
    return sockets


def convert(rows):
    sites = {}
    for row in rows:
        if (row.get("Status") or "").strip() not in ("In Betrieb", ""):
            continue
        lat, lon = number(row.get("Breitengrad")), number(row.get("Längengrad"))
        if lat is None or lon is None or not (47.0 <= lat <= 55.5 and 5.5 <= lon <= 15.5):
            continue
        operator = (row.get("Betreiber") or "").strip()
        key = (round(lat, 4), round(lon, 4), operator)
        site = sites.get(key)
        if site is None:
            street = " ".join(p for p in (row.get("Straße", "").strip(), row.get("Hausnummer", "").strip()) if p)
            town = " ".join(p for p in (row.get("Postleitzahl", "").strip(), row.get("Ort", "").strip()) if p)
            site = sites[key] = {
                "n": int(float(row["Ladeeinrichtungs-ID"])),
                "a": (row.get("Standortbezeichnung") or "").strip(),
                "m": (row.get("Anzeigename (Karte)") or "").strip(),
                "o": operator,
                "d": ", ".join(p for p in (street, town) if p),
                "y": round(lat, 6),
                "x": round(lon, 6),
                "_sockets": {},
            }
        site["n"] = min(site["n"], int(float(row["Ladeeinrichtungs-ID"])))
        for kind, power in sockets_of(row):
            site["_sockets"][(kind, power)] = site["_sockets"].get((kind, power), 0) + 1

    stations = []
    for site in sites.values():
        groups = site.pop("_sockets")
        site["s"] = [[kind, power, count] for (kind, power), count in sorted(groups.items(), key=lambda i: str(i))]
        stations.append(site)
    return stations


def write_json_lines(path, header, stations):
    head = json.dumps(header, ensure_ascii=False)[:-1]
    lines = [json.dumps(s, ensure_ascii=False, separators=(",", ":")) for s in stations]
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + ',"stations":[\n' + ",\n".join(lines) + "\n]}\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", help="local CSV/XLSX instead of downloading")
    parser.add_argument("--force", action="store_true", help="rebuild even if this source was already converted")
    args = parser.parse_args()

    index_path = os.path.join(ROOT, "index.json")
    previous = {}
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            previous = json.load(f)

    if args.input:
        kind = "xlsx" if args.input.endswith(".xlsx") else "csv"
        match = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(args.input))
        source_date, source_url = (match.group(1) if match else None), os.path.basename(args.input)
        with open(args.input, "rb") as f:
            data = f.read()
    else:
        source_date, kind, source_url = newest_source()
        if previous.get("sourceURL") == source_url and not args.force:
            print(f"Already up to date ({source_date})", file=sys.stderr)
            return
        data = fetch(source_url)

    stations = convert(rows_from_xlsx(data) if kind == "xlsx" else rows_from_csv(data))
    if len(stations) < 10000:
        raise SystemExit(f"Refusing to write a suspiciously small snapshot ({len(stations)} stations)")

    tiles = {}
    for station in stations:
        tiles.setdefault(f"{math.floor(station['y'])}_{math.floor(station['x'])}", []).append(station)

    generated = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    tile_dir = os.path.join(ROOT, "tiles")
    shutil.rmtree(tile_dir, ignore_errors=True)
    os.makedirs(tile_dir)
    for key, items in tiles.items():
        items.sort(key=lambda s: s["n"])
        write_json_lines(os.path.join(tile_dir, f"{key}.json"),
                         {"v": 1, "generatedAt": generated, "source": "BNetzA"}, items)

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"v": 1, "generatedAt": generated, "source": "BNetzA", "license": "CC BY 4.0",
                   "attribution": "Bundesnetzagentur", "sourceDate": source_date, "sourceURL": source_url,
                   "tileSize": 1, "tiles": {k: len(v) for k, v in sorted(tiles.items())}},
                  f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"Wrote {len(stations)} stations in {len(tiles)} tiles (source {source_date})", file=sys.stderr)


if __name__ == "__main__":
    main()
