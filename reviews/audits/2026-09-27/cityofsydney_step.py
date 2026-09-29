"""Reproduce the City of Sydney replacement-step tables (run from the repo root):

    systemd-run --user --scope -p MemoryMax=2G -p MemorySwapMax=0 --quiet uv run python \
        reviews/audits/2026-09-27/cityofsydney_step.py

Level = median of workday daily totals (both directions, days with >= 90 slots and > 0 bikes) per site, counter
and month; medians ignore the scattered duplicate-load and zero days. Step = new/old in matched calendar months,
divided by the same change at controls (geometric mean).
"""
import datetime as dt
import glob
import math
import statistics as st

import polars as pl

D = dt.date
TFNSW = {101: 156, 158: 155, 160: 102, 161: 163, 168: 251, 174: 210, 175: 211, 154: 109}  # continuous, never replaced
SITES = [541, 542, 543, 544, 545, 548, 550, 551, 552, 554, 559, 561, 537, 538, *TFNSW]

files = [f for s in SITES for f in sorted(glob.glob(f"data/raw/counts/site_{s:04d}_*.parquet")) if int(f[-12:-8]) >= 2023]
day = (pl.scan_parquet(files).group_by("SITE_SK", "COUNTER_SK", "DIRECTION_SK", "date")
       .agg(pl.col("TOTAL_15MIN_COUNT").cast(pl.Int64).sum().alias("bikes"), pl.col("slot").n_unique().alias("slots"))
       .collect(engine="streaming"))
dates = pl.read_csv("data/raw/dates.csv", infer_schema_length=0).select(
    pl.col("Date").str.slice(0, 10).str.to_date().alias("date"), (pl.col("Day type") == "Weekday (excl. PH)").alias("workday"))
site_day = (day.filter(pl.col("slots") >= 90).group_by("SITE_SK", "COUNTER_SK", "date").agg(pl.col("bikes").sum())
            .join(dates, on="date").filter(pl.col("workday"), pl.col("bikes") > 0))
m = (site_day.group_by("SITE_SK", "COUNTER_SK", pl.col("date").dt.truncate("1mo").alias("mo"))
     .agg(pl.col("bikes").median().alias("v"), pl.len().alias("n")).filter(pl.col("n") >= 8))
val = {(s, c, mo): v for s, c, mo, v in m.select("SITE_SK", "COUNTER_SK", "mo", "v").iter_rows()}


def addm(d, k):
    y, mo = d.year + (d.month - 1 + k) // 12, (d.month - 1 + k) % 12 + 1
    return D(y, mo, 1)


def local(site, mo):
    """CoS Metrocount sites that changed unit but not vendor, joined at their verified handovers (overlap +4-11%)."""
    if mo < D(2024, 6, 1):
        return None  # doubled until 2024-05-19
    c = {543: 330 if mo < D(2025, 10, 1) else 356, 548: 329 if mo < D(2025, 11, 1) else 361,
         559: 332 if mo < D(2025, 12, 1) else (368 if mo < D(2026, 2, 1) else 387)}[site]
    return val.get((site, c, mo))


ym = lambda y, *ms: [D(y, x, 1) for x in ms]
CASES = {  # site: old counter, new counter, new-counter months compared with the same months `lag` earlier
    541: (234, 354, ym(2025, 9, 10), 12),
    542: (231, 355, ym(2025, 10, 11, 12) + ym(2026, 1, 2, 3, 4), 12),
    545: (227, 358, ym(2025, 10, 11, 12) + ym(2026, 1, 2, 3, 4), 12),
    550: (226, 362, ym(2025, 11, 12) + ym(2026, 1, 2, 3, 4), 12),
    551: (233, 367, ym(2025, 11, 12) + ym(2026, 1, 2, 3, 4, 5), 12),
    552: (241, 360, ym(2025, 11, 12) + ym(2026, 1, 2, 3, 4, 5, 6, 7), 12),
    554: (225, 363, ym(2025, 11, 12) + ym(2026, 1, 2, 3, 4), 12),
    561: (240, 371, ym(2025, 11, 12) + ym(2026, 1, 2, 3), 12),
    544: (228, 357, ym(2025, 10, 11) + ym(2026, 1, 2, 3, 4, 5, 6, 7, 8), 24),
    537: (333, 351, ym(2025, 9, 10, 11, 12) + ym(2026, 1, 2, 3, 4, 5), 12),
    538: (331, 353, ym(2025, 9, 10, 11, 12) + ym(2026, 1, 2, 3, 4), 12),
    543: (330, 356, ym(2025, 10, 11, 12) + ym(2026, 1, 2, 3, 4, 5, 6, 7, 8, 9), 12),
}
gm = lambda pairs: math.exp(st.mean(math.log(a / b) for a, b in pairs))
print("site months  site_new/old  tfnsw_gm  step_vs_tfnsw (range)   local_gm  step_vs_local")
for s, (o, n, months, lag) in CASES.items():
    rows = []
    for mo in months:
        old = addm(mo, -lag)
        a, b = val.get((s, n, mo)), val.get((s, o, old))
        T = [(val.get((c, cc, mo)), val.get((c, cc, old))) for c, cc in TFNSW.items()]
        if None in (a, b) or any(None in t for t in T):
            continue
        L = [(local(x, mo), local(x, old)) for x in (543, 548, 559)]
        rows.append((a / b, gm(T), gm(L) if all(None not in p for p in L) else None))
    if not rows:
        continue
    rel_t = [r / t for r, t, _ in rows]
    rel_l = [r / l for r, _, l in rows if l]
    loc = f"{st.median([l for *_, l in rows if l]):.2f}      {st.median(rel_l):.2f}" if rel_l else "  -"
    print(f"{s}  {len(rows):>3}     {st.median([r for r, *_ in rows]):.2f}        {st.median([t for _, t, _ in rows]):.2f}"
          f"      {st.median(rel_t):.2f} ({min(rel_t):.2f}-{max(rel_t):.2f})      {loc}")

print("\nMarch 2025 -> March 2026 (workday median, both directions)")
for s, (o, n, *_ ) in CASES.items():
    a, b = val.get((s, o, D(2025, 3, 1))), val.get((s, n, D(2026, 3, 1)))
    if a and b:
        print(s, f"{a:.0f} -> {b:.0f}  x{b / a:.2f}")
for s, c in TFNSW.items():
    a, b = val.get((s, c, D(2025, 3, 1))), val.get((s, c, D(2026, 3, 1)))
    print(s, f"{a:.0f} -> {b:.0f}  x{b / a:.2f}  (continuous TfNSW)")

print("\nSide-by-side overlaps, new/old over the overlap's full days")
for s, o, n, a, b in [(548, 329, 361, D(2025, 10, 31), D(2025, 11, 21)), (559, 332, 368, D(2025, 11, 20), D(2025, 12, 1)),
                      (543, 330, 356, D(2025, 10, 2), D(2025, 10, 2))]:
    x = day.filter(pl.col("SITE_SK") == s, pl.col("date").is_between(a, b), pl.col("slots") >= 90, pl.col("date") != D(2025, 11, 18))
    t = x.group_by("COUNTER_SK").agg(pl.col("bikes").sum())
    t = dict(t.iter_rows())
    print(s, f"{o}->{n}", f"x{t[n] / t[o]:.3f}", "(2025-11-18 excluded: old unit doubled)" if s == 548 else "")
