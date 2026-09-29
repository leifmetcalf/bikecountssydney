"""Download the raw 15-minute NSW cycling counts behind the TfNSW walking and cycling counts dashboard.

https://www.transport.nsw.gov.au/projects/programs/walking-and-cycling-program/walking-and-cycling-counts is an
embedded Power BI report with no download link, so its dataset is queried directly (see powerbi.py).

    uv run download.py

writes data/raw:
    counts/site_<SITE_SK>_<year>.parquet   every record with Mode name = Cycle, all columns (RAW_SCHEMA), including
                                           counters the dashboard leaves out and sites missing from the Site table
    sites.csv, counters.csv, directions.csv  dimension tables, all columns; `fact_rows` counts each member's records
    dates.csv                              calendar (day type, public and school holidays)

Re-running is safe: a site-year file is downloaded again only when its row count no longer matches the dataset
(e.g. the current year, which grows as new counts arrive).

About the records: `DATE_SK` is the year followed by the unpadded day of year (20131 = 2013-01-01), decoded as
`date` (DATE_SK itself is not stored). `ID` is TfNSW's row number within one load and restarts with every load, so it is not unique and only
orders records of the same load; `ADDED_UPDATED_DATETIME_SYDNEY` is the load date. `Status` is 0 (good) or 1
(warning); warning records always have a count of 0.
"""

import csv
import os
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import polars as pl

from clean import RAW
from powerbi import WINDOW, PowerBIClient, column, is_in, measure

THREADS = 8
REPORT_ID = "e7d70973-10d2-4ec5-819d-82f7ef5c4899"  # "AT Counts_public-Cycling"
FACT = "Counts - 15min aggregation"
FACT_COLUMNS = [
    "ID",
    "DATE_SK",
    "15MIN_TIME_SLOT",
    "SITE_SK",
    "DIRECTION_SK",
    "COUNTER_SK",
    "MODE_SK",
    "TOTAL_15MIN_COUNT",
    "SPEED_15MIN_MEDIAN",
    "SPEED_15MIN_85P",
    "Status",
    "Status description",
    "ADDED_UPDATED_DATETIME_SYDNEY",
]
# the cycling rows of the fact table
CYCLING = [("m", "Mode"), ("c", FACT)]
MODE_FILTER = is_in(column("m", "Mode name"), ["Cycle"])
DIMENSIONS = {"sites.csv": "Site", "counters.csv": "Counter", "directions.csv": "Direction"}

# Raw count records as stored. TfNSW's DATE_SK and slot label ("08:00 - 08:14") are stored as a date and slot number.
RAW_SCHEMA = {
    "SITE_SK": pl.Int16,
    "DIRECTION_SK": pl.Int16,
    "COUNTER_SK": pl.Int16,
    "MODE_SK": pl.Int8,
    "date": pl.Date,
    "slot": pl.UInt8,
    "ID": pl.UInt32,  # max 66M so far
    "TOTAL_15MIN_COUNT": pl.UInt16,
    "SPEED_15MIN_MEDIAN": pl.Float32,
    "SPEED_15MIN_85P": pl.Float32,
    "Status": pl.Int8,
    "Status description": pl.Utf8,
    "ADDED_UPDATED_DATETIME_SYDNEY": pl.Date,  # always midnight in the source
}
RAW_SORT = ["SITE_SK", "DIRECTION_SK", "date", "slot", "ID"]


def date_from_sk(date_sk: pl.Expr) -> pl.Expr:
    """20131 -> 2013-01-01, 2026265 -> 2026-09-22."""
    s = date_sk.cast(pl.Utf8)
    return pl.date(s.str.slice(0, 4).cast(pl.Int32), 1, 1) + pl.duration(days=s.str.slice(4).cast(pl.Int32) - 1)


def slot_from_label(label: pl.Expr) -> pl.Expr:
    """'08:00 - 08:14' -> 32."""
    return (label.str.slice(0, 2).cast(pl.UInt8) * 4 + label.str.slice(3, 2).cast(pl.UInt8) // 15).cast(pl.UInt8)


def to_raw_frame(rows: list[list]) -> pl.DataFrame:
    df = pl.DataFrame(rows, schema=FACT_COLUMNS, orient="row", infer_schema_length=None)
    df = df.with_columns(
        date_from_sk(pl.col("DATE_SK")).alias("date"),
        slot_from_label(pl.col("15MIN_TIME_SLOT")).alias("slot"),
        pl.col("ADDED_UPDATED_DATETIME_SYDNEY").str.to_datetime(),
    )
    return df.select(pl.col(c).cast(t) for c, t in RAW_SCHEMA.items()).sort(RAW_SORT)


def write_csv(path: Path, header: list[str], rows) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def download_dimensions(client: PowerBIClient) -> None:
    schema = client.schema()
    columns = lambda entity: [name for name, kind in schema[entity] if kind == "column"]
    for filename, entity in DIMENSIONS.items():
        # the row-count measure restricts each dimension to members with cycling counts
        select = [(p, column("x", p)) for p in columns(entity)] + [("fact_rows", measure("c", "_CountRows"))]
        names, rows = client.query(CYCLING + [("x", entity)], select, [MODE_FILTER])
        write_csv(RAW / filename, names, rows)
        print(f"{filename}: {len(rows)} rows")
    names, rows = client.query([("x", "Date")], [(p, column("x", p)) for p in columns("Date")])
    write_csv(RAW / "dates.csv", names, rows)
    print(f"dates.csv: {len(rows)} rows")


def inventory(client: PowerBIClient, site_sks: list[int]) -> dict[int, list[tuple[int, int]]]:
    """Per site, the (DATE_SK, row count) pairs present in the fact table."""

    def site_days(site_sk: int) -> list[tuple[int, int]]:
        where = [MODE_FILTER, is_in(column("c", "SITE_SK"), [site_sk])]
        _, rows = client.query(CYCLING, [("DATE_SK", column("c", "DATE_SK")), ("rows", measure("c", "_CountRows"))], where)
        return [(int(d), int(n)) for d, n in rows]

    with ThreadPoolExecutor(THREADS) as pool:
        return dict(zip(site_sks, pool.map(site_days, site_sks)))


def pack_days(days: list[tuple[int, int]]) -> list[list[int]]:
    """Group days into chunks that each fit in a single query window.

    PowerBIClient.query can page through a larger result with restart tokens, but each continuation re-runs the
    query: a 300k-row site-year took 62-83 s that way against 19-23 s in single-window chunks.
    """
    chunks: list[list[int]] = [[]]
    total = 0
    for date_sk, n in days:
        if chunks[-1] and total + n > WINDOW - 1:
            chunks.append([])
            total = 0
        chunks[-1].append(date_sk)
        total += n
    return chunks


def download_counts(client: PowerBIClient, days_by_site: dict[int, list[tuple[int, int]]]) -> None:
    counts_dir = RAW / "counts"
    counts_dir.mkdir(exist_ok=True)

    site_years = defaultdict(list)  # (site_sk, year) -> [(date_sk, rows)]
    for site_sk, days in days_by_site.items():
        for date_sk, n in days:
            site_years[site_sk, int(str(date_sk)[:4])].append((date_sk, n))
    todo = []  # (site_sk, days, path, expected rows)
    for (site_sk, year), days in sorted(site_years.items()):
        path, expected = counts_dir / f"site_{site_sk:04d}_{year}.parquet", sum(n for _, n in days)
        if not (path.exists() and pl.scan_parquet(path).select(pl.len()).collect().item() == expected):
            todo.append((site_sk, days, path, expected))
    total_rows = sum(t[3] for t in todo)
    print(f"{len(site_years)} site-years, {len(site_years) - len(todo)} already complete; downloading {len(todo)} ({total_rows:,} rows)")

    lock = threading.Lock()
    done = {"tasks": 0, "rows": 0}
    started = time.time()

    def fetch(site_sk: int, days: list[tuple[int, int]], path: Path, expected: int):
        # ID is not unique (the ETL reuses it across loads), so rows are kept as returned; chunks never overlap
        rows = []
        for chunk in pack_days(days):
            where = [MODE_FILTER, is_in(column("c", "SITE_SK"), [site_sk]), is_in(column("c", "DATE_SK"), chunk)]
            rows += client.query(CYCLING, [(c, column("c", c)) for c in FACT_COLUMNS], where)[1]
        # write then rename, so an interrupted run never leaves a partial file behind
        to_raw_frame(rows).write_parquet(path.with_suffix(".tmp"))
        os.replace(path.with_suffix(".tmp"), path)
        with lock:
            done["tasks"] += 1
            done["rows"] += len(rows)
            rate = done["rows"] / (time.time() - started)
            print(f"[{done['tasks']}/{len(todo)}] {path.name}: {len(rows):,} rows ({done['rows']:,}/{total_rows:,}, {rate:,.0f} rows/s)")
            if len(rows) != expected:
                print(f"  row count changed while downloading: expected {expected:,}; the next run fetches it again")

    with ThreadPoolExecutor(THREADS) as pool:
        failed = 0
        for f in as_completed([pool.submit(fetch, *task) for task in todo]):
            if f.exception():
                failed += 1
                print(f"FAILED: {f.exception()!r}")
    if failed:
        raise SystemExit(f"{failed} site-years failed; rerun to retry them")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    client = PowerBIClient(REPORT_ID)
    download_dimensions(client)
    # take sites from the fact table: some counts reference a SITE_SK missing from the Site table
    _, rows = client.query(CYCLING, [("SITE_SK", column("c", "SITE_SK")), ("rows", measure("c", "_CountRows"))], [MODE_FILTER])
    site_sks = sorted(int(sk) for sk, _ in rows if sk is not None)
    days_by_site = inventory(client, site_sks)
    print(f"inventory: {len(site_sks)} sites, {sum(n for days in days_by_site.values() for _, n in days):,} rows")
    download_counts(client, days_by_site)


if __name__ == "__main__":
    main()
