import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="TfNSW cycling counts: download the raw 15-minute data and clean it.")
    sub = parser.add_subparsers(dest="command", required=True)

    dl = sub.add_parser("download", help="download raw 15-minute NSW cycling counts to data/raw/cycling")
    dl.add_argument("--threads", type=int, default=8, help="number of download threads")

    cl = sub.add_parser("clean", help="apply automatic fixes and build the review queue")
    cl.add_argument("--raw", type=Path, default=Path("data/raw/cycling"), help="raw data directory")
    cl.add_argument("--out", type=Path, default=Path("data/clean/cycling"), help="output directory")
    cl.add_argument("--cache", type=Path, default=Path("data/interim/slots.parquet"), help="cached slot table, rebuilt when the raw data changes")
    cl.add_argument("--events", type=Path, default=Path("events.csv"), help="known real-world events")
    cl.add_argument("--decisions", type=Path, default=Path("review_decisions.csv"), help="review decisions to apply")

    pl_ = sub.add_parser("plot", help="write an HTML page of cleaned daily counts with review flags marked")
    pl_.add_argument("sites", nargs="*", help="SITE_SK or SITE_SK:COUNTER_SK (default counter: every counter at the site)")
    pl_.add_argument("--random", type=int, help="plot this many random site-counters with at least a year of data")
    pl_.add_argument("--seed", type=int, default=0)
    pl_.add_argument("--out", type=Path, default=Path("sites.html"))
    pl_.add_argument("--title", default="Counter Review")
    pl_.add_argument("--intro", help="opening sentence for the page")
    pl_.add_argument("--clean", type=Path, default=Path("data/clean/cycling"))
    pl_.add_argument("--raw", type=Path, default=Path("data/raw/cycling"))
    pl_.add_argument("--events", type=Path, default=Path("events.csv"))

    args = parser.parse_args()
    if args.command == "download":
        from .download import run

        run(args.threads)
    elif args.command == "clean":
        from .clean import run

        run(args.raw, args.out, args.cache, args.events, args.decisions)
    else:
        plot(args)


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
              " fixed or removed. Shaded periods are flagged for review; events come from events.csv.")
    data = export.payload(counts, args.clean / "review_queue.csv", args.raw, args.events, pairs)
    export.write_page(data, args.out, args.title, intro)
    print(f"{len(data)} site-counters -> {args.out}")
