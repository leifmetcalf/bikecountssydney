# bikecount

Downloads the raw, full-resolution (15-minute) NSW cycling counts behind the
[TfNSW walking and cycling counts dashboard](https://www.transport.nsw.gov.au/projects/programs/walking-and-cycling-program/walking-and-cycling-counts),
cleans them, and has every counter's full record reviewed.

The dashboard is an embedded Power BI report. There is no download link, so the
downloader queries the report's dataset directly using the page's anonymous embed token.

```sh
uv run bikecount download          # all NSW cycling counts, 8 threads -> data/raw/cycling
uv run bikecount clean             # automatic fixes + review decisions -> data/clean/cycling
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
- **record**: one raw row. A direction's records for the same slot are summed, as the dashboard does. Most
  directions have one record per slot; some have 2 or 4 channel records. Recent data can have a second
  record from the next day's load, and one of the two is then always 0.

## Raw data (`data/raw/cycling`)

All records with `Mode name = Cycle`, including counters the dashboard leaves out
(`counters.csv` `Selected = No`) and sites missing from the Site table.

| File | Contents |
| --- | --- |
| `counts/site_<SITE_SK>_<year>.parquet` | Every record from the fact table `Counts - 15min aggregation`, all columns. TfNSW's slot label (`08:00 - 08:14`) is stored as `slot` (0-95) |
| `sites.csv`, `counters.csv`, `directions.csv` | Dimension tables, all columns; `fact_rows` counts each member's records |
| `modes.csv`, `dates.csv` | Mode and calendar tables (dates carry public and school holidays) |
| `inventory.csv` | Records per site per day in the dataset at the last download (what each file's row count is checked against) |

`DATE_SK` is the year followed by the unpadded day of year (`20131` = 2013-01-01); `date` has it
decoded. `ID` is TfNSW's row number within one load, and the numbering restarts with every load,
so it is not unique and only orders records that came in the same load; `ADDED_UPDATED_DATETIME_SYDNEY`
is the load date. `Status` is 0 (good) or 1 (warning); warning records always have a count of 0.

## Cleaned data (`data/clean/cycling`)

| File | Contents |
| --- | --- |
| `counts_15min.parquet` | One row per direction and slot: `SITE_SK`, `COUNTER_SK`, `DIRECTION_SK`, `date`, `time` (local start of the slot), `workday` (weekday other than a public holiday), `records` (raw records in the slot, from the load that carries its count), `raw` (sum of all records, as the dashboard shows), `count` (cleaned; null = missing), `fix` (why `count` differs from `raw`), `direction_unreliable` (a reviewer found the split between directions wrong; the total is fine), `hourly_binned` (early hourly data: each hour's count sits in one of its four slots) |
| `weekly.parquet` | Bikes per series and week (Monday to Sunday) over the week's complete days: `SITE_SK`, `series`, `week`, `bikes`, `complete_days` (7 = a full week), `direction_unreliable` |
| `series.csv` | The counter-directions making up each series (reviewed ones, and one series per counter-direction elsewhere) |
| `fixes.csv` | Runs fixed automatically (duplicate loads, verified doubling, duplicate measurements) |
| `review_groups.csv` | `SITE_SK` -> review group |

Automatic fixes (see `clean.py`) are the rules reliable enough to apply unseen: warning records,
duplicate loads (extra records that exactly repeat the slot's other records), duplicate measurements,
verified doubling (even-only runs at ~2x the surrounding level), impossible counts and the rest of that
counter-day, and zero outages. A zero run counts as an outage only when the counter stopped for most of
a day's traffic, or when its other directions kept counting meanwhile; shorter lulls in every direction
at once stay zeros, since rain or a closure empties a path too. Hourly days are exempt. Everything else
is left to review.

A **series** is one continuous line of counts for one direction of travel at a site. Where a counter
was replaced, or several counters ran at a site, reviewers define which counter-directions make up
each series (TfNSW's direction labels are not always consistent between counters). Weekly totals are
built per series.

## Review

Sites that share a counter, or counters that share a site, form a review group (153 groups). Each
group's whole record is reviewed by a person or an agent, with the aim of accurate weekly totals.

```sh
uv run bikecount review briefs           # a brief per group -> data/review/briefs/<group>.md
# a reviewer (e.g. the count-reviewer agent in .claude/agents) follows the brief and
# writes reviews/verdicts/<group>.json
uv run bikecount review collect          # verdicts -> reviews/decisions.csv, reviews/series.csv
uv run bikecount clean                   # applies the decisions, builds weekly totals per series
```

Reviewers use the tools in `review.py` (monthly overview, weekly, daily and hourly views, cleaned
slots, raw records, the records behind each slot, nearby sites, holidays, known events). What they are told, and what is
withheld to avoid steering them, is recorded in `reviews/INFORMATION.md`.

`reviews/decisions.csv` has one row per decision: `review_group`, `SITE_SK`, `DIRECTION_SK` (blank for every
direction at the site), `start`, `end`, `action` (`missing`, `halve`, `direction_unreliable`,
`restore` (undo an automatic fix) or `uncertain`), `confidence`, `diagnosis`, `reviewer` and `status`. New decisions are `proposed`;
set `status` to `accepted` or `rejected` after checking them. `clean` applies every decision that
is not rejected; `uncertain` ones change nothing. `reviews/series.csv` has one row per series
part (`SITE_SK`, `series`, `COUNTER_SK`, `DIRECTION_SK`, optional `start` and `end`) with the same
`status` column. Run a round's reviews before applying its decisions, so that every reviewer sees the
same data.

Site totals need care: camera "sites" are zones of one intersection (never sum them all), and
the Harbour Bridge ran a parallel tube counter in 2021-22 that duplicates the piezo.

## Storage

Parquet files are uncompressed, data page v2, with encodings chosen per column (`storage.py`):
dictionary encoding for low-cardinality sorted columns, delta encoding for `ID`, `slot`, counts and `time`.
The raw records take 0.5 GB (11 GB as CSV); the cleaned table 0.1 GB. Nearly all of the saving comes
from delta encoding `ID` and `time`: with pyarrow's default encodings the raw records would take
970 MB and the cleaned table 725 MB.

## Events

`events.csv` logs real-world events that show up in the counts (organised rides, closures),
for annotating plots. `sites` is a `;`-separated list of `SITE_SK`s where the effect was seen.
