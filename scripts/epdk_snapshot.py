#!/usr/bin/env python3
"""Builds the compact EPDK charging-station snapshot the app reads (epdk_stations.json).

Source: EPDK "Şarj İstasyonları" API gateway (public stations of licensed charge network
operators). The gateway enforces a strict quota (roughly one full download per day per
client), so the app never calls it directly: run this script once a day (CI job) or before
a release, and publish/bundle the output.

Usage:
    python3 scripts/epdk_snapshot.py                         # download + write bundled file
    python3 scripts/epdk_snapshot.py --input raw.json        # convert a saved raw response
    python3 scripts/epdk_snapshot.py --output /tmp/epdk.json

Output format (v1):
    {"v":1,"generatedAt":"<ISO8601>","source":"EPDK","stations":[
        {"n":7918,"a":"<station name>","m":"<brand>","o":"<operator legal name>",
         "d":"<address>","y":<lat>,"x":<lon>,"s":[["AC_TYPE2",22.0,2], ...]}]}
    "s" groups identical sockets: [socket kind, power kW, count]. Only HALKA_ACIK (public)
    stations inside Türkiye's bounding box are kept.
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

API_URL = "https://apigateway.epdk.gov.tr/sarjIstasyonlari/"
DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "..", "ChargeStationMap", "epdk_stations.json")


def download():
    request = urllib.request.Request(
        API_URL, data=b"{}", method="GET",
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "chargemap-epdk-data (daily snapshot)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise SystemExit(f"EPDK request failed: HTTP {error.code} {error.read()[:300]!r}")
    if "data" not in payload:
        raise SystemExit(f"Unexpected EPDK response (quota?): {str(payload)[:300]}")
    return payload


def parse_power(value):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def convert(payload):
    stations = []
    for row in payload["data"]:
        if row.get("hizmetSekli") != "HALKA_ACIK":
            continue
        lat, lon = row.get("enlem"), row.get("boylam")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        if not (35.5 <= lat <= 42.5 and 25.5 <= lon <= 45.0):
            continue
        digits = re.sub(r"\D", "", row.get("sarjIstasyonuNo") or "")
        if not digits:
            continue
        sockets = {}
        for socket in row.get("soketler") or []:
            key = (socket.get("soketTuru") or socket.get("soketTipi") or "?", parse_power(socket.get("soketGucu")))
            sockets[key] = sockets.get(key, 0) + 1
        stations.append({
            "n": int(digits),
            "a": (row.get("sarjIstasyonuAdi") or "").strip(),
            "m": (row.get("marka") or "").strip(),
            "o": (row.get("sarjAgiIsletmecisiUnvan") or "").strip(),
            "d": " ".join((row.get("adres") or "").split()),
            "y": round(lat, 6),
            "x": round(lon, 6),
            "s": [[kind, power, count] for (kind, power), count in sorted(sockets.items(), key=lambda i: str(i))],
        })
    stations.sort(key=lambda s: s["n"])
    return {
        "v": 1,
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
        "source": "EPDK",
        "stations": stations,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", help="raw EPDK response saved earlier (skips the download)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if args.input:
        with open(args.input, encoding="utf-8") as f:
            payload = json.load(f)
    else:
        payload = download()

    snapshot = convert(payload)
    if len(snapshot["stations"]) < 1000:
        raise SystemExit(f"Refusing to write a suspiciously small snapshot ({len(snapshot['stations'])} stations)")

    # Keep the old file (and its timestamp) when the station data didn't change, so the
    # daily job only commits real updates.
    try:
        with open(args.output, encoding="utf-8") as f:
            if json.load(f).get("stations") == snapshot["stations"]:
                print("Station data unchanged; snapshot left as is", file=sys.stderr)
                return
    except (OSError, ValueError):
        pass

    # One station per line keeps git diffs (and repo growth) small for the daily updates.
    header = json.dumps({k: snapshot[k] for k in ("v", "generatedAt", "source")}, ensure_ascii=False)[:-1]
    lines = [json.dumps(s, ensure_ascii=False, separators=(",", ":")) for s in snapshot["stations"]]
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(header + ',"stations":[\n' + ",\n".join(lines) + "\n]}\n")
    print(f"Wrote {len(snapshot['stations'])} stations to {os.path.normpath(args.output)}", file=sys.stderr)


if __name__ == "__main__":
    main()
