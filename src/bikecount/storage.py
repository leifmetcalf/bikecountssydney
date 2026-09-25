"""Parquet storage for the count tables: uncompressed, with an encoding chosen per column.

Nearly every column is low-cardinality and sorted into long runs (keys, dates, statuses), so dictionary
encoding with RLE/bit-packed indices shrinks it to almost nothing. Columns that change a little from row to
row are delta encoded instead: `ID` (close to unique, where a dictionary falls back to plain), the counts,
and the time of day.

Time of day is `slot` (0-95, 15 minutes each) in the raw records and `time` (the slot's local start) in the
cleaned table. The cleaned table has exactly one row per direction and slot, so `time` steps by a constant
15 minutes and delta encodes to almost nothing (5 MB), where `slot` wraps from 95 to 0 at midnight and that
one step makes every value in its delta block cost 7 bits (88 MB). Raw records can have several channel
records per slot, so `time` would step by 0 or 15 minutes (20 bits a value) and `slot` is cheaper there.
Data page v2 stores null markers apart from the values, which saves ~10% on the cleaned table.
"""

import os
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

RAW = Path("data/raw/cycling")  # downloaded records and dimension tables
CLEAN = Path("data/clean/cycling")  # cleaned counts, fixes and the review queue
EVENTS = Path("events.csv")
DECISIONS = Path("review_decisions.csv")

DELTA_COLUMNS = {"ID", "slot", "time", "TOTAL_15MIN_COUNT", "raw", "count"}

# Raw count records, as downloaded. TfNSW's slot label ("08:00 - 08:14") is stored as its slot number.
RAW_SCHEMA = {
    "SITE_SK": pl.Int16,
    "DIRECTION_SK": pl.Int16,
    "COUNTER_SK": pl.Int16,
    "MODE_SK": pl.Int8,
    "date": pl.Date,
    "slot": pl.UInt8,
    "ID": pl.UInt32,  # max 66M so far
    "DATE_SK": pl.Int32,
    "TOTAL_15MIN_COUNT": pl.UInt16,
    "SPEED_15MIN_MEDIAN": pl.Float32,
    "SPEED_15MIN_85P": pl.Float32,
    "Status": pl.Int8,
    "Status description": pl.Utf8,
    "ADDED_UPDATED_DATETIME_SYDNEY": pl.Date,  # always midnight in the source
}
RAW_SORT = ["SITE_SK", "DIRECTION_SK", "date", "slot", "ID"]


def slot_from_label(label: pl.Expr) -> pl.Expr:
    """'08:00 - 08:14' -> 32."""
    return (label.str.slice(0, 2).cast(pl.UInt8) * 4 + label.str.slice(3, 2).cast(pl.UInt8) // 15).cast(pl.UInt8)


def slot_start(date: pl.Expr, slot: pl.Expr) -> pl.Expr:
    """(2019-05-01, 32) -> 2019-05-01 08:00, local Sydney wall-clock time."""
    return (date.cast(pl.Datetime("ms")) + pl.duration(minutes=slot.cast(pl.Int32) * 15)).cast(pl.Datetime("ms"))


def write_parquet(df: pl.DataFrame, path: Path) -> None:
    """Uncompressed Parquet, data page v2: delta encoding for DELTA_COLUMNS, dictionary encoding for the rest."""
    # One chunk per column: a multi-chunk Categorical gets a dictionary per chunk, pyarrow then falls back to plain
    # pages after the first, and polars 1.x cannot read those back (pola-rs/polars#28959, fixed in 2.0).
    table = df.rechunk().to_arrow(compat_level=pl.CompatLevel.oldest())
    delta = [c for c in table.column_names if c in DELTA_COLUMNS]
    tmp = path.with_suffix(".tmp")
    pq.write_table(
        table,
        tmp,
        compression="NONE",
        data_page_version="2.0",
        use_dictionary=[c for c in table.column_names if c not in DELTA_COLUMNS],
        column_encoding={c: "DELTA_BINARY_PACKED" for c in delta},
    )
    os.replace(tmp, path)


def parquet_rows(path: Path) -> int:
    return pq.ParquetFile(path).metadata.num_rows
