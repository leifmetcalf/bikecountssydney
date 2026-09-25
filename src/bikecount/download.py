"""Download full-resolution (15 minute) NSW cycling counts from the TfNSW counts dashboard.

Source page: https://www.transport.nsw.gov.au/projects/programs/walking-and-cycling-program/walking-and-cycling-counts
"""

import csv
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import polars as pl

from .powerbi import WINDOW, PowerBIClient, column, is_in, measure
from .storage import RAW, RAW_SCHEMA, RAW_SORT, parquet_rows, slot_from_label, write_parquet

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


def date_from_sk(date_sk: int) -> date:
    """DATE_SK is the year followed by the unpadded day of year, e.g. 20131 = 2013-01-01, 2026265 = 2026-09-22."""
    s = str(date_sk)
    return date(int(s[:4]), 1, 1) + timedelta(days=int(s[4:]) - 1)


def write_csv(path: Path, header: list[str], rows) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def date_from_sk_expr(date_sk: pl.Expr) -> pl.Expr:
    s = date_sk.cast(pl.Utf8)
    return pl.date(s.str.slice(0, 4).cast(pl.Int32), 1, 1) + pl.duration(days=s.str.slice(4).cast(pl.Int32) - 1)


def to_raw_frame(rows: list[list]) -> pl.DataFrame:
    """Records as returned by the query -> the stored raw schema (see storage.RAW_SCHEMA)."""
    df = pl.DataFrame(rows, schema=FACT_COLUMNS, orient="row", infer_schema_length=None)
    df = df.with_columns(
        date_from_sk_expr(pl.col("DATE_SK")).alias("date"),
        slot_from_label(pl.col("15MIN_TIME_SLOT")).alias("slot"),
        pl.col("ADDED_UPDATED_DATETIME_SYDNEY").str.to_datetime(),
    )
    return df.select(pl.col(c).cast(t) for c, t in RAW_SCHEMA.items()).sort(RAW_SORT)


def download_dimensions(client: PowerBIClient, schema: dict) -> None:
    for filename, entity in DIMENSIONS.items():
        props = [name for name, kind in schema[entity] if kind == "column"]
        # the row-count measure restricts each dimension to members with cycling counts
        select = [(p, column("x", p)) for p in props] + [("fact_rows", measure("c", "_CountRows"))]
        names, rows = client.query(CYCLING + [("x", entity)], select, [MODE_FILTER])
        write_csv(RAW / filename, names, rows)
        print(f"{filename}: {len(rows)} rows")

    for filename, entity in {"modes.csv": "Mode", "dates.csv": "Date"}.items():
        props = [name for name, kind in schema[entity] if kind == "column"]
        names, rows = client.query([("x", entity)], [(p, column("x", p)) for p in props])
        write_csv(RAW / filename, names, rows)
        print(f"{filename}: {len(rows)} rows")


def inventory(client: PowerBIClient, site_sks: list[int], threads: int) -> dict[int, list[tuple[int, int]]]:
    """Per site, the (DATE_SK, row count) pairs present in the fact table."""

    def site_days(site_sk: int) -> list[tuple[int, int]]:
        where = [MODE_FILTER, is_in(column("c", "SITE_SK"), [site_sk])]
        _, rows = client.query(CYCLING, [("DATE_SK", column("c", "DATE_SK")), ("rows", measure("c", "_CountRows"))], where)
        return [(int(d), int(n)) for d, n in rows]

    with ThreadPoolExecutor(threads) as pool:
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


def download_counts(client: PowerBIClient, days_by_site: dict[int, list[tuple[int, int]]], threads: int) -> None:
    counts_dir = RAW / "counts"
    counts_dir.mkdir(exist_ok=True)

    site_years = defaultdict(list)  # (site_sk, year) -> [(date_sk, rows)]
    for site_sk, days in days_by_site.items():
        for date_sk, n in days:
            site_years[site_sk, date_from_sk(date_sk).year].append((date_sk, n))
    todo = []  # (site_sk, days, path, expected rows)
    for (site_sk, year), days in sorted(site_years.items()):
        path, expected = counts_dir / f"site_{site_sk:04d}_{year}.parquet", sum(n for _, n in days)
        if not (path.exists() and parquet_rows(path) == expected):
            todo.append((site_sk, days, path, expected))
    total_rows = sum(t[3] for t in todo)
    print(f"{len(site_years)} site-years, {len(site_years) - len(todo)} already complete; downloading {len(todo)} ({total_rows:,} rows) with {threads} threads")

    lock = threading.Lock()
    done = {"tasks": 0, "rows": 0}
    started = time.time()

    def fetch(site_sk: int, days: list[tuple[int, int]], path: Path, expected: int):
        # ID is not unique (the ETL reuses it across loads), so rows are kept as returned; chunks never overlap
        rows = []
        for chunk in pack_days(days):
            where = [MODE_FILTER, is_in(column("c", "SITE_SK"), [site_sk]), is_in(column("c", "DATE_SK"), chunk)]
            rows += client.query(CYCLING, [(c, column("c", c)) for c in FACT_COLUMNS], where)[1]
        write_parquet(to_raw_frame(rows), path)
        with lock:
            done["tasks"] += 1
            done["rows"] += len(rows)
            rate = done["rows"] / (time.time() - started)
            print(f"[{done['tasks']}/{len(todo)}] {path.name}: {len(rows):,} rows ({done['rows']:,}/{total_rows:,}, {rate:,.0f} rows/s)")
            if len(rows) != expected:
                print(f"  row count changed while downloading: expected {expected:,}; the next run fetches it again")

    with ThreadPoolExecutor(threads) as pool:
        failed = 0
        for f in as_completed([pool.submit(fetch, *task) for task in todo]):
            if f.exception():
                failed += 1
                print(f"FAILED: {f.exception()!r}")
    if failed:
        raise SystemExit(f"{failed} site-years failed; rerun to retry them")


def run(threads: int) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    client = PowerBIClient(REPORT_ID)
    download_dimensions(client, client.schema())

    # take sites from the fact table: some counts reference a SITE_SK missing from the Site table
    _, rows = client.query(CYCLING, [("SITE_SK", column("c", "SITE_SK")), ("rows", measure("c", "_CountRows"))], [MODE_FILTER])
    site_sks = sorted(int(sk) for sk, _ in rows if sk is not None)
    days_by_site = inventory(client, site_sks, threads)
    write_csv(
        RAW / "inventory.csv",
        ["SITE_SK", "DATE_SK", "date", "rows"],
        ([s, d, date_from_sk(d).isoformat(), n] for s, days in days_by_site.items() for d, n in days),
    )
    print(f"inventory: {len(site_sks)} sites, {sum(n for days in days_by_site.values() for _, n in days):,} rows")

    download_counts(client, days_by_site, threads)
