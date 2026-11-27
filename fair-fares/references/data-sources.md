# Data sources

Built by `scripts/update_data.py` on 2026-11-27. Exact dates, row counts and filters are also in `assets/data/meta.json` (rewritten on every update).

| File | Source | Licence | Source date | Filter / notes |
|---|---|---|---|---|
| countries.json, states.json | [countries-states-cities-database](https://github.com/dr5hn/countries-states-cities-database) (`csv/countries.csv`, `csv/states.csv`) | ODbL-1.0 | 2026-11-24 (last commit) | 250 countries; 3,895 first-level regions (sub-regions dropped) |
| currencies.json | same `countries.csv` (currency, name, symbol) | ODbL-1.0 | 2026-11-24 | 154 currencies; maps home country → default currency |
| cities.json | [GeoNames cities15000](https://download.geonames.org/export/dump/) + `admin1CodesASCII.txt` | CC BY 4.0 (credit: GeoNames) | 2026-11-27 (download; GeoNames updates daily) | 34,248 cities with population ≥ 15,000. The CSC database has no population field, so GeoNames supplies "larger cities"; region names come from GeoNames admin1 and can differ slightly from CSC spellings |
| airports.json | [OurAirports](https://github.com/davidmegginson/ourairports-data) `airports.csv` | Public domain | 2026-11-27 | 4,132 airports with `scheduled_service=yes`, an IATA code and not closed; size 3 = large, 2 = medium, 1 = small |
| visa.json | [Passport Index dataset](https://github.com/ilyankou/passport-index-dataset) `passport-index-tidy-iso2.csv` (fork [imorte/passport-index-data](https://github.com/imorte/passport-index-data) also checked; the newer one wins) | MIT (data from passportindex.org) | **2026-02-18** (newest available upstream on 2026-11-27) | 39,601 passport→destination pairs. Values: number = visa-free days, VF, VOA, EV, ETA, VR, NA, SELF |
| doc_rules.json | Hand-curated for this skill from official government sites listed per destination | MIT (this repo) | reviewed 2026-11-27 | Fees and processing times are rough estimates and are always re-verified during the search |
| fx.json (runtime) | [ECB euro reference rates](https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml) | ECB reuse policy (free with source credit) | fetched at each run | ~30 currencies; others are recorded by hand |

Attribution: "Contains information from GeoNames (geonames.org), CC BY 4.0" and "countries-states-cities-database, ODbL" must stay in the README.

Refresh: `python3 scripts/update_data.py` (all) or `--visa` (visa only). `--check` reports the visa dataset's age and whether a newer upstream exists.
