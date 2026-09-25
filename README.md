# bikecount

Downloads the raw, full-resolution (15-minute) NSW cycling counts behind the
[TfNSW walking and cycling counts dashboard](https://www.transport.nsw.gov.au/projects/programs/walking-and-cycling-program/walking-and-cycling-counts),
cleans them, and queues suspect periods for review.

The dashboard is an embedded Power BI report. There is no download link, so the
downloader queries the report's dataset directly using the page's anonymous embed token.

```sh
uv run bikecount download          # all NSW cycling counts, 8 threads -> data/raw/cycling
uv run bikecount clean             # automatic fixes + review queue -> data/clean/cycling
uv run bikecount plot 541 101:156 --out sites.html   # chart page for sites (or site:counter)
uv run bikecount plot --random 10 --seed 1
```

Re-running `download` is safe: a site-year file is re-downloaded only if its row count no
longer matches the dataset (e.g. the current year, which grows as new counts arrive).
`clean` caches the slot table in `data/interim/` and rebuilds it only when raw files change.

## Terms

- **site**: a counting location (`SITE_SK`). **counter**: a device (`COUNTER_SK`); a camera covers many sites.
- **direction**: one direction of travel at a site, measured by one counter (`DIRECTION_SK`).
- **slot**: a 15-minute interval of the day, 0 (00:00-00:14) to 95 (23:45-23:59).
- **record**: one raw row. Some counters send several channel records per direction and slot; they are summed.

## Raw data (`data/raw/cycling`)

All records with `Mode name = Cycle`, including counters the dashboard leaves out
(`counters.csv` `Selected = No`) and sites missing from the Site table.

| File | Contents |
| --- | --- |
| `counts/site_<SITE_SK>_<year>.parquet` | Every record from the fact table `Counts - 15min aggregation`, all columns. TfNSW's slot label (`08:00 - 08:14`) is stored as `slot` (0-95) |
| `sites.csv`, `counters.csv`, `directions.csv` | Dimension tables, all columns; `fact_rows` counts each member's records |
| `modes.csv`, `dates.csv` | Mode and calendar tables (dates carry public and school holidays) |
| `inventory.csv` | Records per site per day, used to plan and verify the download |

`DATE_SK` is the year followed by the unpadded day of year (`20131` = 2013-01-01); `date` has it
decoded. `ID` is not unique: the TfNSW ETL reuses it across loads. `Status` is 0 (good) or
1 (warning); warning records always have a count of 0.

## Cleaned data (`data/clean/cycling`)

| File | Contents |
| --- | --- |
| `counts_15min.parquet` | One row per direction and slot: `time` (local start of the slot), `raw` (sum of all records, as the dashboard shows), `count` (cleaned; null = missing), `fix` (automatic fix applied), `flags` (review checks covering the slot), `direction_unreliable` |
| `fixes.csv` | Runs fixed automatically (verified doubling, duplicate measurements) |
| `review_queue.csv` | Suspect periods for a person or agent to review |

Automatic fixes (see `clean.py`): warning records, duplicate measurements, verified doubling
(even-only runs at ~2x the surrounding level), impossible counts and the rest of that counter-day,
and zero outages. Review checks: spikes, level shifts, direction split / peak flip, flat runs,
bad values, and even-only runs that are not verifiably doubled.

To act on a flag, add a row to `review_decisions.csv` (`flag_id,action`, where action is
`keep`, `missing`, `halve` or `direction_unreliable`) and re-run `clean`.

Site totals need care: camera "sites" are zones of one intersection (never sum them all), and
the Harbour Bridge ran a parallel tube counter in 2021-22 that duplicates the piezo.

## Storage

Parquet files are uncompressed, data page v2, with encodings chosen per column (`storage.py`):
dictionary encoding for low-cardinality sorted columns, delta encoding for `ID`, counts and time.
The raw records take 0.5 GB (11 GB as CSV); the cleaned table 0.1 GB.

## Events

`events.csv` logs real-world events that show up in the counts (organised rides, closures),
for annotating plots. `sites` is a `;`-separated list of `SITE_SK`s where the effect was seen.
