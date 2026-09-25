"""Clean the raw 15-minute cycling counts and build a queue of suspect periods for review.

The unit is a direction-slot: one direction's count for one 15-minute slot (0-95) of one date, with any
channel records summed the way the TfNSW dashboard does.

Automatic fixes, applied in this order (each only touches slots that still have a count):
  warning                records with status "warning" (always 0): missing
  duplicate_measurement  a single-record direction carrying a second record that tracks the first: keep the first
  halved                 runs where every non-zero count is even and the level is about double its surroundings
  impossible_count       a slot far beyond anything the direction records: missing
  corrupt_day            the rest of a counter-day that produced an impossible count: missing
  zero_outage            zeros where many bikes were expected, plus short bursts between two such outages: missing

Some early data is hourly: each hour's count sits in one of its four slots and the other three are 0. Those
direction-days are marked `hourly_binned` and left out of the zero-outage rule, whose "zeros" they are not.

Everything else that looks wrong goes to the review queue for a person (or an agent) to decide, including
even-only runs that are not verifiably doubled (normal level, or nothing to compare with): evenness proves
something is off but not what. Decisions recorded in review_decisions.csv are applied last.
"""

from pathlib import Path

import polars as pl

from .storage import slot_start, write_parquet

KEYS = ["SITE_SK", "COUNTER_SK", "DIRECTION_SK"]

# --- automatic fixes ---------------------------------------------------------
DUP_TOTAL_RATIO = 1.25  # a second record within this ratio of the first, and
DUP_MIN_CORR = 0.5  # this closely correlated slot by slot, is a duplicate measurement
MIN_EVEN_NONZERO = 20  # non-zero slots an even-only run needs before it counts as doubling (P <= 0.5^20)
DOUBLED_RATIO = 1.5  # an even-only run at >= this multiple of its surroundings is doubled
REFERENCE_DAYS = 60  # days either side of a run used as its reference level
IMPOSSIBLE_RATIO = 20  # a slot this many times its direction's 99.9th percentile, and
IMPOSSIBLE_MIN = 200  # at least this many bikes, is a fault
BASELINE_WINDOW = 29  # informative days in the rolling median behind the expected count
ZERO_RUN_EXPECTED = 20  # a zero run is an outage once this many bikes would normally have passed
ISLAND_SLOTS = 4  # non-zero bursts this short between two outages are part of the outage
HOURLY_MIN_NONZERO = 8  # a day whose non-zero slots (at least this many) all share one quarter-hour is hourly data

# --- review checks -----------------------------------------------------------
SPIKE_RATIO = 4.0
SPIKE_MIN_BIKES = 50
MIN_NORMAL = 10  # directions quieter than this (bikes/day) are too noisy for ratio checks
LEVEL_RATIO = 2.0  # monthly level vs the direction's own norm, after removing network-wide swings
SPLIT_SHIFT = 0.15  # change in a direction's share of the site total
FLAT_RUN_SLOTS = 8  # identical non-zero counts in a row
FLAT_MIN_VALUE = 5

FIXES = [
    "warning", "duplicate_measurement", "halved", "impossible_count", "corrupt_day", "zero_outage",
    "review_missing", "review_halved",
]
ACTIONS = {"keep", "missing", "halve", "direction_unreliable"}
QUEUE_COLUMNS = ["flag_id", "review_group", "check", "SITE_SK", "COUNTER_SK", "DIRECTION_SK", "start", "end", "days", "detail", "default_action"]


# --- slot table ----------------------------------------------------------------
def build_slots(counts_dir: Path) -> pl.DataFrame:
    """Direction-slots from the raw records: all records summed (`raw`), status-good records summed (`good`)."""
    count = pl.col("TOTAL_15MIN_COUNT")
    return (
        pl.scan_parquet(counts_dir / "*.parquet")
        .group_by(*KEYS, "date", "slot")
        .agg(
            count.sum().cast(pl.UInt16).alias("raw"),
            count.filter(pl.col("Status") == 0).sum().cast(pl.UInt16).alias("good"),
            pl.len().cast(pl.UInt8).alias("records"),
            count.sort_by("ID").first().alias("first"),
            (pl.col("Status") != 0).any().alias("warning"),
        )
        .sort(*KEYS, "date", "slot")
        .collect(engine="streaming")
    )


def load_slots(raw: Path, cache: Path) -> pl.DataFrame:
    """The slot table, rebuilt only when a raw file is newer than the cached copy."""
    counts_dir = raw / "counts"
    newest = max(p.stat().st_mtime for p in counts_dir.glob("*.parquet"))
    if cache.exists() and cache.stat().st_mtime >= newest:
        return pl.read_parquet(cache)
    slots = build_slots(counts_dir)
    cache.parent.mkdir(parents=True, exist_ok=True)
    write_parquet(slots, cache)
    return slots


# --- helpers -----------------------------------------------------------------
def workdays(raw: Path) -> pl.DataFrame:
    dates = pl.read_csv(raw / "dates.csv", infer_schema_length=0)
    return dates.select(
        pl.col("Date").str.slice(0, 10).str.to_date().alias("date"),
        (pl.col("Day type") == "Weekday (excl. PH)").alias("workday"),
    )


def with_workday(df: pl.DataFrame, wd: pl.DataFrame) -> pl.DataFrame:
    # the Date table starts in 2009; fall back to Monday-Friday before that
    return df.join(wd, on="date", how="left").with_columns(pl.col("workday").fill_null(pl.col("date").dt.weekday() <= 5))


def day_stats(slots: pl.DataFrame) -> pl.DataFrame:
    v = pl.col("count")
    return slots.group_by(*KEYS, "date", "workday").agg(
        v.sum().alias("tot"), (v > 0).sum().alias("nz"), (v % 2 == 1).sum().alias("odd"), v.is_not_null().sum().alias("valid")
    )


def runs_of(df: pl.DataFrame, by: list[str], order: str, flag: str, gap: int = 1) -> pl.DataFrame:
    """Label runs of consecutive flagged rows (consecutive = `order` advances by at most `gap`)."""
    f = df.filter(pl.col(flag)).sort(*by, order)
    step = (pl.col(order) - pl.col(order).shift(1)).over(by)
    if f.schema[order] == pl.Date:
        step = step.dt.total_days()
    return f.with_columns(((step > gap) | step.is_null()).cum_sum().over(by).alias("run"))


def run_days(runs: pl.DataFrame, label: str) -> pl.DataFrame:
    """Expand (DIRECTION_SK, start, end, label) runs to one row per day."""
    return runs.select("DIRECTION_SK", pl.date_ranges("start", "end").alias("date"), label).explode("date")


def slot_time() -> pl.Expr:
    """Slots since the epoch, so consecutive slots differ by 1 across midnight."""
    return pl.col("date").cast(pl.Int32).cast(pl.Int64) * 96 + pl.col("slot").cast(pl.Int64)


def mark(slots: pl.DataFrame, where: pl.Expr, fix: str, value: pl.Expr | None = None) -> pl.DataFrame:
    """Where `where` holds and the slot still has a count, replace the count (missing by default) and record why."""
    hit = where.fill_null(False) & pl.col("count").is_not_null()
    return slots.with_columns(
        pl.when(hit).then(value).otherwise(pl.col("count")).alias("count"),
        pl.when(hit).then(pl.lit(fix)).otherwise(pl.col("fix")).alias("fix"),
    )


def fmt(template: str, *exprs) -> pl.Expr:
    """Fill each {} in template with an expression rendered as text (null renders as "?")."""
    parts = template.split("{}")
    out = [pl.lit(parts[0])]
    for e, lit in zip(exprs, parts[1:]):
        e = pl.col(e) if isinstance(e, str) else e
        out += [e.cast(pl.Utf8).fill_null("?"), pl.lit(lit)]
    return pl.concat_str(out)


# --- automatic fixes -----------------------------------------------------------
def duplicate_runs(slots: pl.DataFrame) -> pl.DataFrame:
    """Runs of days where a single-record direction carries a second record that tracks the first slot by slot.

    Seen on the Harbour Bridge (Dec 2010 - Jun 2011): the same counts binned twice, so the sum is double.
    Channels that split the bikes between them (Kent St from Nov 2020) do not correlate and are left alone.
    """
    single = slots.group_by("DIRECTION_SK").agg(pl.col("records").mode().first().alias("modal")).filter(pl.col("modal") == 1)
    two = pl.col("records") == 2
    a = pl.col("first").cast(pl.Float64)
    b = (pl.col("good") - pl.col("first")).cast(pl.Float64)
    day = slots.join(single, on="DIRECTION_SK").group_by(*KEYS, "date").agg(
        (two.mean() >= 0.9).alias("two"), two.sum().alias("n"),
        a.filter(two).sum().alias("a"), b.filter(two).sum().alias("b"),
        (a * a).filter(two).sum().alias("aa"), (b * b).filter(two).sum().alias("bb"), (a * b).filter(two).sum().alias("ab"),
    )
    runs = runs_of(day, KEYS, "date", "two").group_by(*KEYS, "run").agg(
        pl.col("date").min().alias("start"), pl.col("date").max().alias("end"), pl.len().alias("days"),
        *[pl.col(c).sum() for c in ("n", "a", "b", "aa", "bb", "ab")],
    )
    n, sa, sb = pl.col("n"), pl.col("a"), pl.col("b")
    corr = (n * pl.col("ab") - sa * sb) / ((n * pl.col("aa") - sa * sa) * (n * pl.col("bb") - sb * sb)).sqrt()
    ratio = pl.max_horizontal("a", "b") / pl.min_horizontal("a", "b")
    return runs.filter(
        (pl.min_horizontal("a", "b") >= 20 * pl.col("days")) & (ratio <= DUP_TOTAL_RATIO) & (corr >= DUP_MIN_CORR)
    ).select(*KEYS, "start", "end", "days", pl.lit("duplicate_measurement").alias("fix"), (sa / sb).alias("level_ratio"))


def doubling_runs(day: pl.DataFrame) -> pl.DataFrame:
    """Runs of consecutive informative days where every non-zero count is even, with their level vs surroundings."""
    inf = day.filter(pl.col("nz") > 0).sort("DIRECTION_SK", "date").with_columns((pl.col("odd") == 0).alias("even"))
    inf = inf.with_columns((pl.col("even") != pl.col("even").shift(1)).fill_null(True).cum_sum().over("DIRECTION_SK").alias("run"))
    runs = (
        inf.filter("even").group_by(*KEYS, "run")
        .agg(pl.col("date").min().alias("start"), pl.col("date").max().alias("end"), pl.col("nz").sum().alias("nonzero_slots"), pl.len().alias("days"))
        .filter(pl.col("nonzero_slots") >= MIN_EVEN_NONZERO)
    )
    # reference: days with odd counts within REFERENCE_DAYS of the run, compared within the same day class
    ref = inf.filter(~pl.col("even")).select("DIRECTION_SK", "date", "workday", "tot")
    near = runs.select("DIRECTION_SK", "run", "start", "end").join(ref, on="DIRECTION_SK").filter(
        pl.col("date").is_between(pl.col("start") - pl.duration(days=REFERENCE_DAYS), pl.col("start"), closed="left")
        | pl.col("date").is_between(pl.col("end"), pl.col("end") + pl.duration(days=REFERENCE_DAYS), closed="right")
    )
    ref_level = near.group_by("DIRECTION_SK", "run", "workday").agg(pl.col("tot").median().alias("ref"))
    ratio = (
        inf.filter("even").select("DIRECTION_SK", "run", "workday", "tot")
        .join(ref_level, on=["DIRECTION_SK", "run", "workday"], how="left")
        .group_by("DIRECTION_SK", "run")
        .agg((pl.col("tot") / pl.col("ref")).median().alias("level_ratio"), pl.col("tot").median().alias("median_day"))
    )
    fix = (
        pl.when(pl.col("level_ratio").is_null()).then(pl.lit("halved_unverified"))
        .when(pl.col("level_ratio") >= DOUBLED_RATIO).then(pl.lit("halved"))
        .otherwise(pl.lit("even_normal_level"))
    )
    return runs.join(ratio, on=["DIRECTION_SK", "run"], how="left").select(*KEYS, "start", "end", "days", fix.alias("fix"), "level_ratio", "median_day")


def baselines(day: pl.DataFrame) -> pl.DataFrame:
    """Typical daily total for every direction-day (`baseline`), and for the same day class (`b_class`)."""
    rolling = lambda by: pl.col("tot").cast(pl.Float64).rolling_median(BASELINE_WINDOW, center=True, min_samples=5).over(by)
    inf = day.filter(pl.col("tot") > 0).sort("DIRECTION_SK", "date").with_columns(
        rolling("DIRECTION_SK").alias("b"), rolling(["DIRECTION_SK", "workday"]).alias("b_class")
    )
    allday = day.select("DIRECTION_SK", "date", "workday").sort("DIRECTION_SK", "date")
    b = inf.select("DIRECTION_SK", "date", "b")
    back = allday.join_asof(b, on="date", by="DIRECTION_SK", strategy="backward", check_sortedness=False)
    fwd = allday.join_asof(b.rename({"b": "b_fwd"}), on="date", by="DIRECTION_SK", strategy="forward", check_sortedness=False)
    out = back.join(fwd.select("DIRECTION_SK", "date", "b_fwd"), on=["DIRECTION_SK", "date"]).with_columns(
        pl.min_horizontal("b", "b_fwd").alias("baseline")
    )
    cls = inf.filter(pl.col("b_class").is_not_null()).select("DIRECTION_SK", "workday", "date", "b_class").sort("DIRECTION_SK", "workday", "date")
    out = out.sort("DIRECTION_SK", "workday", "date").join_asof(cls, on="date", by=["DIRECTION_SK", "workday"], strategy="nearest", check_sortedness=False)
    return out.select("DIRECTION_SK", "date", "baseline", "b_class")


def expected_counts(slots: pl.DataFrame, day: pl.DataFrame) -> pl.DataFrame:
    """Bikes normally expected in each slot: the day's baseline spread by the direction's time-of-day profile."""
    full = day.filter((pl.col("valid") == 96) & (pl.col("tot") > 0)).select("DIRECTION_SK", "date")
    prof = (
        slots.join(full, on=["DIRECTION_SK", "date"]).group_by("DIRECTION_SK", "workday", "slot").agg(pl.col("count").sum().alias("n"))
        .with_columns((pl.col("n") / pl.col("n").sum().over("DIRECTION_SK", "workday")).alias("share"))
    )
    net = prof.group_by("workday", "slot").agg(pl.col("share").median().alias("net_share"))
    net = net.with_columns(pl.col("net_share") / pl.col("net_share").sum().over("workday"))
    enough = full.join(day.select("DIRECTION_SK", "date", "workday"), on=["DIRECTION_SK", "date"]).group_by("DIRECTION_SK", "workday").len("full_days")
    prof = prof.join(enough, on=["DIRECTION_SK", "workday"]).filter(pl.col("full_days") >= 7).select("DIRECTION_SK", "workday", "slot", "share")
    return (
        slots.join(baselines(day).select("DIRECTION_SK", "date", "baseline"), on=["DIRECTION_SK", "date"], how="left")
        .join(prof, on=["DIRECTION_SK", "workday", "slot"], how="left")
        .join(net, on=["workday", "slot"], how="left")
        .with_columns((pl.col("baseline").fill_null(0) * pl.coalesce("share", "net_share")).alias("expected"))
        .drop("baseline", "share", "net_share")
        .sort(*KEYS, "date", "slot")
    )


def hourly_binned(slots: pl.DataFrame) -> pl.Series:
    """Direction-days of hourly data: every non-zero slot falls on the same quarter of the hour."""
    nz = pl.col("raw") > 0
    quarter = pl.col("slot") % 4
    by = ["DIRECTION_SK", "date"]
    return slots.select(((nz.sum().over(by) >= HOURLY_MIN_NONZERO) & (quarter.filter(nz).n_unique().over(by) == 1)).alias("hourly_binned"))["hourly_binned"]


def outage_mask(slots: pl.DataFrame) -> pl.Expr:
    """Zero runs with at least ZERO_RUN_EXPECTED expected bikes, plus short non-zero bursts between two of them."""
    t, d = pl.col("t"), pl.col("DIRECTION_SK")
    zero = (pl.col("count") == 0) & ~pl.col("hourly_binned")
    new_run = ~zero | ~zero.shift(1) | (t != t.shift(1) + 1) | (d != d.shift(1))
    s = slots.with_columns(slot_time().alias("t")).with_columns(new_run.fill_null(True).cum_sum().alias("zrun"))
    s = s.with_columns((zero & (pl.when(zero).then(pl.col("expected")).sum().over("zrun") >= ZERO_RUN_EXPECTED)).fill_null(False).alias("out"))
    out_t = pl.when("out").then(t)
    between = out_t.backward_fill().over(d) - out_t.forward_fill().over(d)
    island = pl.col("count").is_not_null() & ~pl.col("hourly_binned") & (between <= ISLAND_SLOTS + 1)
    return s.select(pl.col("out") | island.fill_null(False))["out"]


def auto_fix(slots: pl.DataFrame, wd: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Apply the automatic fixes in order. Returns the slot table with `count` and `fix`, the fixed runs,
    and the even-only runs left for review."""
    slots = with_workday(slots, wd).with_columns(pl.col("good").alias("count"), pl.lit(None, dtype=pl.Utf8).alias("fix"))
    slots = slots.with_columns(hourly_binned(slots))
    slots = mark(slots, pl.col("warning"), "warning")

    dups = duplicate_runs(slots)
    slots = slots.join(run_days(dups, "fix").rename({"fix": "dup"}), on=["DIRECTION_SK", "date"], how="left")
    slots = mark(slots, pl.col("dup").is_not_null() & (pl.col("records") == 2), "duplicate_measurement", pl.col("first")).drop("dup")

    doubled = doubling_runs(day_stats(slots))
    slots = slots.join(run_days(doubled, "fix").rename({"fix": "even"}), on=["DIRECTION_SK", "date"], how="left")
    slots = mark(slots, pl.col("even") == "halved", "halved", pl.col("count") // 2).drop("even")

    p999 = pl.col("count").filter(pl.col("count") > 0).quantile(0.999).over("DIRECTION_SK")
    slots = mark(slots, (pl.col("count") >= IMPOSSIBLE_MIN) & (pl.col("count") > IMPOSSIBLE_RATIO * p999), "impossible_count")
    corrupt = (pl.col("fix") == "impossible_count").any().over("SITE_SK", "COUNTER_SK", "date")
    slots = mark(slots, corrupt, "corrupt_day")

    slots = expected_counts(slots, day_stats(slots))
    slots = mark(slots, outage_mask(slots), "zero_outage").drop("expected")

    fixes = pl.concat([doubled.filter(pl.col("fix") == "halved").drop("median_day"), dups], how="vertical_relaxed").sort(*KEYS, "start")
    return slots, fixes, doubled.filter(pl.col("fix") != "halved")


# --- review queue ------------------------------------------------------------
def even_flags(runs: pl.DataFrame) -> pl.DataFrame:
    """Even-only runs that are not verifiably doubled: kept as downloaded until reviewed."""
    r = runs.filter(pl.col("fix") != "halved")
    return r.select(
        pl.lit("even_only").alias("check"), *KEYS, "start", "end", "days",
        fmt("every non-zero count even for {} days at {} bikes/day; level vs surroundings {}", "days", pl.col("median_day").round(0).cast(pl.Int64),
            pl.col("level_ratio").round(2).cast(pl.Utf8).fill_null("unknown (nothing to compare with)")).alias("detail"),
        pl.when(pl.col("fix") == "halved_unverified").then(pl.lit("halve")).otherwise(pl.lit("missing")).alias("default_action"),
    )


def spike_flags(day: pl.DataFrame, base: pl.DataFrame, events: pl.DataFrame) -> pl.DataFrame:
    d = day.join(base, on=["DIRECTION_SK", "date"], how="left").join(events, on=["SITE_SK", "date"], how="anti")
    d = d.with_columns((pl.col("tot") / pl.col("b_class")).alias("x")).with_columns(
        ((pl.col("x") >= SPIKE_RATIO) & (pl.col("tot") >= SPIKE_MIN_BIKES) & (pl.col("b_class") >= MIN_NORMAL)).fill_null(False).alias("spike")
    )
    g = runs_of(d, KEYS, "date", "spike").group_by(*KEYS, "run").agg(
        pl.col("date").min().alias("start"), pl.col("date").max().alias("end"), pl.len().alias("days"),
        pl.col("x").max().alias("xmax"), pl.col("tot").max().alias("max_day"), pl.col("b_class").median().alias("normal"),
    )
    return g.filter((pl.col("days") >= 2) | (pl.col("xmax") >= 2 * SPIKE_RATIO)).select(
        pl.lit("spike").alias("check"), *KEYS, "start", "end", "days",
        fmt("up to {} bikes/day, {}x the normal {}/day", "max_day", pl.col("xmax").round(1), pl.col("normal").round(0).cast(pl.Int64)).alias("detail"),
        pl.lit("missing").alias("default_action"),
    )


def month_index(month: pl.Expr) -> pl.Expr:
    return month.dt.year().cast(pl.Int32) * 12 + month.dt.month().cast(pl.Int32)


def month_end(month: pl.Expr) -> pl.Expr:
    return month.dt.offset_by("1mo") - pl.duration(days=1)


def level_flags(day: pl.DataFrame) -> pl.DataFrame:
    """Months where a direction runs far from its own norm, after dividing out swings shared by the whole network."""
    m = (
        day.filter(pl.col("valid") >= 88)
        .group_by(*KEYS, pl.col("date").dt.truncate("1mo").alias("month"))
        .agg(pl.col("tot").mean().alias("m"), pl.len().alias("n_days"))
        .filter((pl.col("n_days") >= 10) & (pl.col("m") > 0))
        .with_columns(pl.col("m").median().over("DIRECTION_SK").alias("norm"))
        .filter(pl.col("norm") >= MIN_NORMAL)
        .with_columns((pl.col("m") / pl.col("norm")).alias("r"))
        .with_columns((pl.col("r") / pl.col("r").median().over("month")).alias("z"))
        .with_columns(((pl.col("z") < 1 / LEVEL_RATIO) | (pl.col("z") > LEVEL_RATIO)).alias("off"), month_index(pl.col("month")).alias("mi"))
    )
    g = runs_of(m, KEYS, "mi", "off").group_by(*KEYS, "run").agg(
        pl.col("month").min().alias("start"), month_end(pl.col("month").max()).alias("end"), pl.len().alias("months"),
        pl.col("z").median(), pl.col("m").median().alias("level"), pl.col("norm").first(),
    )
    return g.filter((pl.col("months") >= 2) | (pl.col("z") < 1 / (2 * LEVEL_RATIO)) | (pl.col("z") > 2 * LEVEL_RATIO)).select(
        pl.lit("level").alias("check"), *KEYS, "start", "end", ((pl.col("end") - pl.col("start")).dt.total_days() + 1).alias("days"),
        fmt("{} months at {}/day vs its usual {}/day ({}x after allowing for network-wide changes)",
            "months", pl.col("level").round(0).cast(pl.Int64), pl.col("norm").round(0).cast(pl.Int64), pl.col("z").round(2)).alias("detail"),
        pl.lit("keep").alias("default_action"),
    )


def direction_flags(slots: pl.DataFrame, cameras: pl.Series) -> pl.DataFrame:
    """Two-direction counters whose split, or morning/evening pattern ("peak flip"), departs from their norm."""
    s = slots.filter(~pl.col("COUNTER_SK").is_in(cameras.implode()) & pl.col("count").is_not_null() & pl.col("workday"))
    pairs = s.group_by("SITE_SK", "COUNTER_SK").agg(pl.col("DIRECTION_SK").unique().sort().alias("dirs")).filter(pl.col("dirs").list.len() == 2)
    s = s.join(pairs.select("SITE_SK", "COUNTER_SK", pl.col("dirs").list.get(0).alias("A")), on=["SITE_SK", "COUNTER_SK"])
    h, c, is_a = pl.col("slot") // 4, pl.col("count"), pl.col("DIRECTION_SK") == pl.col("A")
    am, pm = h.is_between(7, 9), h.is_between(16, 18)
    agg = (
        s.group_by("SITE_SK", "COUNTER_SK", pl.col("date").dt.truncate("1mo").alias("month"))
        .agg(
            c.filter(is_a).sum().alias("a"), c.sum().alias("tot"),
            c.filter(is_a & am).sum().alias("a_am"), c.filter(am).sum().alias("am"),
            c.filter(is_a & pm).sum().alias("a_pm"), c.filter(pm).sum().alias("pm"),
            pl.col("date").n_unique().alias("n_days"),
        )
        .filter((pl.col("n_days") >= 10) & (pl.col("tot") >= 30 * pl.col("n_days")))
        .with_columns((pl.col("a") / pl.col("tot")).alias("share"), (pl.col("a_am") / pl.col("am") - pl.col("a_pm") / pl.col("pm")).alias("flip"))
        .with_columns(
            pl.col("share").median().over("SITE_SK", "COUNTER_SK").alias("share_norm"),
            pl.col("flip").median().over("SITE_SK", "COUNTER_SK").alias("flip_norm"),
        )
        .with_columns(
            (((pl.col("share") - pl.col("share_norm")).abs() >= SPLIT_SHIFT)
             | ((pl.col("flip_norm").abs() >= 0.3) & ((pl.col("flip") - pl.col("flip_norm")).abs() >= 0.4))).fill_null(False).alias("off"),
            month_index(pl.col("month")).alias("mi"),
        )
    )
    g = runs_of(agg, ["SITE_SK", "COUNTER_SK"], "mi", "off").group_by("SITE_SK", "COUNTER_SK", "run").agg(
        pl.col("month").min().alias("start"), month_end(pl.col("month").max()).alias("end"), pl.len().alias("months"),
        pl.col("share").median(), pl.col("share_norm").first(), pl.col("flip").median(), pl.col("flip_norm").first(),
    )
    return g.select(
        pl.lit("direction").alias("check"), "SITE_SK", "COUNTER_SK", pl.lit(None, dtype=pl.Int16).alias("DIRECTION_SK"), "start", "end",
        ((pl.col("end") - pl.col("start")).dt.total_days() + 1).alias("days"),
        fmt("{} months: first direction carries {} of weekday bikes (usually {}); morning-minus-evening share {} (usually {})",
            "months", pl.col("share").round(2), pl.col("share_norm").round(2), pl.col("flip").round(2), pl.col("flip_norm").round(2)).alias("detail"),
        pl.lit("direction_unreliable").alias("default_action"),
    )


def flat_flags(slots: pl.DataFrame) -> pl.DataFrame:
    """Days with the same non-zero count repeated in FLAT_RUN_SLOTS or more consecutive slots."""
    t = slot_time()
    same = (pl.col("count") == pl.col("count").shift(1)) & (t == t.shift(1) + 1) & (pl.col("DIRECTION_SK") == pl.col("DIRECTION_SK").shift(1))
    s = slots.select(*KEYS, "date", "slot", "count").with_columns((~same.fill_null(False)).cum_sum().alias("frun"))
    runs = s.filter(pl.col("count") >= FLAT_MIN_VALUE).group_by(*KEYS, "frun").agg(
        pl.len().alias("n"), pl.col("date").min().alias("date"), pl.col("count").first().alias("value")
    )
    days = runs.filter(pl.col("n") >= FLAT_RUN_SLOTS).group_by(*KEYS, "date").agg(pl.col("n").max(), pl.col("value").first()).with_columns(pl.lit(True).alias("flat"))
    g = runs_of(days, KEYS, "date", "flat", gap=3).group_by(*KEYS, "run").agg(
        pl.col("date").min().alias("start"), pl.col("date").max().alias("end"), pl.len().alias("flat_days"), pl.col("n").max(), pl.col("value").first()
    )
    return g.select(
        pl.lit("flat").alias("check"), *KEYS, "start", "end", ((pl.col("end") - pl.col("start")).dt.total_days() + 1).alias("days"),
        fmt("{} day(s) with the same count ({}) repeated for up to {} consecutive 15-minute slots", "flat_days", "value", "n").alias("detail"),
        pl.lit("missing").alias("default_action"),
    )


def bad_value_flags(slots: pl.DataFrame) -> pl.DataFrame:
    """Days where the impossible-count rule fired, listed for manual inspection."""
    bad = slots.filter(pl.col("fix") == "impossible_count").group_by(*KEYS, "date").agg(
        pl.col("raw").sort(descending=True).head(5).cast(pl.Utf8).str.join(", ").alias("values"), pl.len().alias("n")
    )
    return bad.select(
        pl.lit("bad_values").alias("check"), *KEYS, pl.col("date").alias("start"), pl.col("date").alias("end"), pl.lit(1).alias("days"),
        fmt("{} slot(s) with impossible counts, largest {}; the counter-day is set to missing automatically", "n", "values").alias("detail"),
        pl.lit("missing").alias("default_action"),
    )


def load_events(events_csv: Path) -> pl.DataFrame:
    if not events_csv.exists():
        return pl.DataFrame(schema={"date": pl.Date, "SITE_SK": pl.Int16})
    ev = pl.read_csv(events_csv, infer_schema_length=0)
    return ev.select(
        pl.date_ranges(pl.col("date").str.to_date(), pl.col("end_date").str.to_date()).alias("date"),
        pl.col("sites").str.split(";").alias("SITE_SK"),
    ).explode("date").explode("SITE_SK").with_columns(pl.col("SITE_SK").cast(pl.Int16))


def review_groups(slots: pl.DataFrame) -> pl.DataFrame:
    """Sites linked by a shared counter, or counters by a shared site, are reviewed together.

    Returns SITE_SK -> review_group, named after the group's lowest SITE_SK (e.g. G0101).
    """
    pairs = slots.select("SITE_SK", "COUNTER_SK").unique().rows()
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
    )


def review_queue(slots: pl.DataFrame, even_runs: pl.DataFrame, raw: Path, events_csv: Path) -> pl.DataFrame:
    day = day_stats(slots)
    cameras = pl.read_csv(raw / "counters.csv", infer_schema_length=0).filter(pl.col("Technology") == "CAMERA")["COUNTER_SK"].cast(pl.Int16)
    parts = [
        even_flags(even_runs),
        spike_flags(day, baselines(day), load_events(events_csv)),
        level_flags(day),
        direction_flags(slots, cameras),
        flat_flags(slots),
        bad_value_flags(slots),
    ]
    q = pl.concat(
        [p.with_columns(*[pl.col(k).cast(pl.Int16) for k in KEYS], pl.col("days").cast(pl.Int32)) for p in parts], how="vertical_relaxed"
    )
    target = pl.col("DIRECTION_SK").cast(pl.Utf8).fill_null(fmt("c{}", "COUNTER_SK"))
    q = q.with_columns(fmt("{}:{}:{}:{}", "check", "SITE_SK", target, "start").alias("flag_id")).join(review_groups(slots), on="SITE_SK", how="left")
    return q.select(QUEUE_COLUMNS).sort("review_group", "SITE_SK", "start", "check")


# --- decisions and outputs ---------------------------------------------------
def apply_review(slots: pl.DataFrame, queue: pl.DataFrame, decisions_csv: Path) -> pl.DataFrame:
    """Mark each slot with the checks that flagged it, and apply any recorded decisions."""
    q = queue.with_columns(pl.date_ranges("start", "end").alias("date")).explode("date")
    keys = slots.select(*KEYS).unique()
    direct = q.filter(pl.col("DIRECTION_SK").is_not_null()).select("flag_id", "check", "DIRECTION_SK", "date")
    # counter-level flags cover every direction of that counter at the site
    counter = q.filter(pl.col("DIRECTION_SK").is_null()).drop("DIRECTION_SK").join(keys, on=["SITE_SK", "COUNTER_SK"]).select("flag_id", "check", "DIRECTION_SK", "date")
    days = pl.concat([direct, counter])
    if decisions_csv.exists():
        dec = pl.read_csv(decisions_csv, infer_schema_length=0).select("flag_id", "action")
        bad = dec.filter(~pl.col("action").is_in(sorted(ACTIONS)))
        if bad.height:
            raise SystemExit(f"unknown actions in {decisions_csv}: {bad.rows()}")
        days = days.join(dec, on="flag_id", how="left")
    else:
        days = days.with_columns(pl.lit(None, dtype=pl.Utf8).alias("action"))
    per_day = days.group_by("DIRECTION_SK", "date").agg(
        pl.col("check").unique().sort().str.join(",").alias("flags"), pl.col("action").drop_nulls().unique().alias("actions")
    )
    slots = slots.join(per_day, on=["DIRECTION_SK", "date"], how="left")
    act = pl.col("actions")
    slots = mark(slots, act.list.contains("missing"), "review_missing")
    slots = mark(slots, act.list.contains("halve"), "review_halved", pl.col("count") // 2)
    return slots.with_columns(act.list.contains("direction_unreliable").fill_null(False).alias("direction_unreliable")).drop("actions")


def run(raw: Path, out: Path, cache: Path, events_csv: Path, decisions_csv: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    slots = load_slots(raw, cache)
    print(f"{slots.height:,} direction-slots from {slots['records'].cast(pl.Int64).sum():,} raw records")
    fixed, fixes, even_runs = auto_fix(slots, workdays(raw))
    fixes.write_csv(out / "fixes.csv")
    for fix, n in fixed.group_by("fix").len().sort("len", descending=True).iter_rows():
        print(f"  {fix or 'unchanged'}: {n:,} slots")
    queue = review_queue(fixed, even_runs, raw, events_csv)
    queue.write_csv(out / "review_queue.csv")
    print(f"review queue: {queue.height} flags at {queue['SITE_SK'].n_unique()} sites -> {out / 'review_queue.csv'}")
    for check, n in queue.group_by("check").len().sort("len", descending=True).iter_rows():
        print(f"  {check}: {n}")
    final = apply_review(fixed, queue, decisions_csv).select(
        *KEYS, "date", slot_start(pl.col("date"), pl.col("slot")).alias("time"), "workday", "records",
        pl.col("raw").cast(pl.UInt16), pl.col("count").cast(pl.UInt16),
        pl.col("fix").cast(pl.Enum(FIXES)), pl.col("flags").cast(pl.Categorical), "direction_unreliable", "hourly_binned",
    )
    write_parquet(final.sort(*KEYS, "time"), out / "counts_15min.parquet")
    print(f"cleaned counts -> {out / 'counts_15min.parquet'}")
