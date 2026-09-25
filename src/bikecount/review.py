"""Tools for reviewing a flagged group: metadata, raw records, cleaned series, profiles and neighbours.

Used by reviewers (people or agents) from Python:

    from bikecount import review as rv
    rv.queue("G0541")                            # the group's flags
    rv.meta("G0541")                             # sites, counters, directions and their date ranges
    rv.daily([541], "2018-01-01", "2020-12-31")  # raw and cleaned daily totals per direction
    rv.hourly([541], "2018-09-01", "2018-11-30")  # mean bikes per hour per direction (workdays)
    rv.channels([541], "2018-09-03", "2018-09-03")  # the individual records behind each slot
    rv.neighbours(541)                           # nearby sites for comparison
"""

import math
from pathlib import Path

import polars as pl



def slot_label(slot: pl.Expr) -> pl.Expr:
    """32 -> '08:00 - 08:14', TfNSW's label for a slot."""
    minutes = slot.cast(pl.Int32) * 15
    hhmm = lambda m: pl.concat_str([(m // 60).cast(pl.Utf8).str.zfill(2), pl.lit(":"), (m % 60).cast(pl.Utf8).str.zfill(2)])
    return pl.concat_str([hhmm(minutes), pl.lit(" - "), hhmm(minutes + 14)])

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "cycling"
CLEAN = ROOT / "data" / "clean" / "cycling"
PACKETS = ROOT / "data" / "review" / "packets"
VERDICTS = ROOT / "data" / "review" / "verdicts"
Dates = str | None


def _period(lf: pl.LazyFrame, start: Dates, end: Dates, col: str = "date") -> pl.LazyFrame:
    if start:
        lf = lf.filter(pl.col(col) >= pl.lit(start).str.to_date())
    if end:
        lf = lf.filter(pl.col(col) <= pl.lit(end).str.to_date())
    return lf


def _dims(name: str) -> pl.DataFrame:
    return pl.read_csv(RAW / name, infer_schema_length=0)


def queue(group: str | None = None) -> pl.DataFrame:
    q = pl.read_csv(CLEAN / "review_queue.csv", try_parse_dates=True)
    return q.filter(pl.col("review_group") == group) if group else q


def group_sites(group: str) -> list[int]:
    """Every site in a review group, flagged or not."""
    from .clean import review_groups

    keys = pl.scan_parquet(CLEAN / "counts_15min.parquet").select("SITE_SK", "COUNTER_SK").unique().collect()
    return sorted(review_groups(keys).filter(pl.col("review_group") == group)["SITE_SK"].to_list())


def meta(group: str) -> dict[str, pl.DataFrame]:
    sites = group_sites(group)
    span = (
        pl.scan_parquet(CLEAN / "counts_15min.parquet").filter(pl.col("SITE_SK").is_in(sites))
        .group_by("SITE_SK", "COUNTER_SK", "DIRECTION_SK").agg(pl.col("date").min().alias("first"), pl.col("date").max().alias("last"))
        .collect().sort("SITE_SK", "COUNTER_SK", "DIRECTION_SK")
    )
    s = [str(x) for x in sites]
    c = [str(x) for x in span["COUNTER_SK"].unique()]
    return {
        "sites": _dims("sites.csv").filter(pl.col("SITE_SK").is_in(s)).select(
            "SITE_SK", "Site name", "Suburb", "LGA", "Facility description", "Site latitude", "Site longitude", "Location name", "Site status", "Site comment"),
        "counters": _dims("counters.csv").filter(pl.col("COUNTER_SK").is_in(c)).select(
            "COUNTER_SK", "Counter ID", "Technology", "Vendor name", "Unit model", "Data owner", "Selected"),
        "directions": span.join(
            _dims("directions.csv").select(pl.col("DIRECTION_SK").cast(pl.Int16), "Orientation description", "Location in/out", "Citybound"),
            on="DIRECTION_SK", how="left"),
    }


def raw(sites: list[int], start: Dates = None, end: Dates = None) -> pl.DataFrame:
    """Raw records exactly as downloaded, with TfNSW's slot label restored."""
    lf = pl.scan_parquet(RAW / "counts" / "*.parquet").filter(pl.col("SITE_SK").is_in(sites))
    return _period(lf, start, end).with_columns(slot_label(pl.col("slot")).alias("slot_label")).collect().sort("DIRECTION_SK", "date", "slot", "ID")


def clean(sites: list[int], start: Dates = None, end: Dates = None) -> pl.DataFrame:
    """Cleaned direction-slots: raw (sum of records), count (cleaned, null = missing), fix, flags."""
    lf = pl.scan_parquet(CLEAN / "counts_15min.parquet").filter(pl.col("SITE_SK").is_in(sites))
    return _period(lf, start, end).collect()


def daily(sites: list[int], start: Dates = None, end: Dates = None) -> pl.DataFrame:
    """Per direction and day: raw and cleaned totals, valid slots, records per slot, fixes and flags present."""
    lf = pl.scan_parquet(CLEAN / "counts_15min.parquet").filter(pl.col("SITE_SK").is_in(sites))
    return (
        _period(lf, start, end)
        .group_by("SITE_SK", "COUNTER_SK", "DIRECTION_SK", "date")
        .agg(
            pl.col("raw").cast(pl.Int32).sum().alias("raw"),
            pl.col("count").cast(pl.Int32).sum().alias("clean"),
            pl.col("count").is_not_null().sum().alias("valid_slots"),
            pl.col("records").cast(pl.Float32).mean().round(2).alias("records_per_slot"),
            ((pl.col("count") % 2 == 1)).sum().alias("odd_slots"),
            (pl.col("count") > 0).sum().alias("nonzero_slots"),
            pl.col("fix").cast(pl.Utf8).drop_nulls().unique().sort().str.join(",").alias("fixes"),
            pl.col("flags").cast(pl.Utf8).drop_nulls().unique().sort().str.join(",").alias("flags"),
        )
        .collect()
        .sort("DIRECTION_SK", "date")
    )


def monthly(sites: list[int], start: Dates = None, end: Dates = None) -> pl.DataFrame:
    """Mean cleaned bikes per complete day (>= 90 valid slots), per direction and month."""
    d = daily(sites, start, end).filter(pl.col("valid_slots") >= 90)
    return (
        d.group_by("SITE_SK", "COUNTER_SK", "DIRECTION_SK", pl.col("date").dt.truncate("1mo").alias("month"))
        .agg(pl.col("clean").mean().round(0).alias("per_day"), pl.len().alias("days"))
        .sort("DIRECTION_SK", "month")
    )


def hourly(sites: list[int], start: Dates, end: Dates, workday: bool = True) -> pl.DataFrame:
    """Mean cleaned bikes per hour of day, per direction (columns are hours 0-23)."""
    c = clean(sites, start, end).filter(pl.col("workday") == workday)
    days = c.group_by("DIRECTION_SK").agg(pl.col("date").n_unique().alias("days"))
    h = (
        c.with_columns((pl.col("time").dt.hour()).alias("hour"))
        .group_by("DIRECTION_SK", "hour").agg(pl.col("count").cast(pl.Int64).sum().alias("n"))
        .join(days, on="DIRECTION_SK")
        .with_columns((pl.col("n") / pl.col("days")).round(1).alias("mean"))
    )
    return h.pivot(on="hour", index="DIRECTION_SK", values="mean", sort_columns=True).join(days, on="DIRECTION_SK")


def channels(sites: list[int], start: Dates, end: Dates) -> pl.DataFrame:
    """The individual records behind each slot (several per slot for multi-channel counters), in ID order."""
    r = raw(sites, start, end)
    return r.group_by("DIRECTION_SK", "date", "slot", "slot_label").agg(
        pl.col("TOTAL_15MIN_COUNT").alias("records"), pl.col("Status").alias("status"), pl.col("ID").alias("ids"),
        pl.col("ADDED_UPDATED_DATETIME_SYDNEY").unique().alias("loaded"),
    ).sort("DIRECTION_SK", "date", "slot")


def neighbours(site: int, km: float = 3.0, cameras: bool = False) -> pl.DataFrame:
    """Other sites within `km`, nearest first, with the dates they have data."""
    s = _dims("sites.csv").with_columns(pl.col("Site latitude").cast(pl.Float64), pl.col("Site longitude").cast(pl.Float64))
    me = s.filter(pl.col("SITE_SK") == str(site)).row(0, named=True)
    lat0, lon0 = me["Site latitude"], me["Site longitude"]
    dist = ((pl.col("Site latitude") - lat0) * 111.0).pow(2) + ((pl.col("Site longitude") - lon0) * 111.0 * math.cos(math.radians(lat0))).pow(2)
    near = s.with_columns(dist.sqrt().round(2).alias("km")).filter((pl.col("km") <= km) & (pl.col("SITE_SK") != str(site)))
    span = pl.scan_parquet(CLEAN / "counts_15min.parquet").group_by("SITE_SK", "COUNTER_SK").agg(
        pl.col("date").min().alias("first"), pl.col("date").max().alias("last")).collect()
    counters = _dims("counters.csv").select(pl.col("COUNTER_SK").cast(pl.Int16), "Technology")
    out = near.select(pl.col("SITE_SK").cast(pl.Int16), "Site name", "km").join(span, on="SITE_SK").join(counters, on="COUNTER_SK", how="left")
    if not cameras:
        out = out.filter(pl.col("Technology") != "CAMERA")
    return out.sort("km")


def events() -> pl.DataFrame:
    return pl.read_csv(ROOT / "events.csv")


RUBRIC = """\
## How to review

You are reviewing possible data faults in TfNSW bike counter data. Each flag below was raised by an
automatic check; decide what should happen to the data it covers. Real changes (new cycleways,
closures, COVID, events such as organised rides) must be kept. Faults (dead sensors, doubled or
corrupted values, wrong direction assignment) must not.

Use the raw 15-minute records, not just the daily totals. Useful evidence:
- hourly profiles per direction before, during and after the period (`rv.hourly`)
- the individual channel records behind each slot (`rv.channels`)
- the same days at nearby sites (`rv.neighbours`, then `rv.daily` / `rv.monthly` on them)
- other counters at the same site over time, and for cameras the other zones of the same camera

Terms: a slot is a 15-minute interval (0-95). `raw` is the sum of all records in a slot, as the TfNSW
dashboard shows it; `count` is after the automatic fixes (null = set to missing). Automatic fixes are
already applied and are not up for review. Camera counters split an intersection into zones ("sites"),
each with directions labelled IN (towards the intersection) or OUT; a rider is counted on the way in
and again on the way out, so a camera's IN total should roughly equal its OUT total.

Actions:
- `keep`: the data is genuine, or the evidence is too weak to change it
- `missing`: the values are wrong and cannot be recovered; set the period to missing
- `halve`: every value is exactly doubled
- `direction_unreliable`: the split between directions is wrong but the total across them is right

You may narrow or widen a flag's dates. Report problems you find that no flag covers under
`other_issues`. Do not modify any code or data except your verdict file.

## Verdict file

Write JSON to `{verdict_path}`:

```json
{{
  "group": "{group}",
  "verdicts": [
    {{"flag_id": "...", "action": "keep|missing|halve|direction_unreliable", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD",
      "confidence": "high|medium|low", "diagnosis": "one sentence", "evidence": "the key numbers"}}
  ],
  "other_issues": [
    {{"SITE_SK": 0, "DIRECTION_SK": null, "start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "description": "...", "suggested_action": "..."}}
  ],
  "summary": "two or three sentences on the group"
}}
```

One verdict per flag_id, covering every flag listed above.
"""


def _md(df: pl.DataFrame) -> str:
    cols = df.columns
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join("" if v is None else str(v) for v in row) + " |" for row in df.rows()]
    return "\n".join(lines)


def write_packet(group: str) -> Path:
    """Write the review brief for a group: what it contains, what was flagged, what was already fixed."""
    m = meta(group)
    sites = group_sites(group)
    flags = queue(group).select("flag_id", "check", "SITE_SK", "COUNTER_SK", "DIRECTION_SK", "start", "end", "detail")
    fixes = (
        clean(sites).filter(pl.col("fix").is_not_null())
        .group_by("SITE_SK", "DIRECTION_SK", "fix").agg(pl.len().alias("slots"), pl.col("date").min().alias("first"), pl.col("date").max().alias("last"))
        .sort("SITE_SK", "DIRECTION_SK", "fix")
    )
    cameras = m["counters"].filter(pl.col("Technology") == "CAMERA").height > 0
    near = neighbours(sites[0], cameras=False).head(8) if not cameras else pl.DataFrame()
    VERDICTS.mkdir(parents=True, exist_ok=True)
    verdict_path = VERDICTS / f"{group}.json"
    parts = [
        f"# Review group {group}",
        "",
        f"Sites {', '.join(map(str, sites))}. Load the tools with `from bikecount import review as rv` "
        "(run Python with `uv run python` from the repository root).",
        "",
        "## Sites",
        _md(m["sites"]),
        "",
        "## Counters",
        _md(m["counters"]),
        "",
        "## Directions (dates with data)",
        _md(m["directions"]),
        "",
        f"## Flags to review ({flags.height})",
        _md(flags),
        "",
        "## Automatic fixes already applied in this group",
        _md(fixes) if fixes.height else "None.",
        "",
    ]
    if not near.is_empty():
        parts += ["## Nearby non-camera sites (for comparison)", _md(near), ""]
    parts.append(RUBRIC.format(group=group, verdict_path=verdict_path))
    PACKETS.mkdir(parents=True, exist_ok=True)
    path = PACKETS / f"{group}.md"
    path.write_text("\n".join(parts))
    return path
