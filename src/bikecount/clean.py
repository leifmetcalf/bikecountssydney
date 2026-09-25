"""Clean the raw 15-minute cycling counts: automatic fixes, then reviewers' decisions.

The unit is a direction-slot: one direction's count for one 15-minute slot (0-95) of one date, with any
channel records summed the way the TfNSW dashboard does.

Automatic fixes, applied in this order (each only touches slots that still have a count):
  warning                records with status "warning" (always 0): missing
  duplicate_load         extra records that exactly repeat the slot's other records (the same data loaded twice): dropped
  duplicate_measurement  a single-record direction carrying a second record that tracks the first: keep the first
  halved                 runs where every non-zero count is even and the level is about double its surroundings
  impossible_count       a slot far beyond anything the direction records: missing
  corrupt_day            the rest of a counter-day that produced an impossible count: missing
  zero_outage            zeros where many bikes were expected, lasting most of a day or while the counter's other
                         directions kept counting, plus short bursts between two such outages: missing

Some early data is hourly: each hour's count sits in one of its four slots and the other three are 0. Those
direction-days are marked `hourly_binned` and left out of the zero-outage rule, whose "zeros" they are not.

Everything else is left to review: every review group is reviewed in full (see review.py), and the
decisions recorded in reviews/decisions.csv are applied last. Weekly totals are built per series, one continuous
line per direction of travel at a site, as reviewers defined them in reviews/series.csv.
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
ZERO_RUN_EXPECTED = 20  # a zero run is an outage once this many bikes would normally have passed, and either
WHOLE_DAY_SHARE = 0.8  # it held this share of a normal day's traffic and
OUTAGE_MAX_SHARE = 0.1  # recorded under this share of it, or
ONE_SIDED_SHARE = 0.5  # the counter's other directions carried this share of their normal traffic meanwhile
DUP_LOAD_MIN_PAIRED = 20  # non-zero repeated slots a direction-day needs before its extra records count as a duplicate load
ISLAND_SLOTS = 4  # non-zero bursts this short between zeros are part of an outage
OUTAGE_CHUNKS = 8  # the outage rule runs on this many groups of counters in turn
HOURLY_MIN_NONZERO = 8  # a day whose non-zero slots (at least this many) all share one quarter-hour is hourly data

AUTO_FIXES = ["warning", "duplicate_load", "duplicate_measurement", "halved", "impossible_count", "corrupt_day", "zero_outage"]
FIXES = AUTO_FIXES + ["review_missing", "review_halved", "review_restored"]
ACTIONS = {"keep", "missing", "halve", "direction_unreliable", "restore", "uncertain"}
COMPLETE_SLOTS = 90  # a day counts as complete with this many of its 96 slots valid


# --- slot table ----------------------------------------------------------------
def build_slots(counts_dir: Path) -> pl.DataFrame:
    """Direction-slots from the raw records: all records summed (`raw`), as the dashboard shows.

    A slot's records can come from two loads: recent data often gets a second record in the next day's load, and
    one of the two is 0. `records` and `first` describe the load with the most bikes (the earlier one on a tie),
    its date is `load`, and IDs are only compared within it: TfNSW numbers the rows of each load from 1.
    """
    count = pl.col("TOTAL_15MIN_COUNT")
    per_load = (
        pl.scan_parquet(counts_dir / "*.parquet")
        .group_by(*KEYS, "date", "slot", pl.col("ADDED_UPDATED_DATETIME_SYDNEY").alias("load"))
        .agg(
            count.sum().alias("n"),
            pl.len().alias("records"),
            count.sort_by("ID").first().alias("first"),
            (pl.col("Status") != 0).any().alias("warning"),
        )
    )
    main = pl.col("records", "first", "load").sort_by("n", "load", descending=[True, False]).first()
    return (
        per_load.group_by(*KEYS, "date", "slot")
        .agg(pl.col("n").sum().cast(pl.UInt16).alias("raw"), main, pl.col("warning").any())
        .with_columns(pl.col("records").cast(pl.UInt8))
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


# --- automatic fixes -----------------------------------------------------------
def duplicate_loads(slots: pl.DataFrame, counts_dir: Path) -> pl.DataFrame:
    """Direction-slots whose extra records exactly repeat other records in the slot, with the count of one copy (`dedup`).

    A slot with more records than its direction usually has that month (the month's most common daily mode) is a
    duplicate load when its extra records can all be matched to identical records. A run of consecutive days with extra
    records qualifies when every such slot matches, and at least DUP_LOAD_MIN_PAIRED of them repeat a non-zero count.
    Where the choice is ambiguous the largest repeats are dropped.
    """
    month = pl.col("date").dt.truncate("1mo").alias("month")
    daily_mode = slots.group_by("DIRECTION_SK", "date").agg(pl.col("records").mode().min().alias("m"))
    usual = daily_mode.group_by("DIRECTION_SK", month).agg(pl.col("m").mode().min().alias("usual"))
    extra = (
        slots.select("DIRECTION_SK", "date", "slot", "load", "records", month).join(usual, on=["DIRECTION_SK", "month"])
        .filter(pl.col("records") > pl.col("usual")).select("DIRECTION_SK", "date", "slot", "load", "usual")
    )
    values = (
        pl.scan_parquet(counts_dir / "*.parquet")
        .select("DIRECTION_SK", "date", "slot", pl.col("ADDED_UPDATED_DATETIME_SYDNEY").alias("load"), "TOTAL_15MIN_COUNT")
        .join(extra.lazy(), on=["DIRECTION_SK", "date", "slot", "load"])
        .group_by("DIRECTION_SK", "date", "slot", "usual", "TOTAL_15MIN_COUNT").agg(pl.len().alias("k"))
        .collect(engine="streaming")
    )
    v = pl.col("TOTAL_15MIN_COUNT").cast(pl.Int64)
    per_slot = values.group_by("DIRECTION_SK", "date", "slot").agg(
        (pl.col("k").sum() - pl.col("usual").first()).alias("excess"),
        (v * pl.col("k")).sum().alias("total"),
        v.repeat_by(pl.col("k") // 2).flatten().sort(descending=True).alias("repeats"),  # values that occur in pairs, once per pair
    )
    dropped = pl.col("repeats").list.head(pl.col("excess")).list.sum()
    per_slot = per_slot.with_columns((pl.col("repeats").list.len() >= pl.col("excess")).alias("matched"), dropped.alias("dropped"))
    days = per_slot.group_by("DIRECTION_SK", "date").agg(
        pl.col("matched").all(), (pl.col("dropped") > 0).sum().alias("paired"), pl.lit(True).alias("extra"),
    )
    runs = runs_of(days, ["DIRECTION_SK"], "date", "extra")
    runs = runs.with_columns(
        (pl.col("matched").all() & (pl.col("paired").sum() >= DUP_LOAD_MIN_PAIRED)).over("DIRECTION_SK", "run").alias("ok")
    ).filter("ok").select("DIRECTION_SK", "date")
    return per_slot.join(runs, on=["DIRECTION_SK", "date"]).select("DIRECTION_SK", "date", "slot", (pl.col("total") - pl.col("dropped")).alias("dedup"))


def duplicate_runs(slots: pl.DataFrame) -> pl.DataFrame:
    """Runs of days where a single-record direction carries a second record that tracks the first slot by slot.

    Seen on the Harbour Bridge (Dec 2010 - Jun 2011): the same counts binned twice, so the sum is double.
    Channels that split the bikes between them (Kent St from Nov 2020) do not correlate and are left alone.
    """
    single = slots.group_by("DIRECTION_SK").agg(pl.col("records").mode().first().alias("modal")).filter(pl.col("modal") == 1)
    two = pl.col("records") == 2
    a = pl.col("first").cast(pl.Float64)
    b = (pl.col("raw") - pl.col("first")).cast(pl.Float64)
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
    """Typical daily total for every direction-day (`baseline`): the lower of the nearest rolling medians either side."""
    inf = day.filter(pl.col("tot") > 0).sort("DIRECTION_SK", "date").with_columns(
        pl.col("tot").cast(pl.Float64).rolling_median(BASELINE_WINDOW, center=True, min_samples=5).over("DIRECTION_SK").alias("b")
    )
    allday = day.select("DIRECTION_SK", "date").sort("DIRECTION_SK", "date")
    b = inf.select("DIRECTION_SK", "date", "b")
    back = allday.join_asof(b, on="date", by="DIRECTION_SK", strategy="backward", check_sortedness=False)
    fwd = allday.join_asof(b.rename({"b": "b_fwd"}), on="date", by="DIRECTION_SK", strategy="forward", check_sortedness=False)
    return back.join(fwd, on=["DIRECTION_SK", "date"]).select("DIRECTION_SK", "date", pl.min_horizontal("b", "b_fwd").alias("baseline"))


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
        slots.join(baselines(day), on=["DIRECTION_SK", "date"], how="left")
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


def outage_mask(slots: pl.DataFrame) -> pl.Series:
    """Slots where a counter stopped counting (see `outages`), computed a few counters at a time to bound memory."""
    cols = slots.select("SITE_SK", "COUNTER_SK", "DIRECTION_SK", "date", "slot", "count", "expected", "hourly_binned").with_row_index("i")
    chunk = (pl.col("COUNTER_SK").cast(pl.Int32).abs() % OUTAGE_CHUNKS).alias("chunk")
    parts = [outages(part) for part in cols.with_columns(chunk).partition_by("chunk", include_key=False)]
    return pl.concat(parts).sort("i")["out"]


def outages(s: pl.DataFrame) -> pl.DataFrame:
    """Row index `i` and `out` for slots where a counter stopped counting: two kinds of outage.

    - A stretch of zeros, and of short bursts (ISLAND_SLOTS or fewer) between zeros, that held most of a normal day's
      traffic (WHOLE_DAY_SHARE) of which it recorded under OUTAGE_MAX_SHARE.
    - A run of zeros while the counter's other directions kept counting (ONE_SIDED_SHARE of their normal traffic).
    Either needs zeros where ZERO_RUN_EXPECTED bikes would normally have passed. Shorter lulls in every direction at
    once stay zeros: rain or a closure empties a path too.
    """
    t, d = pl.col("t"), pl.col("DIRECTION_SK")
    live = ~pl.col("hourly_binned") & pl.col("count").is_not_null()
    zero, nonzero = live & (pl.col("count") == 0), live & (pl.col("count") > 0)
    runs = lambda flag: (~flag | ~flag.shift(1) | (t != t.shift(1) + 1) | (d != d.shift(1))).fill_null(True).cum_sum()
    s = s.with_columns(slot_time().alias("t")).with_columns(zero.alias("zero"), runs(zero).alias("zrun"), runs(nonzero).alias("burst"))
    quiet = pl.col("zero") | (nonzero & (nonzero.sum().over("burst") <= ISLAND_SLOTS))
    s = s.with_columns(quiet.alias("quiet")).with_columns(runs(pl.col("quiet")).alias("stretch"))
    valid_exp = pl.when(pl.col("count").is_not_null()).then(pl.col("expected")).otherwise(0)
    s = s.with_columns(
        # the counter's other directions in the same slot
        (pl.col("count").cast(pl.Int64).sum().over("SITE_SK", "COUNTER_SK", "t") - pl.col("count").cast(pl.Int64).fill_null(0)).alias("other_n"),
        (valid_exp.sum().over("SITE_SK", "COUNTER_SK", "t") - valid_exp).alias("other_exp"),
        pl.col("expected").sum().over("DIRECTION_SK", "date").alias("day_exp"),
    )
    on_zeros = lambda c, by: pl.when("zero").then(pl.col(c)).sum().over(by)
    s = s.with_columns(
        on_zeros("expected", "zrun").alias("run_exp"), on_zeros("other_n", "zrun").alias("run_other_n"), on_zeros("other_exp", "zrun").alias("run_other_exp"),
        on_zeros("expected", "stretch").alias("stretch_zero_exp"),
        pl.col("expected").sum().over("stretch").alias("stretch_exp"), pl.col("count").cast(pl.Int64).sum().over("stretch").alias("stretch_n"),
        pl.col("day_exp").max().over("stretch").alias("stretch_day_exp"),
        # bursts count only between two zeros of the stretch
        pl.col("zero").cum_sum().over("stretch").alias("zeros_before"), pl.col("zero").cum_sum(reverse=True).over("stretch").alias("zeros_after"),
    )
    stopped = (
        (pl.col("stretch_zero_exp") >= ZERO_RUN_EXPECTED) & (pl.col("stretch_exp") >= WHOLE_DAY_SHARE * pl.col("stretch_day_exp"))
        & (pl.col("stretch_n") <= OUTAGE_MAX_SHARE * pl.col("stretch_exp"))
        & (pl.col("zero") | ((pl.col("zeros_before") > 0) & (pl.col("zeros_after") > 0)))
    )
    one_sided = (
        pl.col("zero") & (pl.col("run_exp") >= ZERO_RUN_EXPECTED)
        & (pl.col("run_other_exp") >= ZERO_RUN_EXPECTED) & (pl.col("run_other_n") >= ONE_SIDED_SHARE * pl.col("run_other_exp"))
    )
    return s.select("i", (stopped | one_sided).fill_null(False).alias("out"))


def auto_fix(slots: pl.DataFrame, wd: pl.DataFrame, counts_dir: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Apply the automatic fixes in order. Returns the slot table with `count` and `fix`, and the fixed runs."""
    slots = with_workday(slots, wd).with_columns(pl.col("raw").alias("count"), pl.lit(None, dtype=pl.Utf8).alias("fix"))
    slots = slots.with_columns(hourly_binned(slots))
    slots = mark(slots, pl.col("warning"), "warning")

    slots = slots.join(duplicate_loads(slots, counts_dir), on=["DIRECTION_SK", "date", "slot"], how="left")
    slots = mark(slots, pl.col("dedup").is_not_null(), "duplicate_load", pl.col("dedup").cast(pl.UInt16)).drop("dedup")
    load_days = slots.filter(pl.col("fix") == "duplicate_load").select(*KEYS, "date").unique().with_columns(pl.lit(True).alias("hit"))
    loads = runs_of(load_days, KEYS, "date", "hit").group_by(*KEYS, "run").agg(
        pl.col("date").min().alias("start"), pl.col("date").max().alias("end"), pl.len().alias("days")
    ).select(*KEYS, "start", "end", "days", pl.lit("duplicate_load").alias("fix"))

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

    fixes = pl.concat([loads, doubled.filter(pl.col("fix") == "halved").drop("median_day"), dups], how="diagonal_relaxed").sort(*KEYS, "start")
    return slots, fixes


# --- review groups and decisions --------------------------------------------
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


def apply_decisions(slots: pl.DataFrame, decisions_csv: Path) -> pl.DataFrame:
    """Apply reviewers' decisions (all except those with status "rejected").

    A decision covers SITE_SK, DIRECTION_SK (blank: every direction at the site) and start..end. `restore` undoes the
    automatic fixes (count = raw) and is applied before `missing` and `halve`.
    """
    if not decisions_csv.exists():
        return slots.with_columns(pl.lit(False).alias("direction_unreliable"))
    dec = pl.read_csv(decisions_csv, infer_schema_length=0).filter(pl.col("status") != "rejected")
    bad = dec.filter(~pl.col("action").is_in(sorted(ACTIONS)))
    if bad.height:
        raise SystemExit(f"unknown actions in {decisions_csv}: {bad.select('action').unique().rows()}")
    days = (
        dec.filter(pl.col("action").is_in(["restore", "missing", "halve", "direction_unreliable"]))
        .select(
            pl.col("SITE_SK").cast(pl.Int16), pl.col("DIRECTION_SK").cast(pl.Int16), "action",
            pl.date_ranges(pl.col("start").str.to_date(), pl.col("end").str.to_date()).alias("date"),
        )
        .explode("date")
    )
    keys = slots.select("SITE_SK", "DIRECTION_SK").unique()
    # a blank DIRECTION_SK covers every direction at the site
    days = pl.concat([
        days.filter(pl.col("DIRECTION_SK").is_not_null()),
        days.filter(pl.col("DIRECTION_SK").is_null()).drop("DIRECTION_SK").join(keys, on="SITE_SK").select(days.columns),
    ])
    per_day = days.group_by("DIRECTION_SK", "date").agg(pl.col("action").unique().alias("actions"))
    slots = slots.join(per_day, on=["DIRECTION_SK", "date"], how="left")
    act = pl.col("actions")
    restore = act.list.contains("restore").fill_null(False) & pl.col("fix").is_in(AUTO_FIXES)
    slots = slots.with_columns(
        pl.when(restore).then(pl.col("raw")).otherwise(pl.col("count")).alias("count"),
        pl.when(restore).then(pl.lit("review_restored")).otherwise(pl.col("fix")).alias("fix"),
    )
    slots = mark(slots, act.list.contains("missing"), "review_missing")
    slots = mark(slots, act.list.contains("halve"), "review_halved", pl.col("count") // 2)
    return slots.with_columns(act.list.contains("direction_unreliable").fill_null(False).alias("direction_unreliable")).drop("actions")


# --- series and weekly totals -------------------------------------------------
def series_parts(slots: pl.DataFrame, series_csv: Path, raw: Path) -> pl.DataFrame:
    """The counter-directions making up each series: SITE_SK, series, COUNTER_SK, DIRECTION_SK, start, end, match_site.

    Reviewed series (all except those with status "rejected") take a counter-direction's data under any site. Every
    counter-direction they leave out becomes a series of its own at its site (`match_site`), named after its direction,
    and after its counter too where the site has several counters.
    """
    schema = {"SITE_SK": pl.Int16, "series": pl.Utf8, "COUNTER_SK": pl.Int16, "DIRECTION_SK": pl.Int16, "start": pl.Date, "end": pl.Date}
    reviewed = pl.DataFrame(schema=schema)
    if series_csv.exists():
        reviewed = pl.read_csv(series_csv, infer_schema_length=0).filter(pl.col("status") != "rejected").select(
            pl.col("SITE_SK").cast(pl.Int16), "series", pl.col("COUNTER_SK").cast(pl.Int16), pl.col("DIRECTION_SK").cast(pl.Int16),
            pl.col("start").str.to_date(), pl.col("end").str.to_date(),
        )
    pairs = slots.select(*KEYS).unique().with_columns((pl.col("COUNTER_SK").n_unique().over("SITE_SK") > 1).alias("several"))
    rest = pairs.join(reviewed.select("COUNTER_SK", "DIRECTION_SK").unique(), on=["COUNTER_SK", "DIRECTION_SK"], how="anti")
    dims = lambda name, key, *cols: pl.read_csv(raw / name, infer_schema_length=0).select(pl.col(key).cast(pl.Int16), *cols)
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
    reviewed = reviewed.with_columns(pl.lit(None, pl.Int16).alias("match_site"))
    return pl.concat([reviewed, defaults]).sort("SITE_SK", "series", "COUNTER_SK", "DIRECTION_SK")


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


def run(raw: Path, out: Path, cache: Path, decisions_csv: Path, series_csv: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    slots = load_slots(raw, cache)
    print(f"{slots.height:,} direction-slots")
    fixed, fixes = auto_fix(slots, workdays(raw), raw / "counts")
    fixes.write_csv(out / "fixes.csv")
    review_groups(fixed).sort("review_group", "SITE_SK").write_csv(out / "review_groups.csv")
    final = apply_decisions(fixed, decisions_csv)
    for fix, n in final.group_by("fix").len().sort("len", descending=True).iter_rows():
        print(f"  {fix or 'unchanged'}: {n:,} slots")
    final = final.select(
        *KEYS, "date", slot_start(pl.col("date"), pl.col("slot")).alias("time"), "workday", "records",
        pl.col("raw").cast(pl.UInt16), pl.col("count").cast(pl.UInt16),
        pl.col("fix").cast(pl.Enum(FIXES)), "direction_unreliable", "hourly_binned",
    )
    write_parquet(final.sort(*KEYS, "time"), out / "counts_15min.parquet")
    print(f"cleaned counts -> {out / 'counts_15min.parquet'}")
    parts = series_parts(final, series_csv, raw)
    parts.write_csv(out / "series.csv")
    week = weekly(final, parts)
    write_parquet(week, out / "weekly.parquet")
    print(f"{week.height:,} series-weeks in {parts.select('SITE_SK', 'series').n_unique():,} series -> {out / 'weekly.parquet'}")
