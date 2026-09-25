"""Chart pages from the cleaned counts: daily totals per direction, with review decisions and events marked."""

import html
import json
import random
from pathlib import Path

import polars as pl

TEMPLATE = Path(__file__).parent / "templates" / "sites.html"
MIN_VALID_SLOTS = 90  # a day is drawn only when this many of its 96 slots are valid after cleaning


def daily(counts: Path) -> pl.LazyFrame:
    return (
        pl.scan_parquet(counts)
        .group_by("SITE_SK", "COUNTER_SK", "DIRECTION_SK", "date")
        .agg(pl.col("count").cast(pl.Int32).sum().alias("tot"), pl.col("count").is_not_null().sum().alias("valid"))
    )


def random_pairs(counts: Path, n: int, seed: int, min_days: int = 365) -> list[tuple[int, int]]:
    """n random (site, counter) pairs with at least min_days complete days."""
    d = daily(counts).filter(pl.col("valid") >= MIN_VALID_SLOTS).group_by("SITE_SK", "COUNTER_SK").agg(pl.col("date").n_unique().alias("days"))
    pairs = d.filter(pl.col("days") >= min_days).sort("SITE_SK", "COUNTER_SK").select("SITE_SK", "COUNTER_SK").collect().rows()
    return random.Random(seed).sample(pairs, min(n, len(pairs)))


def payload(counts: Path, decisions_csv: Path, raw: Path, events_csv: Path, pairs: list[tuple[int, int]]) -> list[dict]:
    sel = pl.DataFrame(pairs, schema={"SITE_SK": pl.Int16, "COUNTER_SK": pl.Int16}, orient="row")
    day = daily(counts).join(sel.lazy(), on=["SITE_SK", "COUNTER_SK"]).sort("date").collect()
    read = lambda name, key: {r[key]: r for r in pl.read_csv(raw / name, infer_schema_length=0).to_dicts()}
    sites, counters, directions = read("sites.csv", "SITE_SK"), read("counters.csv", "COUNTER_SK"), read("directions.csv", "DIRECTION_SK")
    decisions = pl.read_csv(decisions_csv, infer_schema_length=0).filter(pl.col("status") != "rejected") if decisions_csv.exists() else None
    events = pl.read_csv(events_csv, infer_schema_length=0) if events_csv.exists() else None
    out = []
    for site_sk, counter_sk in pairs:
        s, c = sites.get(str(site_sk), {}), counters.get(str(counter_sk), {})
        x = day.filter((pl.col("SITE_SK") == site_sk) & (pl.col("COUNTER_SK") == counter_sk))
        dirs = []
        for d_sk in sorted(x["DIRECTION_SK"].unique()):
            g, d = x.filter(pl.col("DIRECTION_SK") == d_sk), directions.get(str(d_sk), {})
            rows = [[str(dt), tot if valid >= MIN_VALID_SLOTS else None] for dt, tot, valid in g.select("date", "tot", "valid").iter_rows()]
            dirs.append({"key": str(d_sk), "orient": d.get("Orientation description", str(d_sk)), "inout": d.get("Location in/out") or "", "rows": rows})
        marks = []
        if decisions is not None:
            for r in decisions.filter(pl.col("SITE_SK") == str(site_sk)).to_dicts():
                marks.append({"kind": r["action"], "dir": r["DIRECTION_SK"], "start": r["start"], "end": r["end"], "detail": f"{r['diagnosis']} ({r['status']})"})
        if events is not None:
            for e in events.filter(pl.col("sites").str.split(";").list.contains(str(site_sk))).to_dicts():
                marks.append({"kind": "event", "dir": None, "start": e["date"], "end": e["end_date"], "detail": f"{e['name']}: {e['effect']}"})
        out.append({
            "site": str(site_sk), "name": s.get("Site name", f"Site {site_sk}"), "suburb": s.get("Suburb") or "", "lga": s.get("LGA") or "",
            "facility": s.get("Facility description") or "", "location": s.get("Location name") or "",
            "counter_id": c.get("Counter ID", ""), "tech": c.get("Technology", ""), "dirs": dirs, "marks": marks,
        })
    return out


def write_page(data: list[dict], out: Path, title: str, intro: str) -> None:
    page = TEMPLATE.read_text()
    page = page.replace("__TITLE__", html.escape(title)).replace("__INTRO__", html.escape(intro))
    # the data sits inside a <script>: keep a "</script>" in any text field from closing it
    page = page.replace("__DATA__", json.dumps(data, separators=(",", ":")).replace("</", "<\\/"))
    out.write_text(page)
