"""Reviewing counter data: tools for reviewers, the brief they are given, and collecting their decisions.

Every review group (sites linked by shared counters) is reviewed in full. Reviewers (people or agents)
use these tools from Python:

    from bikecount import review as rv
    rv.meta("G0000")                              # a group's sites, counters and directions
    rv.overview("G0000")                          # per direction and month: coverage, level, records, fixes
    rv.weekly([SITE], "YYYY-MM-DD", "YYYY-MM-DD") # cleaned weekly totals per counter-direction
    rv.daily([SITE], "YYYY-MM-DD", "YYYY-MM-DD")  # raw and cleaned daily totals per direction
    rv.hourly([SITE], "YYYY-MM-DD", "YYYY-MM-DD") # mean bikes per hour of day per direction
    rv.clean([SITE], "YYYY-MM-DD", "YYYY-MM-DD")  # cleaned 15-minute slots
    rv.raw([SITE], "YYYY-MM-DD", "YYYY-MM-DD")    # raw records exactly as downloaded
    rv.channels([SITE], "YYYY-MM-DD", "YYYY-MM-DD")  # the records behind each slot
    rv.neighbours(SITE)                           # other sites nearby
    rv.calendar()                                 # public and school holidays
    rv.events()                                   # hand-curated list of known events

What reviewers are told, and why, is recorded in reviews/INFORMATION.md.
"""

import json
import math
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "cycling"
CLEAN = ROOT / "data" / "clean" / "cycling"
BRIEFS = ROOT / "data" / "review" / "briefs"
REVIEWS = ROOT / "reviews"
VERDICTS = REVIEWS / "verdicts"
DECISIONS = REVIEWS / "decisions.csv"
COMPLETE_SLOTS = 90  # a day counts as complete with this many of its 96 slots valid after cleaning
Dates = str | None


def slot_label(slot: pl.Expr) -> pl.Expr:
    """32 -> '08:00 - 08:14', TfNSW's label for a slot."""
    minutes = slot.cast(pl.Int32) * 15
    hhmm = lambda m: pl.concat_str([(m // 60).cast(pl.Utf8).str.zfill(2), pl.lit(":"), (m % 60).cast(pl.Utf8).str.zfill(2)])
    return pl.concat_str([hhmm(minutes), pl.lit(" - "), hhmm(minutes + 14)])


def _period(lf: pl.LazyFrame, start: Dates, end: Dates, col: str = "date") -> pl.LazyFrame:
    if start:
        lf = lf.filter(pl.col(col) >= pl.lit(start).str.to_date())
    if end:
        lf = lf.filter(pl.col(col) <= pl.lit(end).str.to_date())
    return lf


def _dims(name: str) -> pl.DataFrame:
    return pl.read_csv(RAW / name, infer_schema_length=0)


def groups() -> pl.DataFrame:
    """SITE_SK -> review_group, as written by `bikecount clean`."""
    return pl.read_csv(CLEAN / "review_groups.csv", schema_overrides={"SITE_SK": pl.Int16})


def group_sites(group: str) -> list[int]:
    return sorted(groups().filter(pl.col("review_group") == group)["SITE_SK"].to_list())


# --- tools ---------------------------------------------------------------------
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
    """Cleaned direction-slots: raw (sum of records), count (cleaned, null = missing), fix (automatic fix applied)."""
    lf = pl.scan_parquet(CLEAN / "counts_15min.parquet").filter(pl.col("SITE_SK").is_in(sites))
    return _period(lf, start, end).drop("direction_unreliable").collect()


def daily(sites: list[int], start: Dates = None, end: Dates = None) -> pl.DataFrame:
    """Per direction and day: raw and cleaned totals, valid slots, records per slot, odd and non-zero slots, fixes applied."""
    return (
        clean(sites, start, end)
        .group_by("SITE_SK", "COUNTER_SK", "DIRECTION_SK", "date")
        .agg(
            pl.col("raw").cast(pl.Int32).sum().alias("raw"),
            pl.col("count").cast(pl.Int32).sum().alias("clean"),
            pl.col("count").is_not_null().sum().alias("valid_slots"),
            pl.col("records").cast(pl.Float32).mean().round(2).alias("records_per_slot"),
            (pl.col("count") % 2 == 1).sum().alias("odd_slots"),
            (pl.col("count") > 0).sum().alias("nonzero_slots"),
            pl.col("fix").cast(pl.Utf8).drop_nulls().unique().sort().str.join(",").alias("fixes"),
        )
        .sort("DIRECTION_SK", "date")
    )


def weekly(sites: list[int], start: Dates = None, end: Dates = None) -> pl.DataFrame:
    """Per direction and week (Monday to Sunday): cleaned total, raw total, complete days, share of slots valid."""
    d = daily(sites, start, end)
    return (
        d.group_by("SITE_SK", "COUNTER_SK", "DIRECTION_SK", pl.col("date").dt.truncate("1w").alias("week"))
        .agg(
            pl.col("clean").sum(), pl.col("raw").sum(),
            (pl.col("valid_slots") >= COMPLETE_SLOTS).sum().alias("complete_days"),
            (pl.col("valid_slots").sum() / (7 * 96)).round(3).alias("valid_share"),
        )
        .sort("DIRECTION_SK", "week")
    )


def monthly(sites: list[int], start: Dates = None, end: Dates = None) -> pl.DataFrame:
    """Mean cleaned bikes per complete day, per direction and month."""
    d = daily(sites, start, end).filter(pl.col("valid_slots") >= COMPLETE_SLOTS)
    return (
        d.group_by("SITE_SK", "COUNTER_SK", "DIRECTION_SK", pl.col("date").dt.truncate("1mo").alias("month"))
        .agg(pl.col("clean").mean().round(0).alias("per_day"), pl.len().alias("days"))
        .sort("DIRECTION_SK", "month")
    )


def overview(group: str) -> pl.DataFrame:
    """One row per direction and month for the whole group: days with data, complete days, mean cleaned and raw
    bikes per day, records per slot, and the share of slots changed by automatic fixes."""
    c = clean(group_sites(group))
    days = c.group_by("DIRECTION_SK", "date").agg(
        pl.col("SITE_SK").first(), pl.col("COUNTER_SK").first(),
        pl.col("count").cast(pl.Int32).sum().alias("clean"), pl.col("raw").cast(pl.Int32).sum().alias("raw"),
        pl.col("count").is_not_null().sum().alias("valid"), pl.col("records").cast(pl.Float32).mean().alias("records"),
        pl.col("fix").is_not_null().mean().alias("fixed"),
    )
    complete = pl.col("valid") >= COMPLETE_SLOTS
    return (
        days.group_by("SITE_SK", "COUNTER_SK", "DIRECTION_SK", pl.col("date").dt.truncate("1mo").alias("month"))
        .agg(
            pl.len().alias("days"), complete.sum().alias("complete_days"),
            pl.col("clean").filter(complete).mean().round(0).alias("clean_per_day"), pl.col("raw").mean().round(0).alias("raw_per_day"),
            pl.col("records").mean().round(2).alias("records_per_slot"), pl.col("fixed").mean().round(3).alias("fixed_share"),
        )
        .sort("SITE_SK", "DIRECTION_SK", "month")
    )


def hourly(sites: list[int], start: Dates, end: Dates, workday: bool = True) -> pl.DataFrame:
    """Mean cleaned bikes per hour of day, per direction (columns are hours 0-23)."""
    c = clean(sites, start, end).filter(pl.col("workday") == workday)
    days = c.group_by("DIRECTION_SK").agg(pl.col("date").n_unique().alias("days"))
    h = (
        c.with_columns(pl.col("time").dt.hour().alias("hour"))
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


def calendar(start: Dates = None, end: Dates = None) -> pl.DataFrame:
    """TfNSW's calendar: day type (weekday, weekend, public holiday), holiday names, school holidays."""
    d = pl.read_csv(RAW / "dates.csv", infer_schema_length=0).select(
        pl.col("Date").str.slice(0, 10).str.to_date().alias("date"), "Day type", "Public holiday", "School holiday")
    return _period(d.lazy(), start, end).collect()


def events() -> pl.DataFrame:
    """A hand-curated list of real-world events seen in the counts (not exhaustive)."""
    return pl.read_csv(ROOT / "events.csv")


# --- the brief ---------------------------------------------------------------
BRIEF = """\
## Purpose

The cleaned data is used mainly for weekly totals per series. A series is one continuous line of counts
for one direction of travel at a site; where a site's counter was replaced, or several counters ran
there, a series is made of those counters' directions over time. Decide what should change so that the
weekly totals are right, and define the series. Problems that change a week's total matter most;
problems that only move counts between 15-minute slots within a day matter little.

## The counters

- **Piezo**: a pressure-sensitive strip across the path detects wheels. Two sensor lines give the
  direction of travel from which one is crossed first. Some units report several records
  ("channels", e.g. one per sensor or lane) for the same direction and slot; they are added together.
- **Tube**: pneumatic tubes across the path register an air pulse per axle; two tubes give direction
  and speed. Often installed temporarily.
- **Camera**: video analytics at an intersection. The intersection is divided into zones (road lanes,
  cycleway, footpaths, crossings); each zone is a "site" with its own directions, labelled IN
  (towards the intersection), OUT (away) or NONE (crossings). A rider is counted in each zone they
  pass through, so across a whole camera the IN and OUT totals should be similar. The camera
  classifies each road user (bicycle, pedestrian, vehicle); only bicycles are in this data.

## The data

- A **slot** is a 15-minute interval, 0 (00:00-00:14) to 95 (23:45-23:59), in local Sydney clock time.
- A **record** is one row as published by TfNSW. `raw` is the sum of a slot's records, as the TfNSW
  dashboard shows it. `count` is after the automatic fixes below; null means set to missing.
- Records have a status: "good", or "warning" (always a count of 0). TfNSW flags many, not all, days
  with a zero total this way; warning records are treated as zeros like any other.
- VivaCity cameras publish their slots in UTC. The cleaned data (`clean`, `daily`, `weekly`, ...) is
  shifted to Sydney time; `raw` and `channels` show the times as published.
- Some camera feeds leave out zero slots for some zones. Where a camera direction has data in a week
  but no zero slot, its absent slots on days the camera published anything are added as zeros
  (`records` = 0).
- `hourly_binned` marks days where each hour's count sits in one of its four slots and the other
  three are 0 (some early data is hourly).
- Speeds are reported by some counters only.

## Automatic fixes already applied (column `fix`)

- `duplicate_record`: in a slot with more records than the direction usually has that month, extra
  records that exactly repeat other records in the slot are dropped (over runs of days where every
  such slot matches, at least 20 of them non-zero).
- `duplicate_measurement`: a direction that normally has one record per slot carries a second record
  that tracks the first slot by slot; the first record is kept. Not applied to cameras.
- `halved`: a run of days where every non-zero count is even, at about twice the level of the
  surrounding weeks; counts divided by 2.
- `impossible_count`: a slot more than 20 times the direction's 99.9th percentile (and at least 200);
  set to missing, and `corrupt_day` for the rest of that counter-day.
- `zero_outage`: set to missing where the direction's usual pattern implies at least 20 bikes in its
  zeros, and either (a) a stretch of zeros and of bursts of 4 slots or fewer between zeros would
  normally have held at least 80% of a day's bikes and recorded under 10% of them (the bursts are set
  missing too), unless the stretch still recorded at least 2% of them and the counter's other directions
  recorded between 2% and 50% of their usual bikes meanwhile, or (b) a run of pure zeros that would
  normally have held at least 80% of a day's bikes, or (c) a run of zeros while the counter's other directions carried at least half their
  usual bikes. Other zeros are kept. Not applied to hourly_binned days.

## What to do

Review the group's whole record. Record a decision for every period whose data should change, and
for anything you cannot settle. Periods you do not mention are kept as they are. Real changes
(weather, holidays, closures, new infrastructure, events) are not faults.

Assume the data is correct unless you have a good explanation of how it went wrong, and the data
bears that explanation out. For example, every count being even at twice the usual level is strong
evidence of double counting. Small spikes and dips are plausibly noise or real riding, and are not
faults just because they are unusual.

Actions:
- `missing`: the values are wrong and cannot be recovered; set them to missing.
- `halve`: the values are exactly doubled.
- `direction_unreliable`: the split between directions is wrong but the total across them is right.
- `restore`: an automatic fix changed values that were right; restore the raw values.
- `uncertain`: something may be wrong but the evidence does not settle it.

Each decision has a scope: `SITE_SK`, `DIRECTION_SK` (null for every direction at the site) and dates.

## Series

Define the series for every site in the group that has more than one counter, or whose counter also
appears under another site. A series lists its parts: counter-directions (`COUNTER_SK`, `DIRECTION_SK`),
each optionally limited to dates. A part takes that counter-direction's data under any site. Decide
from the data which directions of different counters carry the same flow. Where two counters ran at
the same time, put both in one series only if they counted different bikes. Where you cannot tell
whether a later counter reads comparably to an earlier one, make them separate series. Sites you do not
define get one series per counter-direction.

You can sometimes learn things from the raw 15-minute records that summaries don't show; look at them
as well as the daily, weekly and monthly views.

Use only the `bikecount.review` tools (see `help(rv)` and the function docstrings) and this brief. Do
not read other files in the repository (source code, README, reviews, other data), and do not use the web.

## Verdict file

Write JSON to `{verdict_path}`:

```json
{{
  "group": "{group}",
  "decisions": [
    {{"action": "missing|halve|direction_unreliable|restore|uncertain", "SITE_SK": 0, "DIRECTION_SK": null,
      "start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "confidence": "high|medium|low",
      "diagnosis": "one sentence", "evidence": "the key numbers"}}
  ],
  "series": [
    {{"SITE_SK": 0, "name": "a short name for the direction of travel", "confidence": "high|medium|low",
      "parts": [{{"COUNTER_SK": 0, "DIRECTION_SK": 0, "start": null, "end": null}}],
      "evidence": "why these parts belong together"}}
  ],
  "summary": "two or three sentences on the group"
}}
```

An empty `decisions` list means the whole record stands as it is; an empty `series` list means every
counter-direction is its own series.
"""


def _md(df: pl.DataFrame) -> str:
    cols = df.columns
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join("" if v is None else str(v) for v in row) + " |" for row in df.rows()]
    return "\n".join(lines)


def write_brief(group: str) -> Path:
    """The brief for reviewing a group: its metadata and BRIEF. Verdicts go to reviews/verdicts/<group>.json."""
    m = meta(group)
    parts = [
        f"# Review group {group}",
        "",
        f"Load the tools with `from bikecount import review as rv`, running Python from {ROOT} as `uv run python - <<'EOF' ... EOF`.",
        "",
        "## Sites", _md(m["sites"]), "",
        "## Counters", _md(m["counters"]), "",
        "## Directions (dates with data)", _md(m["directions"]), "",
        BRIEF.format(group=group, verdict_path=VERDICTS / f"{group}.json"),
    ]
    BRIEFS.mkdir(parents=True, exist_ok=True)
    path = BRIEFS / f"{group}.md"
    path.write_text("\n".join(parts))
    return path


# --- decisions and series -------------------------------------------------------
DECISION_COLUMNS = ["review_group", "SITE_SK", "DIRECTION_SK", "start", "end", "action", "confidence", "diagnosis", "reviewer", "status"]
DECISION_KEY = ["review_group", "SITE_SK", "DIRECTION_SK", "start", "end", "action"]
SERIES = REVIEWS / "series.csv"
SERIES_COLUMNS = ["review_group", "SITE_SK", "series", "COUNTER_SK", "DIRECTION_SK", "start", "end", "confidence", "reviewer", "status"]
SERIES_KEY = ["review_group", "SITE_SK", "series", "COUNTER_SK", "DIRECTION_SK", "start", "end"]


def _keep_status(new: pl.DataFrame, path: Path, key: list[str], columns: list[str]) -> pl.DataFrame:
    """New rows are `proposed`; a status already set in `path` (e.g. `accepted`, `rejected`) is kept."""
    if path.exists():
        old = pl.read_csv(path, infer_schema_length=0).select(*key, pl.col("status").alias("kept"))
        new = new.join(old, on=key, how="left", nulls_equal=True).with_columns(pl.coalesce("kept", "status").alias("status")).drop("kept")
    new = new.select(columns).sort(key)
    new.write_csv(path)
    return new


def collect(reviewer: str = "count-reviewer") -> tuple[pl.DataFrame, pl.DataFrame]:
    """Gather every verdict in reviews/verdicts into reviews/decisions.csv and reviews/series.csv."""
    decisions, series = [], []
    for f in sorted(VERDICTS.glob("*.json")):
        v = json.loads(f.read_text())
        for d in v["decisions"]:
            decisions.append({"review_group": v["group"], "reviewer": reviewer, "status": "proposed",
                              **{k: d.get(k) for k in ("SITE_SK", "DIRECTION_SK", "start", "end", "action", "confidence", "diagnosis")}})
        for sr in v.get("series", []):
            for part in sr["parts"]:
                series.append({"review_group": v["group"], "SITE_SK": sr["SITE_SK"], "series": sr["name"], "confidence": sr.get("confidence"),
                               "reviewer": reviewer, "status": "proposed", **{k: part.get(k) for k in ("COUNTER_SK", "DIRECTION_SK", "start", "end")}})
    frame = lambda rows, cols: pl.DataFrame([{c: None if r.get(c) is None else str(r[c]) for c in cols} for r in rows], schema={c: pl.Utf8 for c in cols})
    return (
        _keep_status(frame(decisions, DECISION_COLUMNS), DECISIONS, DECISION_KEY, DECISION_COLUMNS),
        _keep_status(frame(series, SERIES_COLUMNS), SERIES, SERIES_KEY, SERIES_COLUMNS),
    )
