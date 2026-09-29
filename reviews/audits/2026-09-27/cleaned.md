# Audit of the cleaned output: 24 groups (verdicts at HEAD d5182d7)

Groups audited: G0111 G0112 G0122 G0125 G0158 G0160 G0162 G0163 G0174 G0190 G0210 G0290 G0314 G0338
G0347 G0360 G0374 G0384 G0389 G0445 G0493 G0512 G0540 G0542. That is 108 sites and about 400 series in
`data/clean/weekly.parquet`. Nothing in the repository was modified.

## Summary

Method: I scanned the weekly totals of every series in scope, normalised by `complete_days`. The scan
looked for spikes and dips against the ±6 surrounding weeks, before/after steps, near-zero full weeks,
and complete days at 0 while the series is usually busy. I also checked:

- direction ratios at the piezo and tube sites;
- camera zones' share of the camera total across each outage and restart;
- level changes of each whole camera on the same day across cameras;
- network-wide outage days (`rv.network`);
- every series join.

Each candidate was checked against the 15-minute data, the raw records, the weather and the group's
verdict. I also compared it with how the other 129 verdicts handled the same dates.

Most of the output holds up (see "Checked and holds up" at the end). The problems fall into five main
groups, plus three minor items:

1. **The 15–28 Feb 2013 MetroCount direction fault was left in at 111 (West) and 125 (South West).**
   Fourteen other verdicts, G0122 among them, fixed it as a fault: on those dates one direction also
   counted the other's riders. G0111 and G0125 recorded only `uncertain`, so their inflated directions
   run 2.5–4× normal for two weeks.
2. **Network-wide feed outages are kept as zeros at 112 (and at 125 on 2025-10-23).** The outages are
   2017-05-19..26, 2021-03-19..26 and 2025-10-23. 52, 35 and 64 decisions in other verdicts set these
   same days `missing`. G0112 marked the first two `uncertain` and has nothing for 2025-10-23. G0125
   also has nothing for 2025-10-23.
3. **Vendor-wide detection steps on Secure Agility cameras sit inside single series.**
   - Many cameras stepped about 2× on the same day, **2024-10-02** or **2024-11-07**. The VivaCity
     cameras did not step.
   - G0338, G0347, G0493 and G0374 split their series at these steps.
   - G0360 flagged its step `uncertain` but did not split, and G0389 did not notice its step (both on
     2024-11-07).
   - G0445 read its 2024-10-02 step as riders being diverted. Its zone 447 series also joins levels
     that differ 3–4× across the camera's Nov 2024 reconfiguration.
4. **G0290: zone levels jump at camera restarts, and the series span them.** Zone 293 falls about 5×
   at the 2022-11-08 restart, rises 3–4× at the 2023-05-14 restart and falls again at 2023-07-12. The
   camera total changes 0.54× at the first restart while nearby tubes do not. Only zone 297 was split.
5. **The last day of the record is provisional but counted complete (a code issue).** Every in-scope
   camera's 2026-09-26 was loaded the same day, and its slots from about 15:00 are zeros. The day still
   counts as complete, so the last week of every camera series is about 5–8% low. The reviewers'
   `missing` decisions for it were rightly rejected. The fix belongs in `weekly()`.

Lower-confidence items:

6. G0374 rejoins 2025–26 with 2023–24, backed only by the Oxford St tube 163, which itself drifted.
7. From mid-2026 the camera and the tube on the same Oxford St cycleway disagree (G0512 vs G0163).
8. Short daylight dropouts at camera 284 (G0374) remain below the reviewer's 8-slot rule.

---

## Finding 1: the Feb 2013 direction fault is uncorrected at 111 West and 125 South West

- **Groups / sites / series:**
  - G0111, site 111, series "West" (DIRECTION_SK 16);
  - G0125, site 125, series "South West" (DIRECTION_SK 50);
  - dates 2013-02-15 to 2013-02-28 (probably to 2013-03-01 about 14:00, as found at 122).
- **What the cleaned data shows:**

  | Series | Week 2013-02-11 (Fri–Sun inflated) | Week 2013-02-18 | Week 2013-02-25 | Other direction, same weeks | Normal weeks, this direction |
  |---|---|---|---|---|---|
  | 111 West | 251 | 248 | 159 | East 80 / 51 / 68 | 120–156 |
  | 125 SW | 183 | 366 | 603 | NE 130 / 124 / 164 | 87–124 before, 175–208 after |

  - 111 daily: West is 35–83 bikes a day, against 7–23 before and after; East stays at 8–17.
  - 125 daily: SW is 53–108 on workdays, against 13–20; NE stays at 20–36.
- **Verdicts:**
  - G0111 records `uncertain` (low). It argues that the neighbouring M7 site 114 "shifted its split the
    same way", which "points to a real temporary route change".
  - G0125 records `uncertain` (low): "no mechanism is evident".
  - The shift at 114 is in fact the same fault: G0114 sets 114's inflated direction `missing` for
    exactly these dates.
  - The same one-direction-counts-both fault on 2013-02-15..28 is diagnosed and fixed (`missing` or
    `subtract_other`) in G0092, G0098, G0100, G0103, G0105, G0106, G0107, G0109, G0114, G0116, G0120 and
    G0122 (G0121 and G0110 have it from 2013-02-08).
  - It is a data fault shared by the MetroCount piezos (many sites 15+ km apart, starting and ending on
    the same days), not a change in riding.
- **Evidence** (`rv.directions([s], "2013-01-21", "2013-03-24")`, week 2013-02-18):
  - The inflated direction had at least as many bikes as the other direction in every slot where the
    other had any: covers = 1.0 at 111 (16 over 15) and 1.0 at 125 (50 over 49).
  - The same measure is 1.0 at 122 and 0.997 at 114, against 0.22–0.48 in the other weeks at all four
    sites.
  - The fault starts on Friday 2013-02-15 at all four sites (`rv.daily([111,125,122,114], "2013-02-08",
    "2013-03-06", wide=True)`).
  - At 125 the excess is more than the other direction's count: SW minus NE is 32–72 a day, against a
    normal SW of 13–20. At 111 the AM hour reaches 4.0 against 0.8 plus East's 1.1. So `subtract_other`
    would leave these directions roughly 2× high; this is not recoverable the way it was at 122.
- **Impact:**
  - 111 West: about +350 bikes over two weeks (about +150%).
  - 125 SW: about +575 bikes (about +270%).
  - Affected weeks: 2013-02-11, 02-18 and 02-25.
- **Confidence:** high.
- **Recommendation:**
  - G0111: `missing` on SITE 111 / DIR 16, 2013-02-15 → 2013-02-28 (check whether the morning of 03-01
    is affected, as it was at 122 until 14:00).
  - G0125: the same on SITE 125 / DIR 50.
  - Drop G0111's "real route change" reasoning.
  - Tools: add a network-level view of `directions` ("sites where one direction covers the other on a
    date"), so reviewers of single-site groups can see a fault that many sites share. The same pattern
    appears in the next finding.

## Finding 2: network-wide feed outages are kept as zero days at 112 (and at 125)

- **Groups / sites / series:**
  - G0112, site 112, North and South: 2017-05-19 10:45 → 05-26 12:30, 2021-03-19 11:00 → 03-26 11:00,
    and 2025-10-23;
  - G0125, site 125, both series: 2025-10-23.
- **What the cleaned data shows:** complete days at exactly 0 in both directions (warning status in the
  raw data), counted as complete. Weekly totals (North/South):

  | Week | 112 North / South | Adjacent weeks |
  |---|---|---|
  | 2017-05-15 | 255 / 312 | 418–478 / 555–662 |
  | 2017-05-22 | 169 / 282 | 418–478 / 555–662 |
  | 2021-03-15 | 235 / 382 | 477–666 / 850–1225 |
  | 2021-03-22 | 290 / 649 | 477–666 / 850–1225 |
  | 2025-10-20 | 636 / 1067, with a zero Thursday | — |

  125 in week 2025-10-20: 201 / 196, with a zero Thursday.
- **Verdicts:**
  - G0112 marks 2017-05 and 2021-03 `uncertain`, "no neighbouring counter can show whether bikes
    passed", and has no decision for 2025-10-23.
  - G0125 has no decision for 2025-10-23.
  - G0122 sets the identical spans `missing` as feed outages and cites 125 at 0 on 2025-10-23.
- **Evidence** (`rv.network(...)`):

  | Outage | Zero sites | Zero sites on the days around it | Other context |
  |---|---|---|---|
  | 2017-05-20..25 | 28 of 50 | 7–12 | Network bikes 5–15k against about 21k |
  | 2021-03-20..25 | 18–19 of 68 | 5–6 | Bikes back to 27–28k on 03-24/25 while 18 sites stayed at 0 |
  | 2025-10-23 | 37 of 203 | 0–3 | A dry day |

  - The zeros at 112 begin and end in the same late-morning slots on Fridays as at 122.
  - Tally over all verdicts:
    - 2017-05-22: 52 `missing`, and only G0112 and G0095 `uncertain`;
    - 2021-03-22: 35 `missing`;
    - 2025-10-23: 64 `missing`.
  - I dropped 2021-08-24, also 0 at 112: 39.8 mm of rain and a maximum of 11.5 °C in lockdown, with the
    neighbours at 3–5% of normal. That is plausibly real.
  - I dropped 2021-02-26..03-02: that zero run is local to 112 (network zero sites 7 against 6). The
    verdict's `uncertain` is reasonable.
- **Impact:**
  - 112: 2017 weeks 40–65% low, 2021 weeks 40–70% low, 2025-10-20 about 13% low (about 226 bikes lost).
  - 125: 2025-10-20 about 14% low (about 60 bikes).
- **Confidence:** high.
- **Recommendation:**
  - G0112: turn the two `uncertain` decisions into `missing` with the same spans, and add
    `missing` 112 2025-10-23.
  - G0125: add `missing` 125 2025-10-23.
  - Tools: annotate `rv.zeros(counter=True)` (or `overview`) with the network's zero-site count on those
    days, so reviewers of single-site groups see a feed outage without having to think of running
    `network()`.

## Finding 3: Secure Agility detection steps inside single series (G0360, G0389, G0445)

- **What the data shows across the network.** The median daily raw total per camera, two weeks after
  against two weeks before each date (a scan of `data/raw` for all cameras):

  | Date | Cameras and ratios |
  |---|---|
  | 2024-10-02 | 280 ×2.02, 281 ×1.41, 312 ×2.68, **315 ×2.6** |
  | 2024-11-07 | **282 ×2.2**, 283 ×1.72, 284 ×3.05 (with a restart), **286 ×1.84**, 313 ×3.01, 314 ×2.24, 316 ×1.69, 318 ×2.0, 319 ×2.58, 320 ×2.8, 323 ×1.97 |
  | Controls | the VivaCity cameras 300–303: ×0.92–1.05; tube 155 at site 158 does not step |

  Cameras 60 km apart (282 Blacktown, 286 Coledale) step on the same day, so this is a vendor-side
  detection change, not riding. The G0338 and G0347 reviewers already split at 2024-10-02, G0493 at
  2024-09-27 and G0374 at 2024-11-12.

### 3a. G0360, camera 282 (sites 360–368), 2024-11-07, not split

- **Cleaned data:** the camera averages 102 bikes a day from 8 Oct to 6 Nov 2024 and 212 from 8 Nov to
  7 Dec. The same windows in 2023: 98 → 96. Per zone, per day:

  | Zone / direction | Before | After |
  |---|---|---|
  | 360/781 | 23.7 | 55.2 |
  | 360/739 | 14.8 | 32.4 |
  | 362/699 | 6.7 | 15.3 |
  | 365/773 | 5.6 | 13.4 |
  | 366/732 | 3.1 | 17.5 |

  The step persists: 360 West is 15–23 a day in 2023–24 and 42–66 in 2025–26, and 366 South goes from
  2–3 to 14–22.
- **Verdict:** `uncertain` from 2024-11-07 with no end ("no mechanism to tell"). There are no series,
  so each direction is one series across the step. The brief says to split with dated parts "where its
  readings change level and you cannot tell which level is right".
- **Confidence:** high that a step sits inside the series; medium-high that it is a detection change.
- **Recommendation:** add dated series parts to 2024-11-06 and from 2024-11-08 for every zone (leave
  2024-11-07 out; it is a partial day).

### 3b. G0389, camera 286 (sites 389–399), 2024-11-07, not noticed

- **Cleaned data:** the camera averages 110 bikes a day from 8 Oct to 6 Nov 2024 and 243 from 8 Nov to
  7 Dec (Gong Ride days excluded). The same windows in 2023: 141 → 121. Per zone, per day:

  | Zone / direction | Before | After |
  |---|---|---|
  | 390/939 | 6.7 | 30.6 |
  | 390/759 | 2.4 | 14.6 |
  | 398/710 | 8.2 | 22.7 |
  | 394/717 | 13.6 | 26.6 |
  | 396/786 | 24.3 | 45.6 |

  The step persists: 390 SW is 4–9 a day in 2023–24 and 13–29 in 2025–26 (Gong Ride months aside), and
  398 NW goes from 7–12 to 13–29.
- **Verdict:** the step is not mentioned, and there are no series.
- **Confidence:** high for the step.
- **Recommendation:** re-review G0389 with dated parts at 2024-11-07.

### 3c. G0445, camera 315 (sites 445–448), 2024-10-02, and zone 447 across the Nov 2024 reconfiguration

- **Cleaned and raw data:**
  - The camera's raw daily total is 530–654 on 30 Sep and 1 Oct, then 1,058–1,380 on 2–6 Oct.
  - Tube 158 (counter 155) is 830–1,289, then 556–1,095, over the same days.
  - The camera total relative to 158 is about 0.3–0.5 before and 0.80–0.84 in Oct–Nov 2024.
  - Zone 447 (halved) reads 26–63 a day in Mar–Jun 2024 (0.04–0.07× site 158). From Dec 2024 to Sep 2026
    it reads 92–232 a day (0.13–0.22× site 158). Three zones stopped publishing at the 2024-11-07
    failure, and 447 alone resumed on 2024-11-21.
  - 448 goes from 13–59 a day to 425–483 in Oct–Nov 2024.
- **Verdict:**
  - The zone shifts in July and October are "most likely construction diversions" (`uncertain`).
  - Every zone is one series with high confidence.
  - The verdict itself notes that "the camera's total also rises well above its earlier share of nearby
    site 158".
- **Confidence:**
  - medium-high that the Oct–Nov 2024 weeks are not comparable with Mar–Sep 2024;
  - medium that 447 after 2024-11-21 is not comparable with 447 before July 2024.
- **Recommendation:**
  - Split 445, 446 and 448 at 2024-10-02.
  - Split 447 at 2024-10-02 and at 2024-11-21.
  - At minimum, give 447 from 2024-11-21 its own series.

**Impact of 3a–3c:** the affected series show false 2–6× steps up in late 2024. Anyone reading a
year-on-year trend from these zones would see a doubling that is not in the riding.

**Tools:** add a tool that lists same-day level steps shared by several counters of one vendor, for
example each counter's daily total against its own 4-week median, flagged where many counters step on
the same date. This keeps to INFORMATION.md: it gives reviewers a search method, not a conclusion. It
would also serve Finding 1.

**Out of scope, for follow-up:** cameras 283, 312, 313, 314, 316, 318, 319, 320 and 323 show the same
steps. Their groups should be checked for splits.

## Finding 4: G0290 (camera 249) zone levels change at camera restarts, but the series span them

- **Group / sites:** G0290. The main case is 293 (Moore Park Rd crossing, 460/463); also 290/404, 296
  and 294. The restarts are 2022-11-08, 2023-05-14 and 2023-07-12.
- **Cleaned data** (mean per complete day):

  | Period | Camera | 293/460 | 293/463 | 290/404 | 296/462 |
  |---|---|---|---|---|---|
  | 15 Oct – 4 Nov 2022 | 1,585 | 118 | 142 | 95 | 68 |
  | 9 – 30 Nov 2022 | 861 | 19 | 31 | 46 | 27 |
  | 25 Feb – 19 Mar 2023 | 1,484 | 21 | 33 | 48 | 43 |
  | 15 May – 22 Jun 2023 | 1,498 | 86 | 98 | 88 | 58 |
  | 13 Jul – 10 Aug 2023 | 944 | 25 | 35 | 72 | 29 |

  Over the same windows, Anzac Pde piezo 106 reads 580 → 684 → 667 → 640 → 625, and the Moore Park Rd
  tube 168 reads 349 → 308 → 485 → 445 → 390.

  `rv.compare(293, [168, 106], "2022-10-01", "2023-08-31")`: the ratio of 293 to 168 is 0.45–0.89
  (Oct 2022), then 0.10–0.20 (Nov 2022 – Mar 2023), 0.38–0.50 (15 May – 18 Jun 2023) and 0.09–0.18
  (Jul – Aug 2023). The level flips at each restart and holds between them.
- **Verdict:**
  - Only zone 297 is split, as a zone redefinition on 21 Jun 2022.
  - The other zones are single series with high confidence.
  - The outages themselves are set `missing` correctly.
- **Explanation:** the zone configuration or detection changed at each restart, the same mechanism the
  reviewer accepted for 297. Weather cannot explain a 5× change in one zone's share of the camera,
  since the camera total fell 0.54× while the nearby tubes stayed flat or rose.
- **Impact:** 293's weekly totals change 3–6× between these periods, and 290/296 change about 2×.
- **Confidence:** high for 293; medium for 290, 294 and 296.
- **Recommendation:**
  - Re-review G0290 with dated series parts at 2022-11-08, 2023-05-14 and 2023-07-12, at least for 293
    and 296, and `uncertain` markers where the level cannot be settled.
  - The same zone-share check across outages flags two cases at G0374 zone 375 that also deserve a look:
    - 62–91 a day before the Dec 2023 – Jan 2024 outage, 1–13 after;
    - both of its series have zero-bike full weeks through 2024 – mid-2025.

## Finding 5: the provisional last day (2026-09-26) is counted complete in the weekly totals (a code issue)

- **Scope:** every camera in scope (counters 278, 280, 281, 282, 284, 285, 286, 315, 322 and 324), all
  of their series, week 2026-09-21.
- **What the data shows:**
  - In `data/raw`, the last date of all 16 counters ending 2026-09-26 was loaded on 2026-09-26
    (`ADDED_UPDATED_DATETIME_SYDNEY == date`).
  - Every slot after about 14:45–15:15 is a published 0.
  - The day has all 96 slots valid, so `weekly()` counts it as complete.
  - The piezos and tubes that end on 2026-09-24 were loaded on 09-27 and are complete.
- **Examples:**
  - Counter 281: 1,112 bikes on Saturday 09-26 with 0 after 15:00, against 1,747–1,907 on the previous
    weekend days.
  - Counter 284: 142 bikes after 15:00, against 1,377–1,538 on the previous Saturday and Sunday.
- **Verdicts:** G0347, G0374, G0493 and G0512 all proposed `missing` for these slots. The decisions were
  rejected (rightly: "later loads add the real counts, which this would then erase").
- **Impact:** the last week of each camera series is about 5–8% low. The bias recurs at the end of
  every download.
- **Confidence:** high.
- **Recommendation (code):** in `clean.weekly()`, or when building the slot table, treat a day as
  incomplete when all of its records come from a load dated the same day (the `load` column is already
  computed in `slot_table`), or when the day is within N days of the counter's last load. The brief
  already says the last days are provisional; the weekly output should say so as well.

## Finding 6 (low): G0374 rejoins 2025–26 with 2023–24, supported only by tube 163, which drifted itself

- **Group / sites:** G0374 (camera 284, sites 374–383). The series join pre-2024-11-11 with
  post-2025-01-16, and split off Nov 2024 – Jan 2025 as a "doubled" level.
- **Data:**
  - 377/163 is 0.37–0.48 in 2023–24 and 0.48–0.55 in Jan–Apr 2026, which is the reviewer's rationale.
  - Against the Alison Rd tube 158, 377 is 0.49–0.65 in 2023–24 but 0.78–0.95 in Jan–Apr 2026, and 1.4–1.5
    in the split-off period.
  - 163 itself rose against 158, from 1.2–1.3 to 1.6–1.75, starting Dec 2024.
  - Camera 284 is in the 2024-11-07 cohort (×3.05). Its cohort members 282 and 286 kept their higher
    level through 2026.
- **Confidence:** low to medium. Which tube is right cannot be settled from these data.
- **Recommendation:** on re-review, consider making 2025-01-16 onward its own series instead of
  rejoining it with 2023–24. When in doubt, keep series separate, as the brief says.

## Finding 7 (low, watch): camera 324 (G0512) and tube 163 (G0163) disagree on Oxford St from mid-2026

- **Data:**
  - Camera 324's cycleway zone 512 (100 m from tube 163) was 0.38–0.46× tube 163 through Jun 2026. It
    fell to 0.25–0.33× from the week of 2026-06-29. East OUT (1521) went from about 2,700–3,000 a week to
    1,100–1,300.
  - Tube 163 eastbound held.
  - Tube 163 westbound fell from 2026-07-29. G0163 flags this `uncertain`, ongoing.
  - G0512 calls 512 and 516 "clean and consistent".
- The camera-to-tube ratio also swings seasonally, lower in winter in both 2025 and 2026, but the drop
  in Jul 2026 (0.38 → 0.25) is larger than the 2025 dip.
- **Impact:** at least one of 163 West and 512/516 (both directions) is wrong from late June – July
  2026, by 20–50%.
- **Confidence:** low about which one.
- **Recommendation:** re-examine the two groups together in the next round. Neither verdict mentions
  the other instrument.

## Finding 8 (low): G0374 daylight dropouts shorter than the reviewer's 8-slot rule remain

- On 45 days, camera 284 has 2–7 camera-wide zero slots between 07:00 and 19:00 that are left in. The
  reviewer's by-hand rule only removed days with 8 or more.
- Examples: 2025-03-11 (438 bikes, 7 zero slots), 2025-05-12 (897, 7), 2025-11-15 (1,262, 7), and
  2025-08-25 (hourly total 11–18 at 12:00–14:00, against 200–300).
- **Impact:** a few percent of the affected weeks.
- **Recommendation:** slot-level `missing` for camera-wide daytime zero runs of 2 or more slots at this
  camera, or implement the reviewer's proposed counter-wide rule with a lower threshold.

---

## Checked and holds up

- **2022-02-19 feed-wide doubling:** 158, 160, 162, 163 and 174 were all halved; each had 0 odd slots
  in the raw data. 190, 210 and 542 had odd counts and were rightly left alone.
- **G0122 `subtract_other` (Feb 2013):** it gives a South East/North West ratio of 1.31, against about
  1.1–1.2 normally.
- **Series joins show no level step:**

  | Site | Join | Check |
  |---|---|---|
  | 174 | 108 → 210, label flips at reinstalls | levels match |
  | 175 | 148 → 211 (2022), label swap 2026-06-09 | levels match |
  | 190 | 197 → 299 → 391 | 190/191 = 0.92–0.97 on both sides |
  | 542 | 231 → 355 | 542/168 = 2.7–2.8 before, 2.7–2.95 after |
  | 540 | 328 → 350 | levels match |
  | 158 | label swap 2023-09-18 | flagged `direction_unreliable` |

- **Series splits:** G0162's split at 2025-12-13 and G0163's at 2022-12-13 keep those level changes out
  of the trends.
- **125's doubling from Oct 2024:** it is real. It tracks Wigram St 173, 140 m away (ratio 0.9–1.0).
- **Low weeks that are real:**
  - 2020-02-09 storm;
  - 2021-03-20 floods;
  - 2021-08-24 (39.8 mm, 11.5 °C, lockdown);
  - weeks of 2013-06-24 and 2025-07-28 (heavy rain);
  - week of 2025-08-18 at camera 284 (25–82 mm a day);
  - March Sunday rides at 112, and the Gong Rides at 390–399.
- **`zero_fill`** creates a complete day from a feed gap only at camera 278 on 2026-01-31. There the
  catch-up dump on 02-01 falls in the same week, so the weekly total is right, as the verdict says.
- **Direction-specific decisions:** all name directions that exist at the named site. DIRECTION_SK is
  never shared between sites in scope.
- **The 2025-10-23 outage** is covered in every other in-scope group that has data that day.

## Calls used (from the repo root, under `systemd-run ... MemoryMax=2G`)

- `rv.directions([111], "2013-01-21", "2013-03-24")`, and the same for 125, 122 and 114;
  `rv.daily([111,125,122,114], "2013-02-08", "2013-03-06", wide=True)`.
- `rv.network("2017-05-17", "2017-05-28")`, `rv.network("2021-03-18", "2021-03-27")`,
  `rv.network("2025-10-21", "2025-10-25")`; `rv.daily([112,125,122], "2025-10-18", "2025-10-26", wide=True)`.
- Camera steps:
  ```python
  pl.scan_parquet("data/raw/counts/*.parquet")
    .filter(pl.col("COUNTER_SK").is_in(CAMS) & pl.col("date").is_between(...))
    .group_by("COUNTER_SK", "date").agg(pl.col("TOTAL_15MIN_COUNT").sum())
  ```
  then the median over 18 Sep – 1 Oct against 3–16 Oct, and 24 Oct – 6 Nov against 8–21 Nov 2024.
  Per zone: the same on `counts_15min.parquet`, filtered by `SITE_SK`.
- `rv.compare(293, [168, 106], "2022-10-01", "2023-08-31")`; `rv.compare(542, [168, 163, 158], "2023-09-01")`;
  `rv.compare(190, [191], ...)`; `rv.compare(125, [173, 124], "2024-06-01", "2025-03-31")`.
- Last day:
  ```python
  pl.scan_parquet("data/raw/counts/*.parquet")
    .filter(pl.col("date") >= pl.date(2026, 9, 20))
    .group_by("COUNTER_SK", "date", "ADDED_UPDATED_DATETIME_SYDNEY").agg(...)
  ```
- Weekly totals: `pl.read_parquet("data/clean/weekly.parquet")` with `bikes / complete_days`.
