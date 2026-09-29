"""Checking a review group's new verdict against its previous one (how to act on it: reviews/CHECKING.md).

    uv run python -c "import check; check.report('G0101')"            # against the verdict at git HEAD
    uv run python -c "import check; check.report('G0101', 'HEAD~1')"  # or any git revision, or a .json path

(under the memory cap, see CLAUDE.md). It prints both verdicts' decisions, the group cleaned under each (fixes, weekly
totals, and per counter-direction the full weeks and mean weekly bikes that changed, since series names change between
reviews), and flags for mistakes reviewers have made before:
    DROPPED  a scale, direction_unreliable, subtract_other or drop_duplicates of the old verdict with no counterpart
    TAIL     a decision with a fixed end in the last days of the data (provisional, or an ongoing fault given an end)
    SCOPE    a camera-wide `missing` recorded for only some of the camera's sites
    SWAP?    the direction carrying a counter's weekday morning peak flips (a label swap, or a dead direction);
             read from the raw data, so periods already set missing flag too
    ZERO WEEKS  full weeks with 0 bikes at a direction that usually carries traffic
Reviewers never see this module or its output.
"""

import collections
import datetime
import json
import subprocess

import polars as pl

import clean
import review as rv

NOTES = ("uncertain", "restore")


def verdict(group: str, rev: str | None = None) -> dict:
    """The group's verdict: the working tree's, or at a git revision, or from a .json path."""
    if rev is None:
        return json.loads((clean.VERDICTS / f"{group}.json").read_text())
    if rev.endswith(".json"):
        return json.loads(open(rev).read())
    out = subprocess.run(["git", "show", f"{rev}:reviews/verdicts/{group}.json"], cwd=clean.ROOT, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def cleaned(v: dict, sites: list[int]) -> tuple[pl.DataFrame, pl.DataFrame]:
    """The group's sites cleaned under verdict `v` alone: the direction-slots and the weekly totals per series."""
    reviewed = clean.reviewed
    clean.reviewed = lambda kind: [x for x in v[kind] if not x.get("rejected")]
    try:
        dec, parts = clean.decision_table(), clean.series_table()
    finally:
        clean.reviewed = reviewed
    final = clean.clean_group(sites, dec)
    return final, clean.weekly(final, clean.series_parts(final, parts))


def _live(v: dict) -> list[dict]:
    return [d for d in v["decisions"] if not d.get("rejected")]


def _day(s: str | None) -> str:
    return (s or "9999-12-31")[:10]


def _parts(v: dict) -> set:
    return {(s["SITE_SK"], tuple((p["COUNTER_SK"], p["DIRECTION_SK"], p["start"], p["end"]) for p in s["parts"])) for s in v["series"] if not s.get("rejected")}


def report(group: str, old: str = "HEAD", new: str | None = None) -> None:
    """Compare the verdict at `old` with the working tree's (or `new`), then print the flags."""
    vo, vn = verdict(group, old), verdict(group, new)
    sites = rv.group_sites(group)
    print(f"===== {group} sites {sites}")
    for name, v in (("old", vo), ("new", vn)):
        acts = collections.Counter(d["action"] for d in _live(v))
        print(f"  {name}: {len(v['decisions'])} decisions {dict(acts)}; {len(v['series'])} series")
    for d in _live(vn):
        if d.get("end") is None:
            print(f"  ONGOING {d['action']} site {d['SITE_SK']} dir {d.get('DIRECTION_SK')} from {d['start']}: {d.get('diagnosis', '')[:120]}")
        if d["action"] == "scale" and d.get("factor") != 0.5:
            print(f"  SCALE factor {d.get('factor')} site {d['SITE_SK']} {d['start']}..{d['end']}: {d.get('diagnosis', '')[:120]}")

    (fo, wo), (fn, wn) = cleaned(vo, sites), cleaned(vn, sites)
    for name, f, w in (("old", fo, wo), ("new", fn, wn)):
        fixes = {str(k): n for k, n in f.group_by("fix").len().iter_rows() if k}
        print(f"  {name}: fixes {fixes}; missing raw bikes {f.filter(pl.col('count').is_null())['raw'].cast(pl.Int64).sum():,}; "
              f"series-weeks {w.height:,}, bikes {w['bikes'].sum():,}, full weeks {w.filter(pl.col('complete_days') == 7).height:,}")
    by_direction = clean.series_parts(fo, clean.series_table().clear())
    full = lambda f: clean.weekly(f, by_direction).filter(pl.col("complete_days") == 7).group_by("SITE_SK", "series").agg(
        pl.len().cast(pl.Int64).alias("weeks"), pl.col("bikes").mean().round(0).alias("mean"))
    j = full(fo).join(full(fn), on=["SITE_SK", "series"], how="full", suffix="_new", coalesce=True).with_columns(
        (pl.col("weeks_new").fill_null(0) - pl.col("weeks").fill_null(0)).alias("d_weeks"), (pl.col("mean_new") / pl.col("mean")).round(3).alias("mean_ratio"))
    changed = j.filter((pl.col("d_weeks").abs() >= 4) | ((pl.col("mean_ratio") - 1).abs() >= 0.02) | pl.col("mean_ratio").is_null())
    if changed.height:
        print("  counter-directions whose full weeks or mean weekly bikes changed:")
        print(changed.sort("SITE_SK", "series"))
    so, sn = _parts(vo), _parts(vn)
    print(f"  series: {len(so & sn)} unchanged, {len(so - sn)} only old, {len(sn - so)} only new")
    for s in vn["series"]:
        if not s.get("rejected") and len(s["parts"]) > 1 and len({(p["COUNTER_SK"], p["DIRECTION_SK"]) for p in s["parts"]}) > 1:
            key = (s["SITE_SK"], tuple((p["COUNTER_SK"], p["DIRECTION_SK"], p["start"], p["end"]) for p in s["parts"]))
            if key not in so:
                print(f"   NEW JOIN {s['SITE_SK']} {s['name']}: {[(p['COUNTER_SK'], p['DIRECTION_SK'], p['start'], p['end']) for p in s['parts']]}")
    flags(group, vo, vn, sites, fn)


def flags(group: str, old: dict, new: dict, sites: list[int], final: pl.DataFrame) -> None:
    print(f"  --- flags {group}")
    for d in _live(old):
        if d["action"] in ("scale", "direction_unreliable", "subtract_other", "drop_duplicates") and not any(
            e["action"] == d["action"] and e["SITE_SK"] == d["SITE_SK"] and _day(e["start"]) <= _day(d["end"]) and _day(d["start"]) <= _day(e["end"])
            for e in _live(new)
        ):
            print(f"  DROPPED {d['action']} site {d['SITE_SK']} dir {d.get('DIRECTION_SK')} {d['start']}..{d['end']}: {d['diagnosis'][:120]}")

    slots = rv.slots(sites)
    last = slots["date"].max()
    for d in _live(new):
        if d["action"] not in NOTES and d["end"] is not None and _day(d["end"]) >= str(last - datetime.timedelta(days=3)):
            print(f"  TAIL {d['action']} site {d['SITE_SK']} dir {d.get('DIRECTION_SK')} {d['start']}..{d['end']}: {d['diagnosis'][:100]}")

    spans = collections.defaultdict(set)
    for d in _live(new):
        if d["action"] == "missing":
            spans[d["start"], d["end"]].add(d["SITE_SK"])
    for c, csites in slots.select("SITE_SK", "COUNTER_SK").unique().group_by("COUNTER_SK").agg("SITE_SK").iter_rows():
        if len(csites) < 2:
            continue
        for (a, b), ss in spans.items():
            part = ss & set(csites)
            text = " ".join(d["diagnosis"].lower() for d in _live(new) if (d["start"], d["end"]) == (a, b))
            wide = any(k in text for k in ("camera", "counter-wide", "every zone", "all zones", "whole counter", "all sites", "every site"))
            if 1 <= len(part) < len(csites) and (len(part) > 1 or wide):
                print(f"  SCOPE counter {c}: missing {a}..{b} at {sorted(part)} of {sorted(csites)}")

    cameras = clean.counters().filter(pl.col("Technology") == "CAMERA")["COUNTER_SK"].implode()
    am = slots.filter(pl.col("workday") & pl.col("time").dt.hour().is_between(7, 8) & ~pl.col("COUNTER_SK").is_in(cameras))
    q = am.group_by("SITE_SK", "COUNTER_SK", "DIRECTION_SK", pl.col("date").dt.truncate("3mo").alias("q")).agg(pl.col("count").cast(pl.Int64).sum().alias("am"))
    for (site, c), part in q.group_by("SITE_SK", "COUNTER_SK"):
        dirs = sorted(part["DIRECTION_SK"].unique().to_list())
        if len(dirs) != 2:
            continue
        a, b = str(dirs[0]), str(dirs[1])
        w = part.pivot(on="DIRECTION_SK", index="q", values="am", sort_columns=True).sort("q").drop_nulls()
        w = w.filter((pl.col(a) + pl.col(b)) >= 200).with_columns((pl.col(a) / (pl.col(a) + pl.col(b))).alias("share"))
        sh, qs = w["share"].to_list(), w["q"].to_list()
        flips = [f"{qs[i]}: {sh[i - 1]:.2f}->{sh[i]:.2f}" for i in range(1, len(sh)) if (sh[i - 1] - 0.5) * (sh[i] - 0.5) < 0 and abs(sh[i] - sh[i - 1]) > 0.25]
        if flips:
            used = [(s["name"], [(p["COUNTER_SK"], p["DIRECTION_SK"], p["start"], p["end"]) for p in s["parts"]]) for s in new["series"] if not s.get("rejected") and any(p["COUNTER_SK"] == c for p in s["parts"])]
            print(f"  SWAP? site {site} counter {c}: share of the morning peak in {a} flips {flips}")
            print(f"     series using counter {c}: {used or 'none (one per labelled direction)'}")

    w = clean.weekly(final, clean.series_parts(final, clean.series_table().clear())).filter(pl.col("complete_days") == 7)
    z = w.group_by("SITE_SK", "series").agg(pl.col("bikes").median().alias("median"), (pl.col("bikes") == 0).sum().alias("zero_weeks"))
    z = z.filter((pl.col("median") >= 50) & (pl.col("zero_weeks") > 0))
    if z.height:
        print("  ZERO WEEKS at busy directions:")
        print(z)
