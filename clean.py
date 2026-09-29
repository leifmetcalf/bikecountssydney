"""Clean the raw 15-minute cycling counts (see download.py) by applying reviewers' decisions.

    uv run clean.py

reads data/raw and the review verdicts (reviews/verdicts), and writes data/clean:
    counts_15min.parquet  one row per direction and slot: SITE_SK, COUNTER_SK, DIRECTION_SK, date, time (local start of
                          the slot), workday (weekday other than a public holiday), records (raw records in the slot,
                          from the load that carries its count), raw (sum of all records, as the dashboard shows),
                          count (cleaned; null = missing), fix (the action that changed count), direction_unreliable
                          (the split between directions is wrong; the total is fine), hourly_binned (see below)
    weekly.parquet        bikes per series and week (Monday to Sunday) over the week's complete days: SITE_SK, series,
                          week, bikes, complete_days (7 = a full week), direction_unreliable
    series.csv            the counter-directions making up each series

A site is a counting location (SITE_SK), a counter a device (COUNTER_SK; a camera covers many sites), and a
direction one direction of travel at a site measured by one counter (DIRECTION_SK). The unit is a direction-slot:
one direction's count for one 15-minute slot (0-95) of one date, with any channel records summed the way the TfNSW
dashboard does. Camera "sites" are zones of one intersection: never sum them all. The Harbour Bridge ran a parallel
tube counter in 2021-22 that duplicates the piezo.

VivaCity cameras publish their slots in UTC. They are moved to Sydney time first, so that every decision's times mean
Sydney time. TfNSW loads a day's counts over the following days, so days on or after a counter's latest load are left
out until a later download completes them. Nothing else is changed automatically: every fix is a reviewer's decision (see review.py), applied in
this order:
  zero_fill             absent slots are zeros, on days the counter published anything (some camera feeds leave
                        zeros out)
  drop_duplicates       extra records that exactly repeat the slot's other records are dropped, in slots with more
                        records than the direction usually has that month
  subtract_other        the count of the counter's other direction at the site is subtracted (at least 0): the
                        direction also counted that direction's riders
  missing               set to missing
  scale                 multiplied by the decision's `factor` (rounded half to even, so halving loses no bikes on average)
  direction_unreliable  flagged: the split between directions is wrong, the total is right
Each action applies once to a slot, however many decisions cover it; overlapping `scale` decisions must agree on the
factor.
`uncertain` changes nothing, nor does `restore`, left from when some fixes were automatic. A decision covers SITE_SK,
DIRECTION_SK (null: every direction at the site) and start..end: dates, or slots as "YYYY-MM-DD HH:MM" (the slot's
start), both ends included. A null end marks a fault still going on at the review: it runs to the end of the record,
including data downloaded later.

Some early data is hourly: each hour's count sits in one of its four slots and the other three are 0. Those
direction-days are marked `hourly_binned`.

Weekly totals are built per series: one continuous line of counts for one direction of travel at a site, as
reviewers defined them where a counter was replaced or several ran at a site (TfNSW's direction labels are not always
consistent between counters). Every other counter-direction is a series of its own.

Every review group (sites linked by shared counters) is reviewed in full, aiming at accurate weekly totals:

    uv run python -c "import review; [review.write_brief(g) for g in review.groups()['review_group'].unique()]"
    # a reviewer (the count-reviewer agent in .claude/agents) follows data/review/briefs/<group>.md and
    # writes reviews/verdicts/<group>.json
    uv run clean.py

Reviewers see only the raw records, never earlier decisions. Every fix must follow from how the counts went wrong,
and the data must bear that out: scale by 0.5 where every bike was counted twice, never by a factor fitted to make a
counter agree with its neighbours or its past. When checking a verdict, reject any decision that fails this, and any
`missing` whose counts could have been recovered: a decision or series found wrong gets `"rejected": true` in its
verdict and is not applied. Reviewers describe fixes that no action provides in their
verdict's `proposals`, and say how the review tools could be better in `tools`. What reviewers are told, and what is withheld to avoid steering them, is recorded in
reviews/INFORMATION.md.
"""

import json
import shutil
from collections import Counter
from pathlib import Path

import polars as pl

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw"  # written by download.py
CLEAN = ROOT / "data" / "clean"
VERDICTS = ROOT / "reviews" / "verdicts"

KEYS = ["SITE_SK", "COUNTER_SK", "DIRECTION_SK"]
SYDNEY = "Australia/Sydney"
UTC_VENDORS = ["VivaCity"]  # cameras whose slots are in UTC: their daily profile peaks at 21-23h and 07-09h
HOURLY_MIN_NONZERO = 8  # a day whose non-zero slots (at least this many) all share one quarter-hour is hourly data
COMPLETE_SLOTS = 90  # a day counts as complete with this many of its 96 slots valid
ACTIONS = ["zero_fill", "drop_duplicates", "subtract_other", "missing", "scale", "direction_unreliable"]
NOTES = ["uncertain", "restore"]  # decisions that change nothing
FIXES = ["drop_duplicates", "subtract_other", "missing", "scale"]


# --- slot table ----------------------------------------------------------------
def counters() -> pl.DataFrame:
    return pl.read_csv(RAW / "counters.csv", infer_schema_length=0).select(pl.col("COUNTER_SK").cast(pl.Int16), "Technology", "Vendor name")


def slot_start(date: pl.Expr, slot: pl.Expr) -> pl.Expr:
    """(2019-05-01, 32) -> 2019-05-01 08:00."""
    return (date.cast(pl.Datetime("ms")) + pl.duration(minutes=slot.cast(pl.Int32) * 15)).cast(pl.Datetime("ms"))


def site_files(sites: list[int] | None = None) -> list[Path]:
    """The raw count files of every site, or only of `sites`."""
    counts = RAW / "counts"
    return [counts / "*.parquet"] if sites is None else sorted(f for s in sites for f in counts.glob(f"site_{s:04d}_*.parquet"))


def records(sites: list[int] | None = None) -> pl.LazyFrame:
    """Raw records, of every site or only `sites`, with VivaCity's UTC slots moved to Sydney time."""
    utc = counters().filter(pl.col("Vendor name").is_in(UTC_VENDORS))["COUNTER_SK"].implode()
    local = slot_start(pl.col("date"), pl.col("slot")).dt.replace_time_zone("UTC").dt.convert_time_zone(SYDNEY)
    shift = pl.col("COUNTER_SK").is_in(utc)
    return pl.scan_parquet(site_files(sites)).with_columns(
        pl.when(shift).then(local.dt.date()).otherwise(pl.col("date")).alias("date"),
        pl.when(shift).then((local.dt.hour() * 4 + local.dt.minute() // 15).cast(pl.UInt8)).otherwise(pl.col("slot")).alias("slot"),
    )


def slot_table(sites: list[int] | None = None) -> pl.DataFrame:
    """Direction-slots from the raw records: all records summed (`raw`), as the dashboard shows.

    A slot's records can come from two loads: recent data often gets a second record in the next day's load, and
    one of the two is 0. `records` describes the load with the most bikes (the earlier one on a tie), its date is
    `load`, and IDs are only compared within it: TfNSW numbers the rows of each load from 1.
    """
    count = pl.col("TOTAL_15MIN_COUNT")
    per_load = records(sites).group_by(*KEYS, "date", "slot", pl.col("ADDED_UPDATED_DATETIME_SYDNEY").alias("load")).agg(
        count.sum().alias("n"), pl.len().alias("records")
    )
    main = pl.col("records", "load").sort_by("n", "load", descending=[True, False]).first()
    return (
        per_load.group_by(*KEYS, "date", "slot")
        .agg(pl.col("n").sum().cast(pl.UInt16).alias("raw"), main)
        .with_columns(pl.col("records").cast(pl.UInt8))
        .collect(engine="streaming")
        .sort(*KEYS, "date", "slot")
    )


def duplicate_values(slots: pl.DataFrame, sites: list[int] | None = None) -> pl.DataFrame:
    """Slots with more records than their direction usually has that month (the month's most common daily mode).

    `dedup` is the count with the extra records that exactly repeat other records in the slot dropped (the largest
    repeats where the choice is ambiguous), `dropped` what that removes, and `matched` whether every extra record
    repeats another.
    """
    month = pl.col("date").dt.truncate("1mo").alias("month")
    daily_mode = slots.group_by("DIRECTION_SK", "date").agg(pl.col("records").mode().min().alias("m"))
    usual = daily_mode.group_by("DIRECTION_SK", month).agg(pl.col("m").mode().min().alias("usual"))
    extra = (
        slots.select("DIRECTION_SK", "date", "slot", "load", "records", month).join(usual, on=["DIRECTION_SK", "month"])
        .filter(pl.col("records") > pl.col("usual")).select("DIRECTION_SK", "date", "slot", "load", "usual")
    )
    values = (
        records(sites)
        .select("DIRECTION_SK", "date", "slot", pl.col("ADDED_UPDATED_DATETIME_SYDNEY").alias("load"), "TOTAL_15MIN_COUNT")
        .join(extra.lazy(), on=["DIRECTION_SK", "date", "slot", "load"])
        .group_by("DIRECTION_SK", "date", "slot", "usual", "TOTAL_15MIN_COUNT").agg(pl.len().alias("k"))
        .collect(engine="streaming")
    )
    v = pl.col("TOTAL_15MIN_COUNT").cast(pl.Int64)
    per_slot = values.group_by("DIRECTION_SK", "date", "slot").agg(
        (pl.col("k").sum() - pl.col("usual").first()).alias("excess"),
        (v * pl.col("k")).sum().alias("total"),
        # values that occur in pairs, once per pair
        v.repeat_by(pl.col("k") // 2).list.explode(keep_nulls=False, empty_as_null=False).sort(descending=True).alias("repeats"),
    )
    dropped = pl.col("repeats").list.head(pl.col("excess")).list.sum()
    return per_slot.select(
        "DIRECTION_SK", "date", "slot", (pl.col("total") - dropped).alias("dedup"), dropped.alias("dropped"),
        (pl.col("repeats").list.len() >= pl.col("excess")).alias("matched"),
    )


def groups() -> pl.DataFrame:
    """SITE_SK -> review_group. Sites linked by a shared counter, or counters by a shared site, are reviewed together;
    a group is named after its lowest SITE_SK (e.g. G0101). Nothing in a group depends on data outside it, so each is
    cleaned on its own."""
    pairs = pl.scan_parquet(RAW / "counts" / "*.parquet").select("SITE_SK", "COUNTER_SK").unique().collect(engine="streaming").rows()
    parent: dict = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for site, counter in pairs:
        parent[find(("site", site))] = find(("counter", counter))
    members: dict = {}
    for site, _ in pairs:
        members.setdefault(find(("site", site)), set()).add(site)
    return pl.DataFrame(
        [(site, f"G{min(sites):04d}") for sites in members.values() for site in sites],
        schema={"SITE_SK": pl.Int16, "review_group": pl.Utf8}, orient="row",
    ).sort("review_group", "SITE_SK")


def hourly_binned(slots: pl.DataFrame) -> pl.Series:
    """Direction-days of hourly data: every non-zero slot falls on the same quarter of the hour."""
    nz = pl.col("raw") > 0
    quarter = pl.col("slot") % 4
    by = ["DIRECTION_SK", "date"]
    return slots.select(((nz.sum().over(by) >= HOURLY_MIN_NONZERO) & (quarter.filter(nz).n_unique().over(by) == 1)).alias("hourly_binned"))["hourly_binned"]


def with_workday(df: pl.DataFrame) -> pl.DataFrame:
    """`workday`: a weekday other than a public holiday (Monday to Friday before 2009, where the Date table starts)."""
    dates = pl.read_csv(RAW / "dates.csv", infer_schema_length=0).select(
        pl.col("Date").str.slice(0, 10).str.to_date().alias("date"), (pl.col("Day type") == "Weekday (excl. PH)").alias("workday")
    )
    return df.join(dates, on="date", how="left").with_columns(pl.col("workday").fill_null(pl.col("date").dt.weekday() <= 5))


# --- review decisions --------------------------------------------------------
def reviewed(kind: str) -> list[dict]:
    """Every reviewer's `decisions` or `series`, except those marked rejected."""
    verdicts = [json.loads(f.read_text()) for f in sorted(VERDICTS.glob("*.json"))]
    return [x for v in verdicts for x in v[kind] if not x.get("rejected")]


def decision_table() -> pl.DataFrame:
    """Every reviewer's decisions that change the data: action, factor, SITE_SK, DIRECTION_SK, start and end (datetimes)."""
    schema = {"SITE_SK": pl.Int16, "DIRECTION_SK": pl.Int16, "start": pl.Utf8, "end": pl.Utf8, "action": pl.Utf8, "factor": pl.Float64}
    dec = pl.DataFrame([{k: d.get(k) for k in schema} for d in reviewed("decisions")], schema=schema)
    bad = set(dec["action"]) - set(ACTIONS) - set(NOTES)
    if bad:
        raise SystemExit(f"unknown actions in {VERDICTS}: {bad}")
    if dec.filter((pl.col("action") == "scale") & ~(pl.col("factor") > 0).fill_null(False)).height:
        raise SystemExit(f"a scale decision in {VERDICTS} has no positive factor")
    # a date alone runs from the day's first slot, or to its last
    at = lambda c, hhmm: pl.when(pl.col(c).str.len_chars() == 10).then(pl.concat_str(c, pl.lit(hhmm))).otherwise(pl.col(c))
    return dec.filter(pl.col("action").is_in(ACTIONS)).with_columns(
        at("start", " 00:00").str.to_datetime("%Y-%m-%d %H:%M", time_unit="ms"),
        at("end", " 23:45").str.to_datetime("%Y-%m-%d %H:%M", time_unit="ms"),
    )


def decision_days(slots: pl.DataFrame, dec: pl.DataFrame) -> pl.DataFrame:
    """The decisions covering `slots`, one row per direction and day: the columns of `dec`, COUNTER_SK and date.
    A null end (an ongoing fault) becomes the last slot of `slots`."""
    # a null DIRECTION_SK covers every direction at the site
    keys = slots.select(*KEYS).unique()
    dec = pl.concat([
        dec.filter(pl.col("DIRECTION_SK").is_not_null()).join(keys.select("COUNTER_SK", "DIRECTION_SK").unique(), on="DIRECTION_SK"),
        dec.filter(pl.col("DIRECTION_SK").is_null()).drop("DIRECTION_SK").join(keys, on="SITE_SK"),
    ], how="diagonal").with_columns(pl.col("end").fill_null(slot_start(pl.lit(slots["date"].max()), pl.lit(95))))
    return dec.with_columns(pl.date_ranges(pl.col("start").dt.date(), pl.col("end").dt.date()).alias("date")).explode("date", empty_as_null=True)


def mark(slots: pl.DataFrame, where: pl.Expr, fix: str, value: pl.Expr | None = None) -> pl.DataFrame:
    """Where `where` holds and the slot still has a count, replace the count (missing by default) and record why."""
    hit = where.fill_null(False) & pl.col("count").is_not_null()
    return slots.with_columns(
        pl.when(hit).then(value).otherwise(pl.col("count")).alias("count"),
        pl.when(hit).then(pl.lit(fix)).otherwise(pl.col("fix")).alias("fix"),
    )


def apply_decisions(slots: pl.DataFrame, dec: pl.DataFrame, sites: list[int]) -> pl.DataFrame:
    """Apply the decisions (see decision_table) to the slots of `sites` in the order of ACTIONS, setting `count`, `fix`
    and `direction_unreliable`."""
    dec = decision_days(slots, dec)
    in_scope = pl.col("time").is_between(pl.col("start"), pl.col("end"))
    slot = pl.DataFrame({"slot": pl.arange(0, 96, eager=True).cast(pl.UInt8)})

    # zero_fill: absent slots on days the counter published anything
    published = slots.select("COUNTER_SK", "date").unique()
    fill = (
        dec.filter(pl.col("action") == "zero_fill").join(published, on=["COUNTER_SK", "date"]).join(slot, how="cross")
        .with_columns(slot_start(pl.col("date"), pl.col("slot")).alias("time")).filter(in_scope)
        .select(*KEYS, "date", "slot").unique().join(slots, on=["DIRECTION_SK", "date", "slot"], how="anti")
    )
    slots = pl.concat([slots, fill.with_columns(pl.lit(0, pl.UInt16).alias("raw"), pl.lit(0, pl.UInt8).alias("records"))], how="diagonal_relaxed")
    slots = slots.sort(*KEYS, "date", "slot").with_columns(
        slot_start(pl.col("date"), pl.col("slot")).alias("time"), pl.col("raw").alias("count"), pl.lit(None, pl.Utf8).alias("fix")
    )

    per_slot = (
        slots.select("DIRECTION_SK", "date", "time").join(dec.filter(pl.col("action") != "zero_fill"), on=["DIRECTION_SK", "date"])
        .filter(in_scope).group_by("DIRECTION_SK", "time")
        .agg(pl.col("action").unique().alias("actions"), pl.col("factor").drop_nulls().unique().alias("factors"))
    )
    clash = per_slot.filter(pl.col("factors").list.len() > 1)
    if clash.height:
        raise SystemExit(f"overlapping scale decisions disagree on the factor:\n{clash}")
    slots = slots.join(per_slot, on=["DIRECTION_SK", "time"], how="left")
    act = pl.col("actions")
    slots = slots.join(duplicate_values(slots, sites).select("DIRECTION_SK", "date", "slot", "dedup"), on=["DIRECTION_SK", "date", "slot"], how="left")
    slots = mark(slots, act.list.contains("drop_duplicates") & pl.col("dedup").is_not_null(), "drop_duplicates", pl.col("dedup").cast(pl.UInt16))
    other = pl.col("count").cast(pl.Int32).sum().over("SITE_SK", "COUNTER_SK", "time") - pl.col("count").cast(pl.Int32)
    slots = mark(slots, act.list.contains("subtract_other"), "subtract_other", (pl.col("count").cast(pl.Int32) - other).clip(0).cast(pl.UInt16))
    slots = mark(slots, act.list.contains("missing"), "missing")
    slots = mark(slots, act.list.contains("scale"), "scale", (pl.col("count") * pl.col("factors").list.first()).round(0, "half_to_even").cast(pl.UInt16))
    return slots.with_columns(act.list.contains("direction_unreliable").fill_null(False).alias("direction_unreliable")).drop("actions", "factors", "dedup")


# --- series and weekly totals -------------------------------------------------
def series_table() -> pl.DataFrame:
    """Every reviewer's series parts: SITE_SK, series, COUNTER_SK, DIRECTION_SK, start, end."""
    schema = {"SITE_SK": pl.Int16, "series": pl.Utf8, "COUNTER_SK": pl.Int16, "DIRECTION_SK": pl.Int16, "start": pl.Utf8, "end": pl.Utf8}
    rows = [{"SITE_SK": s["SITE_SK"], "series": s["name"], **p} for s in reviewed("series") for p in s["parts"]]
    return pl.DataFrame([{k: r.get(k) for k in schema} for r in rows], schema=schema).with_columns(
        pl.col("start").str.to_date(), pl.col("end").str.to_date()
    )


def series_parts(slots: pl.DataFrame, reviewed_parts: pl.DataFrame) -> pl.DataFrame:
    """The counter-directions in `slots` making up each series: SITE_SK, series, COUNTER_SK, DIRECTION_SK, start, end,
    match_site.

    Reviewed series (see series_table) take a counter-direction's data under any site. Every counter-direction they
    leave out becomes a series of its own at its site (`match_site`), named after its direction, and after its counter
    too where the site has several counters.
    """
    pairs = slots.select(*KEYS).unique().with_columns((pl.col("COUNTER_SK").n_unique().over("SITE_SK") > 1).alias("several"))
    reviewed_parts = reviewed_parts.join(pairs.select("COUNTER_SK", "DIRECTION_SK").unique(), on=["COUNTER_SK", "DIRECTION_SK"], how="semi")
    rest = pairs.join(reviewed_parts.select("COUNTER_SK", "DIRECTION_SK").unique(), on=["COUNTER_SK", "DIRECTION_SK"], how="anti")
    dims = lambda name, key, *cols: pl.read_csv(RAW / name, infer_schema_length=0).select(pl.col(key).cast(pl.Int16), *cols)
    rest = rest.join(dims("directions.csv", "DIRECTION_SK", "Orientation description", "Location in/out"), on="DIRECTION_SK", how="left")
    rest = rest.join(dims("counters.csv", "COUNTER_SK", "Counter ID"), on="COUNTER_SK", how="left")
    inout = pl.col("Location in/out")
    name = pl.concat_str(
        pl.col("Orientation description").fill_null(pl.col("DIRECTION_SK").cast(pl.Utf8)),
        pl.when(inout.is_in(["IN", "OUT"])).then(pl.concat_str(pl.lit(" ("), inout, pl.lit(")"))).otherwise(pl.lit("")),
        pl.when("several").then(pl.concat_str(pl.lit(" [counter "), pl.col("Counter ID"), pl.lit("]"))).otherwise(pl.lit("")),
    )
    defaults = rest.select("SITE_SK", name.alias("series"), "COUNTER_SK", "DIRECTION_SK", pl.lit(None, pl.Date).alias("start"),
                           pl.lit(None, pl.Date).alias("end"), pl.col("SITE_SK").alias("match_site"))
    reviewed_parts = reviewed_parts.with_columns(pl.lit(None, pl.Int16).alias("match_site"))
    return pl.concat([reviewed_parts, defaults]).sort("SITE_SK", "series", "COUNTER_SK", "DIRECTION_SK", "start", "end")


def weekly(final: pl.DataFrame, parts: pl.DataFrame) -> pl.DataFrame:
    """Bikes per series and week (Monday to Sunday) over the week's complete days; `complete_days` = 7 is a full week.

    A series-day is complete when every part with data that day has COMPLETE_SLOTS valid slots.
    `direction_unreliable` marks weeks where a reviewer found the split between directions wrong on some day.
    """
    x = final.select("SITE_SK", "COUNTER_SK", "DIRECTION_SK", "date", "count", "direction_unreliable").join(
        parts.rename({"SITE_SK": "series_site"}), on=["COUNTER_SK", "DIRECTION_SK"]
    ).filter(
        (pl.col("match_site").is_null() | (pl.col("match_site") == pl.col("SITE_SK")))
        & (pl.col("start").is_null() | (pl.col("date") >= pl.col("start")))
        & (pl.col("end").is_null() | (pl.col("date") <= pl.col("end")))
    )
    part_day = x.group_by("series_site", "series", "COUNTER_SK", "DIRECTION_SK", "date").agg(
        pl.col("count").cast(pl.Int64).sum().alias("bikes"), pl.col("count").is_not_null().sum().alias("valid"),
        pl.col("direction_unreliable").any(),
    )
    day = part_day.group_by("series_site", "series", "date").agg(
        pl.col("bikes").sum(), (pl.col("valid") >= COMPLETE_SLOTS).all().alias("complete"), pl.col("direction_unreliable").any(),
    )
    return (
        day.filter("complete").group_by("series_site", "series", pl.col("date").dt.truncate("1w").alias("week"))
        .agg(pl.col("bikes").sum(), pl.len().cast(pl.UInt8).alias("complete_days"), pl.col("direction_unreliable").any())
        .rename({"series_site": "SITE_SK"}).sort("SITE_SK", "series", "week")
    )


def clean_group(sites: list[int], dec: pl.DataFrame) -> pl.DataFrame:
    """The cleaned direction-slots of one review group's sites. Days on or after a counter's latest load are left out:
    TfNSW loads a day's counts over the following days, so those are not final yet."""
    last = records(sites).group_by("COUNTER_SK").agg(pl.col("ADDED_UPDATED_DATETIME_SYDNEY").max().alias("last_load")).collect()
    final = apply_decisions(slot_table(sites), dec, sites)
    final = final.join(last, on="COUNTER_SK").filter(pl.col("date") < pl.col("last_load")).drop("last_load")
    final = with_workday(final)
    return final.with_columns(hourly_binned(final)).select(
        *KEYS, "date", "time", "workday", "records",
        pl.col("raw").cast(pl.UInt16), pl.col("count").cast(pl.UInt16),
        pl.col("fix").cast(pl.Enum(FIXES)), "direction_unreliable", "hourly_binned",
    ).sort(*KEYS, "time")


def main() -> None:
    """Clean one review group at a time, so memory stays at the size of the largest group."""
    CLEAN.mkdir(parents=True, exist_ok=True)
    parts_dir = CLEAN / "parts"
    shutil.rmtree(parts_dir, ignore_errors=True)
    parts_dir.mkdir()
    dec, reviewed_parts = decision_table(), series_table()
    fixes, series, weeks = Counter(), [], []
    for group, sites in groups().group_by("review_group").agg("SITE_SK").sort("review_group").iter_rows():
        final = clean_group(sites, dec)
        final.write_parquet(parts_dir / f"{group}.parquet")
        fixes.update(dict(final.group_by("fix").len().iter_rows()))
        parts = series_parts(final, reviewed_parts)
        series.append(parts)
        weeks.append(weekly(final, parts))
    pl.scan_parquet(parts_dir / "*.parquet").sink_parquet(CLEAN / "counts_15min.parquet")
    shutil.rmtree(parts_dir)
    for fix, n in fixes.most_common():
        print(f"  {fix or 'unchanged'}: {n:,} slots")
    print(f"{sum(fixes.values()):,} cleaned direction-slots -> {CLEAN / 'counts_15min.parquet'}")
    series = pl.concat(series).sort("SITE_SK", "series", "COUNTER_SK", "DIRECTION_SK", "start", "end")
    series.write_csv(CLEAN / "series.csv")
    week = pl.concat(weeks).sort("SITE_SK", "series", "week")
    week.write_parquet(CLEAN / "weekly.parquet")
    print(f"{week.height:,} series-weeks in {series.select('SITE_SK', 'series').n_unique():,} series -> {CLEAN / 'weekly.parquet'}")


if __name__ == "__main__":
    main()
