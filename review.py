"""Reviewing counter data: tools for reviewers, and the brief they are given.

Every review group (sites linked by shared counters) is reviewed in full. Reviewers (people or agents)
use these tools from Python. They show the counts as published, before any decisions:

    import review as rv
    rv.meta([SITE])                               # sites, counters and directions
    rv.overview([SITE])                           # per direction and month: coverage, level, records per slot
    rv.weekly([SITE], "YYYY-MM-DD", "YYYY-MM-DD") # weekly totals per direction (wide=True: a column per direction)
    rv.monthly([SITE], "YYYY-MM-DD", "YYYY-MM-DD")  # mean bikes per complete day, per direction and month
    rv.daily([SITE], "YYYY-MM-DD", "YYYY-MM-DD")  # daily totals per direction (wide=True: a column per direction)
    rv.hourly([SITE], "YYYY-MM-DD", "YYYY-MM-DD") # mean bikes per hour of day per direction
    rv.slots([SITE], "YYYY-MM-DD", "YYYY-MM-DD")  # 15-minute slots
    rv.raw([SITE], "YYYY-MM-DD", "YYYY-MM-DD")    # raw records exactly as downloaded
    rv.channels([SITE], "YYYY-MM-DD", "YYYY-MM-DD")  # the records behind each slot
    rv.neighbours(SITE)                           # other sites nearby
    rv.compare(SITE, [OTHER])                     # weekly (or daily) totals against other sites, with ratios
    rv.directions([SITE])                         # balance between a site's directions, and whether one mirrors the other
    rv.counter_days([SITE])                       # per counter and day: directions published, bikes IN / OUT / NONE
    rv.network("YYYY-MM-DD", "YYYY-MM-DD")        # per day, whole dataset: sites at 0 or "warning", total bikes
    rv.calendar()                                 # public and school holidays
    rv.weather("YYYY-MM-DD", "YYYY-MM-DD")        # daily rain and maximum temperature in central Sydney
    rv.events()                                   # hand-curated list of known events

and tools that list candidates for common faults, for the reviewer to judge:

    rv.zeros([SITE])                              # stretches of 0 (6 hours or more), daytime hours, usual bikes; counter=True
    rv.doubled([SITE])                            # runs of days where every non-zero count is even, with their level
    rv.duplicates([SITE])                         # runs of days where slots have extra records that repeat others
    rv.spikes([SITE])                             # bursts far above what the direction usually records at that time
    rv.absent_zeros([SITE])                       # camera weeks with data but not a single zero slot

What reviewers are told, and why, is recorded in reviews/INFORMATION.md.
"""

import math
from pathlib import Path

import polars as pl

import clean
from clean import COMPLETE_SLOTS, KEYS, RAW, ROOT, VERDICTS, groups

BRIEFS = ROOT / "data" / "review" / "briefs"
Dates = str | None
MIN_EVEN_NONZERO = 20  # non-zero slots an even-only run needs before `doubled` lists it (P <= 0.5^20 by chance)
REFERENCE_DAYS = 60  # days either side of an even-only run that `doubled` compares it with


def slot_label(slot: pl.Expr) -> pl.Expr:
    """32 -> '08:00 - 08:14', TfNSW's label for a slot."""
    minutes = slot.cast(pl.Int32) * 15
    hhmm = lambda m: pl.concat_str([(m // 60).cast(pl.Utf8).str.zfill(2), pl.lit(":"), (m % 60).cast(pl.Utf8).str.zfill(2)])
    return pl.concat_str([hhmm(minutes), pl.lit(" - "), hhmm(minutes + 14)])


def _period(df: pl.DataFrame, start: Dates, end: Dates, col: str = "date") -> pl.DataFrame:
    if start:
        df = df.filter(pl.col(col) >= pl.lit(start).str.to_date())
    if end:
        df = df.filter(pl.col(col) <= pl.lit(end).str.to_date())
    return df


def _dims(name: str) -> pl.DataFrame:
    return pl.read_csv(RAW / name, infer_schema_length=0)


def _runs(by: list[str], order: str, step: pl.Expr) -> pl.Expr:
    """Run number of consecutive rows (sorted by `by` and `order`), where `step` is the gap between neighbours."""
    return (pl.col(order).diff() != step).over(by).fill_null(True).cum_sum()


def group_sites(group: str) -> list[int]:
    return sorted(groups().filter(pl.col("review_group") == group)["SITE_SK"].to_list())


# --- views ---------------------------------------------------------------------
def slots(sites: list[int], start: Dates = None, end: Dates = None) -> pl.DataFrame:
    """Direction-slots: `count` is the sum of the slot's records (as the TfNSW dashboard shows it), `records` how many
    records it has, `time` its local start; `workday` and `hourly_binned` as described in the brief."""
    s = clean.with_workday(_period(clean.slot_table(sites), start, end))
    return s.with_columns(clean.hourly_binned(s), clean.slot_start(pl.col("date"), pl.col("slot")).alias("time")).select(
        *KEYS, "date", "slot", "time", "workday", "records", pl.col("raw").alias("count"), "hourly_binned"
    ).sort(*KEYS, "time")


def meta(sites: list[int]) -> dict[str, pl.DataFrame]:
    """The sites, their counters, and their directions with the dates they have data."""
    span = (
        clean.slot_table(sites).group_by(*KEYS).agg(pl.col("date").min().alias("first"), pl.col("date").max().alias("last"))
        .sort(*KEYS)
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
    r = _period(pl.scan_parquet(clean.site_files(sites)), start, end).collect()
    return r.with_columns(slot_label(pl.col("slot")).alias("slot_label")).sort("DIRECTION_SK", "date", "slot", "ID")


def daily(sites: list[int], start: Dates = None, end: Dates = None, wide: bool = False) -> pl.DataFrame:
    """Per direction and day: total, slots with data, records per slot, odd and non-zero slots. `wide=True` gives
    one column of totals per direction instead."""
    d = (
        slots(sites, start, end)
        .group_by(*KEYS, "date")
        .agg(
            pl.col("count").cast(pl.Int32).sum().alias("count"),
            pl.len().alias("slots"),
            pl.col("records").cast(pl.Float32).mean().round(2).alias("records_per_slot"),
            (pl.col("count") % 2 == 1).sum().alias("odd_slots"),
            (pl.col("count") > 0).sum().alias("nonzero_slots"),
        )
        .with_columns(pl.col("date").dt.strftime("%a").alias("weekday"))
        .sort("DIRECTION_SK", "date")
    )
    return d.pivot(on="DIRECTION_SK", index=["date", "weekday"], values="count", sort_columns=True).sort("date") if wide else d


def weekly(sites: list[int], start: Dates = None, end: Dates = None, wide: bool = False) -> pl.DataFrame:
    """Per direction and week (Monday to Sunday): total, complete days, share of the week's slots with data.
    `wide=True` gives one column of totals per direction instead."""
    w = (
        daily(sites, start, end).group_by(*KEYS, pl.col("date").dt.truncate("1w").alias("week"))
        .agg(
            pl.col("count").sum(),
            (pl.col("slots") >= COMPLETE_SLOTS).sum().alias("complete_days"),
            (pl.col("slots").sum() / (7 * 96)).round(3).alias("slot_share"),
        )
        .sort("DIRECTION_SK", "week")
    )
    return w.pivot(on="DIRECTION_SK", index="week", values="count", sort_columns=True).sort("week") if wide else w


def monthly(sites: list[int], start: Dates = None, end: Dates = None) -> pl.DataFrame:
    """Mean bikes per complete day, per direction and month."""
    d = daily(sites, start, end).filter(pl.col("slots") >= COMPLETE_SLOTS)
    return (
        d.group_by(*KEYS, pl.col("date").dt.truncate("1mo").alias("month"))
        .agg(pl.col("count").mean().round(0).alias("per_day"), pl.len().alias("days"))
        .sort("DIRECTION_SK", "month")
    )


def overview(sites: list[int]) -> pl.DataFrame:
    """One row per direction and month: days with data, complete days, mean bikes per complete day, and records per
    slot."""
    d = daily(sites)
    complete = pl.col("slots") >= COMPLETE_SLOTS
    return (
        d.group_by(*KEYS, pl.col("date").dt.truncate("1mo").alias("month"))
        .agg(
            pl.len().alias("days"), complete.sum().alias("complete_days"),
            pl.col("count").filter(complete).mean().round(0).alias("per_day"),
            pl.col("records_per_slot").mean().round(2),
        )
        .sort("SITE_SK", "DIRECTION_SK", "month")
    )


def hourly(sites: list[int], start: Dates, end: Dates, workday: bool = True) -> pl.DataFrame:
    """Mean bikes per hour of day, per direction (columns are hours 0-23)."""
    c = slots(sites, start, end).filter(pl.col("workday") == workday)
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
    files = clean.site_files([int(x) for x in near["SITE_SK"]])
    if not files:
        return pl.DataFrame()
    span = pl.scan_parquet(files).group_by("SITE_SK", "COUNTER_SK").agg(
        pl.col("date").min().alias("first"), pl.col("date").max().alias("last")).collect()
    counters = _dims("counters.csv").select(pl.col("COUNTER_SK").cast(pl.Int16), "Technology")
    out = near.select(pl.col("SITE_SK").cast(pl.Int16), "Site name", "km").join(span, on="SITE_SK").join(counters, on="COUNTER_SK", how="left")
    if not cameras:
        out = out.filter(pl.col("Technology") != "CAMERA")
    return out.sort("km")


def compare(site: int, others: list[int], start: Dates = None, end: Dates = None, by: str = "week") -> pl.DataFrame:
    """Bikes at `site` and at each of `others` (all directions), per week over the days on which every one of them is
    complete (`days`), or per day (`by="day"`, null where a site's day is incomplete), with the ratio of `site` to each
    other site. A steady ratio means the sites move together; a step or drift points at one of them."""
    d = daily([site, *others], start, end)
    day = d.group_by("SITE_SK", "date").agg(
        pl.when((pl.col("slots") >= COMPLETE_SLOTS).all()).then(pl.col("count").sum()).alias("bikes"))
    wide = day.pivot(on="SITE_SK", index="date", values="bikes", sort_columns=True).sort("date")
    cols = [c for c in [str(site), *map(str, others)] if c in wide.columns]
    if by == "week":
        wide = wide.drop_nulls(cols).group_by(pl.col("date").dt.truncate("1w").alias("week")).agg(
            pl.col(cols).sum(), pl.len().alias("days")).sort("week")
    return wide.select(pl.exclude(cols), *cols, *[(pl.col(str(site)) / pl.col(o)).round(3).alias(f"ratio_{o}") for o in cols[1:]])


def directions(sites: list[int], start: Dates = None, end: Dates = None, by: str = "week") -> pl.DataFrame:
    """For each pair of directions (a, b) at a site, per week (or `by="day"`): each one's bikes, their ratio, the
    correlation of their 15-minute counts, `equal`: the share of slots with bikes where both counts are the same, and
    `a_covers_b`: the share of slots where b has bikes in which a has at least as many (near 1 if a also counts b's
    riders), and `b_covers_a` the other way round."""
    s = _period(slots(sites), start, end).select("SITE_SK", "DIRECTION_SK", "date", "time", pl.col("count").cast(pl.Float64))
    j = s.rename({"DIRECTION_SK": "a", "count": "ca"}).join(s.rename({"DIRECTION_SK": "b", "count": "cb"}), on=["SITE_SK", "date", "time"])
    j = j.filter(pl.col("a") < pl.col("b"))
    period = pl.col("date").dt.truncate("1w").alias("week") if by == "week" else pl.col("date")
    any_bikes = (pl.col("ca") > 0) | (pl.col("cb") > 0)
    return j.group_by("SITE_SK", "a", "b", period).agg(
        pl.col("ca").sum().alias("bikes_a"), pl.col("cb").sum().alias("bikes_b"),
        (pl.col("ca").sum() / pl.col("cb").sum()).round(3).alias("ratio"),
        pl.corr("ca", "cb").round(3).alias("corr"),
        ((pl.col("ca") == pl.col("cb")) & any_bikes).sum().truediv(any_bikes.sum()).round(3).alias("equal"),
        (pl.col("ca") >= pl.col("cb")).filter(pl.col("cb") > 0).mean().round(3).alias("a_covers_b"),
        (pl.col("cb") >= pl.col("ca")).filter(pl.col("ca") > 0).mean().round(3).alias("b_covers_a"),
    ).sort("SITE_SK", "a", "b", period.meta.output_name())


def counter_days(sites: list[int], start: Dates = None, end: Dates = None) -> pl.DataFrame:
    """Per counter and day over the given sites: directions that published, slots, bikes, and bikes by the
    directions' in/out label (for cameras: IN towards the intersection, OUT away from it, NONE on crossings)."""
    s = _period(slots(sites), start, end).join(
        _dims("directions.csv").select(pl.col("DIRECTION_SK").cast(pl.Int16), pl.col("Location in/out").fill_null("NA")), on="DIRECTION_SK", how="left")
    base = s.group_by("COUNTER_SK", "date").agg(
        pl.col("DIRECTION_SK").n_unique().alias("directions"), pl.len().alias("slots"), pl.col("count").cast(pl.Int64).sum().alias("bikes"))
    label = s.group_by("COUNTER_SK", "date", "Location in/out").agg(pl.col("count").cast(pl.Int64).sum()).pivot(
        on="Location in/out", index=["COUNTER_SK", "date"], values="count", sort_columns=True)
    return base.join(label, on=["COUNTER_SK", "date"]).sort("COUNTER_SK", "date")


def network(start: str, end: str) -> pl.DataFrame:
    """Per day across every site in the dataset: sites with data, sites whose every record that day is 0, sites with
    a record flagged "warning", and `bikes`, the raw count of every site added up (naive: nothing is cleaned, and
    camera zones and parallel counters are all summed). Many sites at 0 on the same day point at the feed rather than
    at one counter."""
    days = (
        pl.scan_parquet(RAW / "counts" / "*.parquet")
        .filter(pl.col("date").is_between(pl.lit(start).str.to_date(), pl.lit(end).str.to_date()))
        .group_by("SITE_SK", "date").agg(pl.col("TOTAL_15MIN_COUNT").cast(pl.Int64).sum().alias("bikes"), (pl.col("Status") == 1).any().alias("warning"))
    )
    return days.group_by("date").agg(
        pl.len().alias("sites"), (pl.col("bikes") == 0).sum().alias("zero_sites"), pl.col("warning").sum().alias("warning_sites"),
        pl.col("bikes").sum(),
    ).sort("date").collect(engine="streaming")


def calendar(start: Dates = None, end: Dates = None) -> pl.DataFrame:
    """TfNSW's calendar: day type (weekday, weekend, public holiday), holiday names, school holidays."""
    d = pl.read_csv(RAW / "dates.csv", infer_schema_length=0).select(
        pl.col("Date").str.slice(0, 10).str.to_date().alias("date"), "Day type", "Public holiday", "School holiday")
    return _period(d, start, end)


def weather(start: Dates = None, end: Dates = None) -> pl.DataFrame:
    """Daily weather at Sydney (Observatory Hill), from the Bureau of Meteorology: `rain_mm` fell between 9am that day
    and 9am the next, so mostly during that day's riding; `max_temp_c` is the day's maximum. One station in the CBD:
    a fair guide for inner Sydney, a weaker one further out, and none for Wollongong.

    weather.csv keeps BOM's own convention (rain reported at 9am for the previous 24 hours). It was built from Climate
    Data Online products IDCJAC0009 (rain) and IDCJAC0010 (temperature), station 066062 until August 2020 and its
    replacement 066214 after; download those again to extend it.
    """
    w = pl.read_csv(ROOT / "weather.csv", try_parse_dates=True)
    rain = w.select((pl.col("date") - pl.duration(days=1)).alias("date"), pl.col("rain_mm_to_9am").alias("rain_mm"))
    return _period(w.join(rain, on="date", how="left").select("date", "rain_mm", "max_temp_c"), start, end)


def events() -> pl.DataFrame:
    """A hand-curated list of real-world events seen in the counts (not exhaustive)."""
    return pl.read_csv(ROOT / "events.csv")


# --- candidates for common faults ------------------------------------------------
def _usual(s: pl.DataFrame, stat: str) -> pl.DataFrame:
    """What each direction usually records in a slot: its mean or median count at that time of day, workdays and
    other days apart."""
    return s.group_by("DIRECTION_SK", "workday", "slot").agg(getattr(pl.col("count"), stat)().alias("usual"))


def zeros(sites: list[int], start: Dates = None, end: Dates = None, min_hours: float = 6, counter: bool = False) -> pl.DataFrame:
    """Stretches of consecutive slots with a count of 0 lasting at least `min_hours`, per direction; with
    `counter=True`, stretches where every direction of a counter that published is 0 at once. `daytime_hours` is
    the part between 06:00 and 20:00, and `usual_bikes` what the direction(s) record in those slots on average."""
    s = slots(sites)
    s = _period(s.join(_usual(s, "mean"), on=["DIRECTION_SK", "workday", "slot"], how="left"), start, end)
    by = ["COUNTER_SK"] if counter else KEYS
    if counter:
        s = s.group_by("COUNTER_SK", "time").agg(pl.col("count").sum(), pl.col("usual").sum())
    z = s.filter(pl.col("count") == 0).sort(*by, "time")
    return (
        z.with_columns(_runs(by, "time", pl.duration(minutes=15)).alias("run"))
        .group_by(*by, "run")
        .agg(
            pl.col("time").min().alias("start"), pl.col("time").max().alias("end"), (pl.len() / 4).alias("hours"),
            (pl.col("time").dt.hour().is_between(6, 19).sum() / 4).alias("daytime_hours"), pl.col("usual").sum().round(0).alias("usual_bikes"),
        )
        .filter(pl.col("hours") >= min_hours).drop("run").sort(*by, "start")
    )


def doubled(sites: list[int], start: Dates = None, end: Dates = None) -> pl.DataFrame:
    """Runs of consecutive days (with any bikes) on which every non-zero count is even, with at least MIN_EVEN_NONZERO
    non-zero slots. `level` is the run's median daily total over the median of days with odd counts within
    REFERENCE_DAYS either side, comparing workdays with workdays and other days with other days (null: none near)."""
    v = pl.col("count")
    day = slots(sites, start, end).group_by(*KEYS, "date", "workday").agg(
        v.cast(pl.Int64).sum().alias("tot"), (v > 0).sum().alias("nz"), (v % 2 == 1).sum().alias("odd"))
    inf = day.filter(pl.col("nz") > 0).sort("DIRECTION_SK", "date").with_columns((pl.col("odd") == 0).alias("even"))
    inf = inf.with_columns((pl.col("even") != pl.col("even").shift(1)).over("DIRECTION_SK").fill_null(True).cum_sum().alias("run"))
    runs = (
        inf.filter("even").group_by(*KEYS, "run")
        .agg(pl.col("date").min().alias("start"), pl.col("date").max().alias("end"), pl.len().alias("days"), pl.col("nz").sum().alias("nonzero_slots"))
        .filter(pl.col("nonzero_slots") >= MIN_EVEN_NONZERO)
    )
    ref = inf.filter(~pl.col("even")).select("DIRECTION_SK", "date", "workday", "tot")
    near = runs.select("DIRECTION_SK", "run", "start", "end").join(ref, on="DIRECTION_SK").filter(
        pl.col("date").is_between(pl.col("start") - pl.duration(days=REFERENCE_DAYS), pl.col("start"), closed="left")
        | pl.col("date").is_between(pl.col("end"), pl.col("end") + pl.duration(days=REFERENCE_DAYS), closed="right")
    )
    ref_level = near.group_by("DIRECTION_SK", "run", "workday").agg(pl.col("tot").median().alias("ref"))
    level = (
        inf.filter("even").select("DIRECTION_SK", "run", "workday", "tot")
        .join(ref_level, on=["DIRECTION_SK", "run", "workday"], how="left")
        .group_by("DIRECTION_SK", "run").agg((pl.col("tot") / pl.col("ref")).median().round(2).alias("level"))
    )
    return runs.join(level, on=["DIRECTION_SK", "run"], how="left").drop("run").sort("DIRECTION_SK", "start")


def duplicates(sites: list[int], start: Dates = None, end: Dates = None) -> pl.DataFrame:
    """Runs of consecutive days on which slots have more records than their direction usually has that month:
    `slots` with extra records, `matched_slots` where every extra record exactly repeats another record in the slot,
    `nonzero_repeats` of those repeating a non-zero count, and `repeated_bikes`, the bikes the repeats add."""
    d = _period(clean.duplicate_values(clean.slot_table(sites), sites), start, end)
    days = d.group_by("DIRECTION_SK", "date").agg(
        pl.len().alias("slots"), pl.col("matched").sum().alias("matched_slots"),
        (pl.col("dropped") > 0).sum().alias("nonzero_repeats"), pl.col("dropped").sum().alias("repeated_bikes"),
    ).sort("DIRECTION_SK", "date")
    return (
        days.with_columns(_runs(["DIRECTION_SK"], "date", pl.duration(days=1)).alias("run"))
        .group_by("DIRECTION_SK", "run")
        .agg(pl.col("date").min().alias("start"), pl.col("date").max().alias("end"), pl.len().alias("days"),
             *[pl.col(c).sum() for c in ("slots", "matched_slots", "nonzero_repeats", "repeated_bikes")])
        .drop("run").sort("DIRECTION_SK", "start")
    )


def spikes(sites: list[int], start: Dates = None, end: Dates = None, ratio: float = 10, min_count: int = 20) -> pl.DataFrame:
    """Runs of consecutive slots each with at least `min_count` bikes and `ratio` times what the direction usually
    records at that time of day (its median, at least 1): `bikes` is what the run recorded and `usual` what it
    usually would."""
    s = slots(sites)
    s = _period(s.join(_usual(s, "median"), on=["DIRECTION_SK", "workday", "slot"], how="left"), start, end)
    hit = s.filter((pl.col("count") >= min_count) & (pl.col("count") >= ratio * pl.max_horizontal(pl.col("usual"), 1))).sort("DIRECTION_SK", "time")
    return (
        hit.with_columns(_runs(["DIRECTION_SK"], "time", pl.duration(minutes=15)).alias("run"))
        .group_by(*KEYS, "run")
        .agg(pl.col("time").min().alias("start"), pl.col("time").max().alias("end"), pl.len().alias("slots"),
             pl.col("count").cast(pl.Int64).sum().alias("bikes"), pl.col("usual").sum().round(0))
        .drop("run").sort("DIRECTION_SK", "start")
    )


def absent_zeros(sites: list[int], start: Dates = None, end: Dates = None) -> pl.DataFrame:
    """Runs of weeks (Monday to Sunday) in which a camera direction has data but not a single zero slot, with the
    slots it has."""
    cameras = clean.counters().filter(pl.col("Technology") == "CAMERA")["COUNTER_SK"].implode()
    w = (
        slots(sites, start, end).filter(pl.col("COUNTER_SK").is_in(cameras))
        .group_by(*KEYS, pl.col("date").dt.truncate("1w").alias("week"))
        .agg(pl.len().alias("slots"), (pl.col("count") == 0).sum().alias("zero_slots"))
        .filter(pl.col("zero_slots") == 0).sort("DIRECTION_SK", "week")
    )
    return (
        w.with_columns(_runs(["DIRECTION_SK"], "week", pl.duration(days=7)).alias("run"))
        .group_by(*KEYS, "run")
        .agg(pl.col("week").min().alias("start"), (pl.col("week").max() + pl.duration(days=6)).alias("end"), pl.len().alias("weeks"), pl.col("slots").sum())
        .drop("run").sort("DIRECTION_SK", "start")
    )


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
- A **record** is one row as published by TfNSW. A slot's `count` is the sum of its records, as the
  TfNSW dashboard shows it. Nothing has been fixed: the tools show the data as published, and your
  decisions are the only changes made to it.
- Records have a status: "good", or "warning" (always a count of 0). TfNSW flags many, not all, days
  with a zero total this way.
- VivaCity cameras publish their slots in UTC. All tools except `raw` and `channels` show them in
  Sydney time, and decisions use Sydney time.
- Some camera feeds leave out zero slots for some zones.
- `hourly_binned` marks days where each hour's count sits in one of its four slots and the other
  three are 0 (some early data is hourly).
- A counter that stops working may keep reporting zeros.
- TfNSW loads each day's counts over the following days, so the last few days of the record can be
  incomplete (no records yet, or zeros for slots whose counts have not arrived). Later downloads complete
  them: make no decisions about them.
- Speeds are reported by some counters only.

## What to do

Review the group's whole record. Record a decision for every period whose data should change, and
for anything you cannot settle. Periods you do not mention are kept as they are. Real changes
(weather, holidays, closures, new infrastructure, events) are not faults.

Assume the data is correct unless you have a good explanation of how it went wrong, and the data
bears that explanation out. For example, every count being even at twice the usual level is strong
evidence of double counting. Small spikes and dips are plausibly noise or real riding, and are not
faults just because they are unusual.

Actions, applied in this order:
- `zero_fill`: the feed left out zero counts; absent slots are 0 on every day the counter published
  anything for any of its sites or directions (so a zone's whole missing days are filled too).
- `drop_duplicates`: in slots with more records than the direction usually has that month, drop the
  extra records that exactly repeat other records in the slot.
- `subtract_other`: the direction also counted the riders of the counter's other direction at the site;
  subtract that direction's count, slot by slot.
- `missing`: the values are wrong and cannot be recovered; set them to missing. Say in the diagnosis
  why they cannot be recovered.
- `scale`: multiply the counts by `factor` (rounded half to even), e.g. 0.5 where every bike was counted twice.
- `direction_unreliable`: the split between directions is wrong but the total across them is right.
- `uncertain`: something may be wrong but the evidence does not settle it.

Every fix must follow from how the counts went wrong, and the data must bear that out: scale by 0.5
because every bike was counted twice, set missing because the counter reported nothing while bikes
passed. Never adjust counts to make a counter agree with its neighbours, its past or your
expectations: without a mechanism, the counts stand (record `uncertain` if you suspect a fault).

Recover counts wherever you can rather than setting them missing. If a fix that no action provides
would recover them, describe it in `proposals` (what it would do, where, and why), and set the period
`missing` until it exists.

Each decision has a scope: `SITE_SK`, `DIRECTION_SK` (null for every direction at the site), and a start
and end. A decision covers only the site it names: record a fault that affects several sites (such as a
whole camera) once for each of them. Start and end are dates, or slots as "YYYY-MM-DD HH:MM" (the slot's start time). Both ends are included. If a fault
is still going on at the end of the record, set `end` to null: the decision then also covers data that
arrives after your review.

## Series

Define the series for every site in the group that has more than one counter, or whose counter also
appears under another site. A series lists its parts: counter-directions (`COUNTER_SK`, `DIRECTION_SK`),
each optionally limited to dates. A part takes that counter-direction's data under any site. Decide
from the data which directions of different counters carry the same flow. Where two counters ran at
the same time, put both in one series only if they counted different bikes. Where you cannot tell
whether a later counter reads comparably to an earlier one, make them separate series. When in doubt,
keep series separate: a wrong join makes a false trend, while separate series lose nothing. Dated parts
can also split one counter-direction into several series, where its readings change level and you cannot
tell which level is right. Sites you do not define get one series per counter-direction.

You can sometimes learn things from the raw 15-minute records that summaries don't show; look at them
as well as the daily, weekly and monthly views.

Use only the `review` tools (see `help(rv)` and the function docstrings) and this brief. Do
not read other files in the repository (source code, README, reviews, other data), and do not use the web.

## Verdict file

Write JSON to `{verdict_path}`:

```json
{{
  "group": "{group}",
  "decisions": [
    {{"action": "zero_fill|drop_duplicates|subtract_other|missing|scale|direction_unreliable|uncertain", "factor": null, "SITE_SK": 0, "DIRECTION_SK": null,
      "start": "YYYY-MM-DD or YYYY-MM-DD HH:MM", "end": "YYYY-MM-DD or YYYY-MM-DD HH:MM or null (ongoing)", "confidence": "high|medium|low",
      "diagnosis": "one sentence", "evidence": "the key numbers"}}
  ],
  "series": [
    {{"SITE_SK": 0, "name": "a short name for the direction of travel", "confidence": "high|medium|low",
      "parts": [{{"COUNTER_SK": 0, "DIRECTION_SK": 0, "start": null, "end": null}}],
      "evidence": "why these parts belong together"}}
  ],
  "proposals": ["a fix no action provides: what it would do, where, and why"],
  "tools": {{"useful": ["tool: what it showed you"], "not_useful": ["tool: why not"],
            "improve": ["tool: what would make it better"], "add": ["a tool that would have helped: what it would show"]}},
  "summary": "two or three sentences on the group"
}}
```

`factor` is for `scale` only. In `tools`, say which tools helped and which did not, how any could be
improved, and what new tools would have helped; the tools are revised from this. An empty `decisions` list means the whole record stands as it is; an empty `series` list means every
counter-direction is its own series.
"""


def _md(df: pl.DataFrame) -> str:
    cols = df.columns
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join("" if v is None else str(v) for v in row) + " |" for row in df.rows()]
    return "\n".join(lines)


def write_brief(group: str) -> Path:
    """The brief for reviewing a group: its metadata and BRIEF. Verdicts go to reviews/verdicts/<group>.json."""
    sites = group_sites(group)
    m = meta(sites)
    parts = [
        f"# Review group {group}",
        "",
        f"Load the tools with `import review as rv`, running Python from {ROOT} as `uv run python - <<'EOF' ... EOF`.",
        "",
        f"The group's sites: `{sites}`",
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
