# chargemap-epdk-data

Daily snapshot of Türkiye's public EV charging stations, as published by EPDK
(Enerji Piyasası Düzenleme Kurumu), in the compact format the ChargeStationMap iOS app reads.

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

## Notes

- The EPDK gateway enforces a strict quota (about one full download per day per client), which is
  why apps should read this mirror instead of calling EPDK directly.
- Data © EPDK. This repository only reformats the publicly published registry; check EPDK's terms
  before commercial reuse.
