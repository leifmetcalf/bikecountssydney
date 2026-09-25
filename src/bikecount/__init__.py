import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="TfNSW cycling counts: download the raw 15-minute data and clean it.")
    sub = parser.add_subparsers(dest="command", required=True)

    dl = sub.add_parser("download", help="download raw 15-minute NSW cycling counts to data/raw/cycling")
    dl.add_argument("--threads", type=int, default=8, help="number of download threads")

    cl = sub.add_parser("clean", help="apply automatic fixes and review decisions; build weekly totals")
    cl.add_argument("--raw", type=Path, default=Path("data/raw/cycling"), help="raw data directory")
    cl.add_argument("--out", type=Path, default=Path("data/clean/cycling"), help="output directory")
    cl.add_argument("--cache", type=Path, default=Path("data/interim/slots.parquet"), help="cached slot table, rebuilt when the raw data changes")
    cl.add_argument("--decisions", type=Path, default=Path("reviews/decisions.csv"), help="review decisions to apply (none if the file does not exist)")
    cl.add_argument("--series", type=Path, default=Path("reviews/series.csv"), help="reviewed series for weekly totals")

    rv = sub.add_parser("review", help="write review briefs, or collect verdicts into reviews/decisions.csv and reviews/series.csv")
    rv.add_argument("action", choices=["briefs", "collect"])
    rv.add_argument("groups", nargs="*", help="review groups to write briefs for (default: all)")

    pl_ = sub.add_parser("plot", help="write an HTML page of cleaned daily counts with review decisions marked")
    pl_.add_argument("sites", nargs="*", help="SITE_SK or SITE_SK:COUNTER_SK (default counter: every counter at the site)")
    pl_.add_argument("--random", type=int, help="plot this many random site-counters with at least a year of data")
    pl_.add_argument("--seed", type=int, default=0)
    pl_.add_argument("--out", type=Path, default=Path("sites.html"))
    pl_.add_argument("--title", default="Counter Review")
    pl_.add_argument("--intro", help="opening sentence for the page")
    pl_.add_argument("--clean", type=Path, default=Path("data/clean/cycling"))
    pl_.add_argument("--raw", type=Path, default=Path("data/raw/cycling"))
    pl_.add_argument("--decisions", type=Path, default=Path("reviews/decisions.csv"))
    pl_.add_argument("--events", type=Path, default=Path("events.csv"))

    args = parser.parse_args()
    if args.command == "download":
        from .download import run

        run(args.threads)
    elif args.command == "clean":
        from .clean import run

        run(args.raw, args.out, args.cache, args.decisions, args.series)
    elif args.command == "review":
        review_cmd(args)
    else:
        plot(args)


def review_cmd(args) -> None:
    from . import review as rv

    if args.action == "collect":
        d, sr = rv.collect()
        print(f"{d.height} decisions -> {rv.DECISIONS}; {sr.select('SITE_SK', 'series').n_unique()} series -> {rv.SERIES}")
        return
    groups = args.groups or rv.groups()["review_group"].unique().sort().to_list()
    for g in groups:
        rv.write_brief(g)
    print(f"{len(groups)} briefs -> {rv.BRIEFS}")


def plot(args) -> None:
    import polars as pl

    from . import export

    counts = args.clean / "counts_15min.parquet"
    if args.random:
        pairs = export.random_pairs(counts, args.random, args.seed)
        intro = f"{len(pairs)} site-counters drawn at random (seed {args.seed}) from those with at least a year of complete days."
    else:
        wanted = [tuple(int(v) for v in s.split(":")) for s in args.sites]
        all_pairs = pl.scan_parquet(counts).select("SITE_SK", "COUNTER_SK").unique().collect().rows()
        pairs = [p for w in wanted for p in sorted(all_pairs) if p[0] == w[0] and (len(w) == 1 or p[1] == w[1])]
        intro = "Selected site-counters."
    if args.intro:
        intro = args.intro
    intro += (" Lines show cleaned daily counts: outages, doubled and duplicated records and impossible values are already"
              " fixed or removed, and review decisions applied. Shaded periods have a review decision; events come from events.csv.")
    data = export.payload(counts, args.decisions, args.raw, args.events, pairs)
    export.write_page(data, args.out, args.title, intro)
    print(f"{len(data)} site-counters -> {args.out}")
