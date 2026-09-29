# City of Sydney piezo counters: cross-group audit (2026-09-27)

Scope: the City of Sydney (CoS) Ecocounter piezos (COUNTER_SK 222-241, 274) and the MetroCount MC5920 units (COUNCIL,
350-375) that replaced them in Sep-Nov 2025. Reviewed groups: G0542, G0544, G0547, G0549, G0550. Older verdicts:
G0253-G0269, G0537-G0540, G0543, G0546, G0553, G0555-G0558, G0559, G0562. I used the groups under re-review (G0541,
G0545, G0551, G0552, G0554, G0560, G0561) and G0169 (site 548) only as neighbours. I did not modify any repository file.

## Summary

- **The step at the replacement is real growth, not a counter effect.** In matched calendar months, the change at the
  eight Ecocounter-to-MC5920 sites (541, 542, 544, 545, 550, 551, 554, 561) is 0.93-1.13 times the change at eight
  continuous TfNSW counters (median 1.08). It is 0.84-0.99 times the change at the CoS sites that switched between
  MetroCount units. At those sites, side-by-side overlaps show the new unit reads 4-11% higher. From March 2025 to
  March 2026 the replaced sites rose by a median of 18% (range 10-32%). The City's own manual count, a different
  method, rose 20% over the same period. The "+35-45% step while a continuous counter rose ~3%" came from a
  single, unrepresentative control. Over the same months the continuous counters rose 0-36% (geometric mean about
  17-24%).
- **Recommended rule:** join old and new counters (matching directions by AM/PM peak) wherever the step can be
  checked against counters that were not replaced and falls within about ±15%. That is the tolerance the
  program already accepts at the MetroCount-to-MetroCount handovers: G0169 joins 548 with a measured +11% offset.
  Where the check fails or cannot be made, keep the series separate.
  - Change **G0544** to one series per direction (340+1752, 341+1751).
  - The re-reviews of **G0541, G0545, G0551 and G0554** should also join.
  - The joins in **G0542, G0550 and G0561** are upheld.
  - **G0552** stays separate: its step is 1.49-1.72 relative to controls, in both directions.
  - **G0549 and G0560** stay separate.
  - **G0547** could be joined: King St's ratio to Kent St (551) was 1.00 in 2022 and is 1.00 in 2026. This is a
    judgement call because of the 3-year gap.
- **Duplicate-record days are feed-wide.** 40 dates between 2022-04-10 and 2025-08-04 are each shared by 3 or more
  CoS Ecocounters, 37 of them by 9-16. Every affected site-day (all 473 outside Nov 2020) is covered by
  `drop_duplicates` or `missing` in every CoS verdict. In 16-30 Nov 2020 the 2-channel sites went from 1 to 2 records per slot. That was a format change, not a
  duplication (weekly totals are continuous), and all four verdicts rightly leave it alone.
- **All-zero outage days.** The feed-wide outages are covered at every CoS site: 2023-06-30..07-02, 2023-07-25..08-17
  (11 sites, warning records) and 2025-10-23 (37 of 74 non-camera sites in the whole dataset). The six MC5920 units
  first published on 2025-10-23 have complete, normal counts that day. So G0549, G0550 and G0553 rightly set nothing
  missing there. Only 13 of 13,285 all-zero CoS site-days are uncovered, and none of them falls on a feed-wide date.
- **Missed anomaly (group under re-review):** at 561, Epsom Rd, from 2026-01-30 to 02-16 the counter read 0-7 bikes
  a day where it normally reads 150-330. It carried whole-day warning zeros and published no records at all for
  4 days. That points to a counter outage, but the verdict only marks it `uncertain`, so about 3 near-zero weeks
  enter the weekly totals.

---

## Finding 1: the old-to-new step is growth; there is no systematic counter effect

**Groups and sites.** All CoS replacements:
- 541 (G0541): 234 → 354
- 542 (G0542): 231 → 355
- 544 (G0544): 228 → 357
- 545 (G0545): 227 → 358
- 550 (G0550): 226 → 362
- 551 (G0551): 233 → 367
- 552 (G0552): 241 → 360
- 554 (G0554): 225 → 363
- 561 (G0561): 240 → 371
- 568 (G0547): 239 → 366
- 549 (G0549): 238 → 365
- 560 (G0560): 229 → 370

The old counters end between Apr and Aug 2025 (at 544 in Aug 2024, 568 in Feb 2023, 549 in May 2020). The new ones
start between 2025-09-16 and 2025-11-20.

**What the verdicts say.**
- G0542 and G0550 join. G0542 relies on one control: Moore Park Rd (168), which rose 37-45% year on year.
- G0544, G0545, G0551 and G0554 keep separate. Their reasons are that the new counter "reads 25-44% higher" and that
  "every neighbouring counter was replaced at the same time, so real growth cannot be separated from a change in
  detection".
- G0545 also points to a relatively higher off-peak share on the new counter.

**Alternative explanation tested.** Cycling in inner Sydney grew about 20-35% between 2024-25 and 2025-26. Counters
that were not replaced show the same growth, so the step is growth.

**Evidence.**

1. *Matched calendar months, against continuous counters that were never replaced.* The controls are TfNSW sites
   101 (Harbour Bridge), 158, 160, 161, 168, 174, 175 and CoS/COUNCIL 154. The level is the median of workday
   daily totals per month, which ignores scattered duplicate and zero days. The step is new/old in the same
   calendar month (lag 12 months, or 24 for 544), divided by the controls' geometric-mean change.

   | site | months | raw new/old | controls' change | step vs controls (range) | step vs CoS MetroCount sites 543/548/559 |
   |---|---|---|---|---|---|
   | 541 | 2 | 1.01 | 1.09 | 0.93 (0.91-0.95) | 0.84 |
   | 542 | 7 | 1.36 | 1.21 | 1.08 (1.04-1.19) | 0.97 |
   | 544 (lag 24) | 9 | 1.51 | 1.31 | 1.13 (1.00-1.23) | n/a* |
   | 545 | 6 | 1.30 | 1.17 | 1.09 (1.01-1.16) | 0.97 |
   | 550 | 6 | 1.19 | 1.24 | 0.97 (0.91-1.01) | 0.87 |
   | 551 | 7 | 1.39 | 1.21 | 1.12 (1.06-1.19) | 0.99 |
   | 554 | 6 | 1.37 | 1.24 | 1.09 (1.04-1.15) | 0.95 |
   | 561 | 5 | 1.17 | 1.21 | 1.04 (0.87-1.22) | 0.90 |
   | **552** | 8 | **1.97** | 1.26 | **1.60 (1.43-1.76)** | **1.41** |
   | *reference: MetroCount RidePod → MC5920, no change of vendor* | | | | | |
   | 537 | 8 | 1.33 | 1.17 | 1.11 (1.00-1.19) | 0.99 |
   | 538 | 8 | 1.15 | 1.17 | 0.97 (0.83-1.18) | 0.89 |
   | 543 | 12 | 1.53 | 1.23 | 1.24 (1.09-1.57) | 1.08 |

   \*The local controls are unusable for 544's 2024 months, because 559 nearly stopped counting from 2024-06-14 to 07-10.

   Excluding 552, the Ecocounter sites' steps (0.93-1.13, median 1.08) sit inside the spread seen at sites that
   changed only between MetroCount units (0.97-1.24). Those units were validated by overlap (point 3). A +35-45%
   counter effect would put every step near 1.35-1.45 against the controls.

2. *March 2025 → March 2026.* A clean year-on-year comparison: the old counters still ran in March 2025 and the new
   ones in March 2026.

   | group | sites | change |
   |---|---|---|
   | Ecocounter → MC5920 | 542, 545, 550, 551, 554, 561 | 1.24, 1.19, 1.10, 1.32, 1.18, 1.17 (median 1.18) |
   | RidePod → MC5920 (CoS) | 537, 538, 543 | 1.24, 0.97, 1.38 |
   | Continuous TfNSW | 101, 158, 160, 161, 168, 174, 175, 154 | 1.09, 1.09, 1.12, 1.17, 1.34, 1.06, 1.13, 1.00 |

   The City of Sydney's biannual manual survey (78 intersections, the same method both years) rose **20%** from
   March 2025 to March 2026. That is independent of any counter.

3. *Side-by-side overlaps between the old and new MetroCount units* (same bikes, full days):

   | site | old → new unit | overlap | new/old |
   |---|---|---|---|
   | 548 | 329 → 361 | 22 days (excluding 2025-11-18, when the old unit doubled) | ×1.093 |
   | 559 | 332 → 368 | 12 days | ×1.042 |
   | 543 | 330 → 356 | 1 day | ×1.049 |

   The MC5920 therefore reads a few percent high, if anything. The joins at these sites are already accepted
   (G0169, G0543, G0559).

4. *Directions move together.* Per-direction steps against the controls (old → new direction):

   | site | direction step | direction step |
   |---|---|---|
   | 541 | 312→1746: 0.91 | 313→1745: 0.94 |
   | 542 | 322→1747: 1.10 | 323→1748: 1.09 |
   | 544 | 340→1752: 1.08 | 341→1751: 1.18 |
   | 545 | 338→1753: 1.10 | 339→1754: 1.08 |
   | 550 | 336→1762: 0.99 | 337→1761: 0.93 |
   | 551 | 332→1771: 1.12 | 333→1772: 1.12 |
   | 554 | 334→1763: 1.11 | 335→1764: 1.07 |
   | 561 | 348→1779: 1.09 | 349→1780: 1.11 |
   | **552** | 351→1757: **1.49** | 350→1758: **1.72** |

5. *The profile change is network-wide.* On workdays, comparing May 2024-Apr 2025 with Oct 2025-Sep 2026:
   - At the new CoS counters the 00-06h share rises by 0.4-0.9 points and the 07-10h share falls by 0.9-1.6 points.
   - At the continuous TfNSW counters the night share rises by 0.2-0.6 points and the AM share falls by 0.9-2.0
     points: 101 −1.8, 163 −2.0, 154 −4.2.
   - At the RidePod → MC5920 sites (537, 543, 559) the night share rises by 0.2-1.1 points.

   G0545's "relatively much higher off-peak" is part of a network-wide shift, not a detection change.

6. *Real-world corroboration.*
   - The City installed 26 MetroCount RidePods with in-pavement sensors in late 2025, some replacing old units.
   - New infrastructure opened between the old and new counters' spans:
     - the Oxford St West cycleway (Jul-Aug 2025), which meets Bourke St at Taylor Sq, site 542;
     - the King St-College St link (Dec 2025);
     - the Castlereagh St extension to King St, after which Goulburn/Castlereagh rose 36% in 6 months. The old
       counter at 545 already tracked this: its ratio to the controls rose from 2.2 in Mar/Apr 2024 to 2.4/2.7 in
       Mar/Apr 2025.
   - E-bike trips nearly doubled in 2025.

   Sources:
   - [Bicycle NSW, 22 Aug 2025](https://bicyclensw.org.au/tracking-the-rise-of-cycling-in-sydney/)
   - [Bicycle NSW, 22 Sep 2026](https://bicyclensw.org.au/cycling-is-booming-in-sydney-even-in-winter/)
   - [City of Sydney news, Aug 2025](https://news.cityofsydney.nsw.gov.au/articles/sydney-rides-the-wave-towards-a-true-city-for-cycling)

**How to reproduce.**
- Run `reviews/audits/2026-09-27/cityofsydney_step.py` from the repo root, under the memory cap. It prints tables 1-3.
- With the review tools:
  - `rv.monthly([542, 101, 158, 168], "2024-10-01", "2026-04-30")`
  - `rv.compare(545, [101, 158, 168, 163], "2024-10-01", "2026-04-30")` (compare weeks a year apart)
  - `rv.daily([548], "2025-10-31", "2025-11-21", wide=True)` (the overlap)

**Impact.** Series choice does not change any weekly total. What it decides is whether the five busiest CoS
cycleway counters have a continuous trend across 2025. Together these are about 11,000-12,000 workday bikes in 2026 at 542, 544,
545, 551 and 554. With the series split, each site's 2025-26 growth is lost to any trend analysis. Joining creates at
most a ±10% false step, the same tolerance already accepted at 543, 548 and 559.

**Confidence.** High that there is no systematic +35-45% counter effect. Medium that any residual offset is within
±10%.

**Recommendation.**
- Adopt the rule above, and state it in the brief (Finding 9).
- Change G0544's series (Finding 2). The re-reviews of G0541, G0545, G0551 and G0554 should join.
- Keep G0552, G0549 and G0560 separate.

## Finding 2: G0544 should join old and new counters

**Groups and sites.** G0544, site 544, Liverpool St.
- Old counter 228: 340 (East, AM peak) and 341 (West, PM peak). Healthy data up to Aug 2024; exact zeros
  2024-12-31..2025-06-12.
- New counter 357: 1752 (West, AM peak) and 1751 (East, PM peak), from 2025-10-02.

**What the verdict says.** Four separate series. "The 14-month gap and the change of counter, while the neighbouring
counters were replaced too, mean comparability cannot be checked."

**Evidence.**
- Against controls that were not replaced, the lag-24 step is 1.08 (340→1752) and 1.18 (341→1751) per direction,
  1.13 for the site.
- The ratio of 544 to its neighbours barely changes between 2024 and 2026:

  | ratio | Feb-Apr 2024 → 2026 | Jun-Aug 2024 → 2026 | change |
  |---|---|---|---|
  | 544/545 | 2.29 → 2.11 | 2.44 → 2.21 | ×0.92 / ×0.91 |
  | 544/551 | 1.60 → 1.70 | 1.53 → 1.67 | ×1.06 / ×1.09 |
  | 544/554 | | | ×1.12 / ×1.06 |
  | 544/542 | | | ×1.06 / ×1.00 |

  Those neighbours are themselves shown in Finding 1 to carry no counter effect.
- The direction mapping is confirmed by the peaks: 340 and 1752 have 114 and 192 bikes in the 8h hour; 341 and 1751
  have 131 and 229 in the 17h hour.

**Impact.** No change to weekly totals. It gives a continuous 2016-2026 series for the busiest CoS counter (about
3,300 workday bikes in 2026).

**Confidence.** Medium: the check has to span 24 months because of the gap.

**Recommendation.** Replace the four series with two:
- "AM-peak flow": 228/340 + 357/1752.
- "PM-peak flow": 228/341 + 357/1751.

## Finding 3: the joins in G0542 and G0550 are upheld, but G0542's evidence should cite more than one control

**Groups and sites.**
- G0542: 322+1747 (northbound) and 323+1748 (southbound).
- G0550: 336+1762 and 337+1761.

**What the verdicts say.**
- G0542: "the ~45% year-on-year rise Dec-Jan matches the continuous Moore Park Rd tube (168: +37%/+45%)".
- G0550: the hourly profile and the ratios to 106 and 158 are unchanged.

**Assessment.**
- The conclusions are right: the steps against eight controls are 1.08 for 542 and 0.97 for 550. Per direction:
  542 is 1.10/1.09 and 550 is 0.99/0.93.
- G0542's evidence, though, uses the fastest-growing control. Site 168 rose ×1.34 from Mar 2025 to Mar 2026, while
  the Harbour Bridge rose ×1.09. A reviewer who picked a different control could have concluded the opposite, which
  is probably what G0542's earlier reviewer did.
- The mapping of 1747 (labelled East) to northbound holds: it has the AM peak, 196 bikes in the 8h hour against 63.

**Confidence.** High.

**Recommendation.** No change to the decisions. For robustness, this evidence should come from a tool (Finding 9).

## Finding 4: G0552 (Miller St, Pyrmont) has a real discontinuity and should stay separate

**Group and site.** G0552 (under re-review), site 552: 241 (to 2025-08-02) → 360 (from 2025-10-23).

**Evidence.**
- Raw change ×1.97 in matched months, ×1.79 from March to March.
- Against the controls, the steps are 1.49 (351→1757) and 1.72 (350→1758). Against the CoS MetroCount sites the
  site step is 1.41.
- Every other replacement is at 0.93-1.13.
- The two counters are 6 m apart. The old unit's 2 channels split evenly (50/50), so no dead channel explains it.
- In March 2025 the City itself published "Miller Street (Pyrmont): 874 daily trips" from the old counter. A 2021
  report said the Saunders/Miller St cycleway "handles over 1,500 daily bike trips", which suggests the old unit
  under-read. That is weak evidence.

**Assessment.** A counter or installation difference, or an unexplained local change. Either way the join cannot be
validated.

**Confidence.** High that the join fails the check. The cause is unknown.

**Recommendation.** Keep G0552's four separate series, which is the current verdict. Do not propose a scale: nothing
shows a mechanism.

## Finding 5: long gaps (G0549 and G0560 stay separate; G0547 is joinable)

**G0549 (549, Kent St south of Margaret St).** The old counter was dead from 2020-05-18. The ratio of 549 to its
corridor neighbour 551 (Kent St south of Druitt St) moved from 1.19 (Mar-May 2019) to 0.90 (Mar-May 2026), and from
1.03 to 0.87 (Jun-Aug). That is ×0.75-0.84 over 7 years that include COVID. A counter effect cannot be told apart
from a real shift. **Keep separate (upheld, high).**

**G0560 (560, Blackwattle Bay).** The recorded coordinates of the new counter 370 are 206 m from the old counter 229.
The direction labels change (N/S to W/E), and there is a 3-year gap. **Keep separate (upheld, high).**

**G0547 (568, King St west of Kent St).** The old counter 239 ended in Feb 2023; the new counter 366 is at 568 from
2026-02-16. The verdict keeps them separate because of the "2.7-year gap and different level (~590/day in 2022 vs
~1000/day in 2026)". But the level difference is not evidence of a counter effect. 551 (Kent St), with its own
counter change, grew exactly as much: the ratio 568/551 was 1.02 in Mar-May 2022 and 1.01 in Mar-May 2026, and 1.00
and 0.99 in Jun-Aug. Each window has about 63-66 workdays.

The coordinates differ: 239 is at 151.20639, 366 at 151.20427, about 200 m apart. The flow measured, however, tracks
551 identically in both eras. **A join is supportable (confidence low-medium).** Under the Finding 1 rule, join
329+1770 and 328+1769. Keeping them separate is defensible because of the gap, but the reason should be the gap, not
the level.

Reproduce: ratios of workday daily totals from `rv.daily([549, 551, 568], ...)` for the months named.

## Finding 6: duplicate-record days are a feed-wide event, and every CoS verdict covers them

**Evidence.**
- A duplicate day is a full day with at least 1.8 times the usual records per slot. From 2022, 40 dates are each
  shared by 3 or more CoS Ecocounters, and 37 of them by 9-16 of the 16-20 active ones: 2022-04-10, 06-06, 06-21,
  07-31, 09-08, 09-10; 2023-02-14, 04-23, 05-23, 07-20, 07-24, 10-06, 12-08; many dates in 2024 up to 11-29/30.
  2025-06-21 (5 of 9 active) and 2025-08-04 (3 of 7) are the last.
- All 473 duplicated CoS site-days outside Nov 2020 are covered by a `drop_duplicates` or `missing` decision in the
  site's verdict.
- The same event also recurs on the old RidePod units:
  - the doubling (all-even counts) at 537, 538, 540, 543, 548 and 559 ends on 2024-05-19 at all six, and all six
    verdicts scale 0.5 to that date;
  - 2025-11-18 is doubled at both 548 and 559, and both are scaled 0.5.
- The single-site days (541 on 2024-01-08, 561 on 2024-02-26, 541/551 on 2024-08-02, 258 on 2024-10-19) are also
  covered.

**Nov 2020 format change.** From 16 to 30 Nov 2020 the 2-channel sites (253, 541, 551, 560) carry 2 records per
slot instead of 1. The totals are continuous: 541's weekly totals were 10,080 and 10,410 in the weeks of Nov 9 and
Nov 16. So this is a new channel, not a duplicate. G0541 and G0560 explicitly restore it, and G0253 and G0551 leave it
alone: consistent.

**Caveat for the tools.** `duplicates()` flags these days, because the month's usual record count is 1.
`drop_duplicates` there would drop a genuine second-channel record wherever both channels happened to hold the same
value.

**Confidence.** High.

**Recommendation.** None for the verdicts. For the tools, see Finding 9.

## Finding 7: all-zero days (feed outages covered; 2025-10-23 correct for the counters that started that day)

**Evidence.**
- There are 13,285 all-zero CoS site-days. All but 13 are covered by `missing`. The feed-wide ones:
  - 2023-06-30..07-02;
  - 2023-07-25..08-17 (11 CoS sites, 2,300-3,800 warning records a day);
  - 2025-10-23. Across the whole dataset, every counter already in the feed was a warning zero that day (37 of 74
    non-camera sites), including 537-546, 548 and 559. Each of those CoS verdicts sets that day missing.
- The six MC5920 units first published on 2025-10-23 have full, normal days, with night counts from 00:00:

  | site | unit | 2025-10-23 | 2025-10-24 |
  |---|---|---|---|
  | 547/568 | 366 | 2,059 | 1,605 |
  | 549 | 365 | 1,891 | 1,578 |
  | 550 | 362 | 1,014 | 936 |
  | 552 | 360 | 1,909 | 1,606 |
  | 553 | 364 | 1,526 | 1,314 |
  | 554 | 363 | 2,134 | 2,118 |

  So G0549, G0550 and G0553 rightly set nothing missing that day. These units were evidently counting before the feed
  carried them; their high first days (Thursday) are ordinary weekday levels.
- The 13 uncovered all-zero site-days:
  - 544, 4 days (2017-08-06, 09-23, 10-08; 2019-03-24): weekends with 1-8 bikes on the adjacent days. G0544 judged
    them real closures. They coincide only with CoS counters that were dead for months (253, 254, 255, 560), not
    with any working counter, so there is no feed-wide cause. The verdict holds.
  - 256, 4 days (see Finding 10).
  - 561, 5 days (see Finding 8).

**Confidence.** High.

**Recommendation.** None, apart from Findings 8 and 10.

## Finding 8: the 561 outage in Jan-Feb 2026 is left in the weekly totals (note for the G0561 re-review)

**Group, site and dates.** G0561 (under re-review), site 561, counter 371, directions 1779 and 1780, from
2026-01-29 20:00 to 2026-02-16 19:45.

**What the verdict says.** It is `uncertain`: "could be a local path closure (trickle of riders) or a sensor fault".
The verdict's summary wrongly says this period is "set to missing".

**Evidence.**
- Daily totals of 0-7 per direction, against 150-330 before and after.
- 1780 has whole-day warning zeros on 01-30..02-01 and 02-05; 1779 on 02-05 and 02-12..15.
- There are no records at all on 02-07..02-10, and 1780 has none on 02-02 and 02-11..15.
- A closed path does not stop a counter publishing or trigger TfNSW's warning flag. Missing loads and warnings point
  to a counter or comms outage.
- No other CoS counter has warnings or zeros on these dates.

**Impact.** Site totals, both directions, from the raw data:
- The week of 2026-01-26 counts all 7 days as complete, 3 of them near-zero. It reads 788 against 1,317-1,412 in
  the weeks before (−40%).
- The week of 2026-02-16 counts all 7 days as complete, the Monday near-zero. It reads 1,776 against 2,273 the week
  after.
- The week of 2026-02-02 has 4 "complete" days that total 15 bikes.
- The week of 2026-02-09 has no complete days.

**Confidence.** Medium.

**Recommendation.** `missing` for the whole span, for both directions.

## Finding 9: brief and tools, the cause of the inconsistency

Every reviewer who kept the series separate did so because they could not find a control outside the replacement
program. "Every neighbouring counter was replaced at the same time" appears in G0545, G0551 and G0554, and
effectively in G0544. G0542's earlier reviewer found a control that happened to rise about 3%.

**Recommendations.**
- **Tool:** add `rv.step(site, old_counter, new_counter)`. For matched calendar months (lag 12, or 24 across longer
  gaps) it would return:
  - the site's new/old change;
  - the same change at every counter that ran through both periods on one device, with their geometric mean;
  - per-direction peak-hour matching.

  This supplies a method, not a conclusion, and is consistent with INFORMATION.md.
- **Brief:** say that comparability can be checked against counters anywhere in the dataset that ran through both
  periods. State the tolerance already in use: joins are accepted where overlaps show +4-11%. Leave "when in doubt
  keep separate" for cases where no such check is possible.
- **Tool:** make `duplicates()` and `drop_duplicates` robust to a mid-month change in channel count, for example by
  using the modal record count of the day's neighbours rather than of the month (Finding 6).

## Finding 10 (minor): G0256 zero days not set missing

**Group, site and dates.** G0256, site 256 (Buckland St east of Garden St), counter 223, both directions:
2018-01-14 (Sunday, 0.2 mm rain) and 2018-04-23 (Monday, dry). Adjacent days read 9-32 per direction.

2016-06-05 (the 68 mm East Coast Low) and 2017-05-19 (14.6 mm) are plausibly real.

**Impact.** About 20 bikes, roughly 10-15%, in each of two weeks of a very low-volume series.

**Confidence.** Low-medium.

**Recommendation.** Optionally set 2018-01-14 and 2018-04-23 missing, or mark them `uncertain`.

---

## Checked and found sound

- G0549's `uncertain` for the 2013-09-20..12-08 dip. King St (568) was unchanged throughout (about 840-970 per
  direction on workdays), so this is not a detour through King St. The channel split stays even and the NB profile
  keeps its shape at about 1/14 scale. That fits either a partial sensor failure or a closure, and nothing
  published settles it, so `uncertain` stands.
- Direction mappings across the replacements, by AM/PM peak:
  - labels swapped between the counters at 544 and 552 (and 537);
  - labels kept at 541, 542 (N→E), 545, 550, 551, 554 and 561.

  The verdicts that join or pair directions have them right.
- The in-scope cleaned weekly series (`data/clean/weekly.parquet`, built 12:36 today) against the control index:
  only one week deviates more than ±50% from its rolling ratio. It is 544 AM, the week of 2021-07-05, the start of
  Sydney's lockdown: a real change.
