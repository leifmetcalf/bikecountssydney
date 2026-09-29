import sys; sys.path.insert(0, ".")
import polars as pl, clean, json
SP="data/audit/cams/"; __import__("os").makedirs(SP, exist_ok=True)
g = clean.groups()
c = clean.counters()
pairs = pl.scan_parquet(clean.RAW/"counts"/"*.parquet").select("SITE_SK","COUNTER_SK").unique().collect(engine="streaming").join(g, on="SITE_SK").join(c, on="COUNTER_SK")
pairs.write_parquet(SP+"pairs.parquet")
G = sorted(set(pairs.filter(pl.col("Technology")=="CAMERA")["review_group"]))
rows=[]
for gg in G:
    v=json.load(open(f"reviews/verdicts/{gg}.json"))
    for i,d in enumerate(v["decisions"]):
        rows.append(dict(group=gg, i=i, action=d["action"], factor=d.get("factor"), SITE_SK=d["SITE_SK"], DIRECTION_SK=d.get("DIRECTION_SK"), start=d["start"], end=d.get("end"), conf=d.get("confidence"), rejected=bool(d.get("rejected")), diagnosis=d.get("diagnosis",""), evidence=d.get("evidence","")))
pl.DataFrame(rows, infer_schema_length=None).write_parquet(SP+"decisions.parquet")
sa = pairs.filter((pl.col("Vendor name")=="Secure Agility"))
dirs = pl.read_csv("data/raw/directions.csv", infer_schema_length=0).select(pl.col("DIRECTION_SK").cast(pl.Int16), pl.col("Location in/out").fill_null("NA").alias("io"))
parts=[]; cparts=[]
for cam in sorted(set(sa["COUNTER_SK"].to_list())):
    sites = sorted(sa.filter(pl.col("COUNTER_SK")==cam)["SITE_SK"].to_list())
    for f in clean.site_files(sites):
        s = (pl.scan_parquet(f).filter(pl.col("COUNTER_SK")==cam)
             .group_by("SITE_SK","COUNTER_SK","DIRECTION_SK","date","slot")
             .agg(pl.col("TOTAL_15MIN_COUNT").cast(pl.Int32).sum().alias("n"), (pl.col("Status")==1).any().alias("warn")))
        s = s.collect(engine="streaming")
        d = s.group_by("SITE_SK","COUNTER_SK","DIRECTION_SK","date").agg(
            pl.col("n").sum().alias("bikes"), pl.len().alias("slots"), (pl.col("n")==0).sum().alias("zero_slots"),
            (pl.col("n")>0).sum().alias("nz"), (pl.col("n")%2==1).sum().alias("odd"),
            pl.col("n").filter(pl.col("slot")<20).sum().alias("night"), pl.col("n").filter(pl.col("slot").is_between(28,75)).sum().alias("day7_19"),
            pl.col("n").max().alias("maxslot"), pl.col("warn").any().alias("warn"))
        parts.append(d)
        cparts.append(s.join(dirs, on="DIRECTION_SK", how="left").group_by("COUNTER_SK","date","slot").agg(pl.col("n").sum().alias("bikes"), pl.col("DIRECTION_SK").n_unique().alias("dirs"),
              pl.col("n").filter(pl.col("io")=="IN").sum().alias("IN"), pl.col("n").filter(pl.col("io")=="OUT").sum().alias("OUT")))
out = pl.concat(parts).join(dirs, on="DIRECTION_SK", how="left")
out.write_parquet(SP+"sa_daily.parquet")
cs = pl.concat(cparts).group_by("COUNTER_SK","date","slot").agg(pl.col("bikes").sum(), pl.col("dirs").sum(), pl.col("IN").sum(), pl.col("OUT").sum()).sort("COUNTER_SK","date","slot")
cs.write_parquet(SP+"cam_slots.parquet")
cam = out.group_by("COUNTER_SK","date").agg(pl.col("bikes").sum(), pl.len().alias("dirs"), pl.col("slots").sum(), pl.col("zero_slots").sum(),
    pl.col("bikes").filter(pl.col("io")=="IN").sum().alias("IN"), pl.col("bikes").filter(pl.col("io")=="OUT").sum().alias("OUT"), pl.col("bikes").filter(pl.col("io")=="NONE").sum().alias("NONE"),
    pl.col("night").sum(), pl.col("day7_19").sum()).sort("COUNTER_SK","date")
cam.write_parquet(SP+"cam_daily.parquet")
rng = cam.group_by("COUNTER_SK").agg(pl.date_ranges(pl.col("date").min(), pl.col("date").max()).alias("date")).explode("date", empty_as_null=True)
full = rng.join(cam, on=["COUNTER_SK","date"], how="left").sort("COUNTER_SK","date")
full = full.with_columns(pl.col("bikes").fill_null(0).rolling_median(window_size=29, center=True, min_samples=10).over("COUNTER_SK").alias("med"))
full = full.with_columns((pl.col("bikes").fill_null(0) / pl.col("med")).alias("rel"))
ok = clean.with_workday(cam).join(full.select("COUNTER_SK","date","rel"), on=["COUNTER_SK","date"]).filter((pl.col("rel")>0.3) & (pl.col("bikes")>0))
ok.write_parquet(SP+"cam_daily_ok.parquet")
# slot grid + usual
cs2 = clean.with_workday(cs.filter(~pl.col("COUNTER_SK").is_in([250,338]))).with_columns(clean.slot_start(pl.col("date"), pl.col("slot")).alias("time"))
usual = cs2.group_by("COUNTER_SK","workday","slot").agg(pl.col("bikes").median().alias("usual"))
rng = cs2.group_by("COUNTER_SK").agg(pl.datetime_ranges(pl.col("time").min(), pl.col("time").max(), "15m", time_unit="ms").alias("time")).explode("time", empty_as_null=True)
fs = rng.join(cs2.select("COUNTER_SK","time","bikes"), on=["COUNTER_SK","time"], how="left").with_columns(pl.col("time").dt.date().alias("date"), (pl.col("time").dt.hour()*4+pl.col("time").dt.minute()//15).cast(pl.UInt8).alias("slot"))
fs = clean.with_workday(fs).join(usual, on=["COUNTER_SK","workday","slot"], how="left")
fs.select("COUNTER_SK","time","bikes","usual").write_parquet(SP+"cam_full_slots.parquet")
z = fs.filter(pl.col("bikes").fill_null(0)==0).sort("COUNTER_SK","time").with_columns((pl.col("time").diff()!=pl.duration(minutes=15)).over("COUNTER_SK").fill_null(True).cum_sum().alias("run"))
runs = z.group_by("COUNTER_SK","run").agg(pl.col("time").min().alias("start"), pl.col("time").max().alias("end"), (pl.len()/4).alias("hours"), pl.col("usual").sum().alias("usual_bikes"), pl.col("bikes").is_null().mean().round(2).alias("absent")).drop("run")
runs.filter(pl.col("usual_bikes")>=15).sort("COUNTER_SK","start").write_parquet(SP+"outage_runs.parquet")
print("done", out.shape, cs.shape)
