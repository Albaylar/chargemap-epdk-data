# chargemap-epdk-data

Daily snapshots of official public EV charging-station registries, in the compact format the
ChargeStationMap iOS app reads:

| Country | Source | File(s) | License |
|---|---|---|---|
| Türkiye | EPDK (Enerji Piyasası Düzenleme Kurumu) | `data/epdk_stations.json` | see notes |
| Germany | Bundesnetzagentur, Ladesäulenregister | `data/de/index.json` + `data/de/tiles/<lat>_<lon>.json` (1°×1°) | CC BY 4.0 — © Bundesnetzagentur |

## Türkiye (EPDK)

- **File:** [`data/epdk_stations.json`](data/epdk_stations.json)
- **Raw URL used by the app:** `https://raw.githubusercontent.com/Albaylar/chargemap-epdk-data/main/data/epdk_stations.json`
- **Updated:** daily by [GitHub Actions](.github/workflows/update.yml) (only committed when the data changes)
- **Source:** EPDK "Şarj İstasyonları" API gateway — only stations with service type `HALKA_ACIK` (public)

## Format (v1)

```json
{"v": 1, "generatedAt": "2026-10-26T10:18:01+00:00", "source": "EPDK", "stations": [
{"n": 7918, "a": "station name", "m": "brand", "o": "operator legal name",
 "d": "address", "y": 39.9197, "x": 32.8605, "s": [["AC_TYPE2", 22.0, 2]]}
]}
```

`s` groups identical sockets as `[kind, powerKW, count]`; kinds are `AC_TYPE2`, `DC_CCS`, `DC_CHADEMO`.

## Germany (Bundesnetzagentur)

- **Source page:** https://www.bundesnetzagentur.de/ladeinfrastruktur — newest dated `Ladesaeulenregister_BNetzA_*.csv|xlsx`
- **Raw base URL used by the app:** `https://raw.githubusercontent.com/Albaylar/chargemap-epdk-data/main/data/de/`
- Charging devices at the same spot (~10 m) of the same operator are merged into one station.
- Socket kinds: `AC_TYPE2`, `AC_TYPE2_CABLE`, `AC_SCHUKO`, `AC_TYPE1`, `AC_CEE`, `DC_CCS`, `DC_CHADEMO`, `DC_MCS`.
- Data © Bundesnetzagentur, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); reformatted (merged per site, tiled).

## Notes

- The EPDK gateway enforces a strict quota (about one full download per day per client), which is
  why apps should read this mirror instead of calling EPDK directly.
- EPDK data © EPDK. This repository only reformats the publicly published registry; check EPDK's terms
  before commercial reuse.
