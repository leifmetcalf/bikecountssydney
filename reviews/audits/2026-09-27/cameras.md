# Audit: Secure Agility intersection cameras

Scope: G0290 (camera 249), G0314 (250, 278), G0338 (280), G0347 (281), G0360 (282), G0374 (284), G0384 (285), G0389 (286), G0445 (315), G0464 (318), G0493 (322), G0512 (324). I used G0428, G0456, G0569 and G0577 (under re-review) and the out-of-scope Secure Agility groups (G0274, G0298, G0329, G0369, G0432, G0449, G0475, G0484, G0509) only for comparison. G0464 has uncommitted changes in the working tree; I audited the working-tree version. I changed no repository file.

Scratch tables (camera-level daily and slot totals for all 30 Secure Agility counters) are rebuilt by
`reviews/audits/2026-09-27/cameras_build.py` (from the repo root; tables go to data/audit/cams/)
(run it with the 2G systemd-run cap; it reads one site file at a time).

## Summary

The reviewers were right about most things. They missed or treated differently some events that only show up when all the cameras are read together.

1. **Network-wide detection steps in late 2024.** Almost every Bosch/Secure Agility camera's bike count jumped by 1.5 to 3 times, in waves:
   - 2024-08-29 in the morning: 313 and 314, the same morning several cameras came back from long outages.
   - 2024-09-27 to 2024-10-04: 322, 280, 281, 312 and 315.
   - 2024-11-07 around midday: 282, 283, 286, 313, 314, 316, 318, 319, 320 and 323. Cameras 284 and 315 failed that same day.

   The new levels last into 2026 (checked year on year), and nearby independent counters stayed flat. G0338, G0347, G0464 and G0493 split their series at these dates. **G0360 and G0389 did not split, and flagged only some zones. G0445 put its camera's doubling down to a construction diversion.**
2. **G0290 (camera 249, the older Meraki generation)** changes zone levels at every restart. On 2022-11-08, 2023-05-14 and 2023-07-12 the Moore Park Rd crossing (293) went 210 → 49 → 162 → 57 bikes a day. There is no uncertain decision and no series split. G0274, a camera of the same generation that restarted on the same days, flagged the same thing.
3. **G0464 (camera 318)** lost about half its detection from May to August 2024, measured against two nearby independent counters. It recovered in steps on 2024-08-29 and at the 2024-10-04 restart. No decision covers this.
4. **Network-wide outages that some groups missed.** 2023-09-20 from 08:15 to 16:00 and 2023-11-10 from 00:00 to 17:00: 11 to 13 cameras read 0 at the same moments, in dry weather, with no catch-up afterwards. G0389 has no missing decision for either; it marked 11-10 uncertain as "maybe a very wet day". Also missed:
   - the Sunday-night outage of 2023-11-12/13 (G0338, G0374);
   - the before-counting zeros on the first day (G0360, G0389, G0445).

   The effect is small but real: 2 to 10% of the affected weeks.
5. **Feed changes held up, and so did one right call to keep data.**
   - Zero direction-days disappear from the feed network-wide around 2025-06-15 to 06-24, and zero slots within days around 2025-10-15 to 10-27. The reviewers' `zero_fill` dates are consistent with this, and `zero_fill` does not turn real outages into zeros anywhere that matters.
   - The network-wide zero stretch on 2025-11-13 from 09:30 to 11:15 is followed by a backlog dump at 11:30, so the groups that left it as it is were right.
   - Separately: zones that count only even numbers were halved in G0347 and G0445 but not in G0432 (zone 444 on camera 314).

## Findings

### F1. Late-2024 detection steps are shared across the network; G0360, G0389 and G0445 treat them differently from the other groups

**Groups and sites**
- G0360 (282, all zones)
- G0389 (286, all zones)
- G0445 (315: 445, 447, 448)

For comparison: G0338 (280), G0347 (281), G0464 (318), G0493 (322) and G0432 (313, 314).

**What the verdicts say**
- G0338 splits at 2024-10-02, G0347 at 2024-01-24 and 2024-10-02, G0493 at 2024-09-27, and G0464 at 2024-11-07. All of them name a camera detection change.
- G0360 records `uncertain` from 2024-11-07 with no end on sites 360, 362, 365 and 366 only, and defines no series: "could be a real change in riding or a camera detection/zone change, with no mechanism to tell … no neighbouring counters".
- G0389 records `uncertain` on 390 only, from 2024-11-04, and defines no series.
- G0445 calls the October 2024 shifts "most likely construction diversions" and records `uncertain` on 445 (2024-07-11 to 10-03) and 448 (2024-10-04 to 11-07), with no split.

**Alternative explanation**
The same vendor change reached every Bosch camera in waves. Ratios of workday medians (21 days after ÷ 21 days before) at each date:

| Date | Cameras with a step (ratio) |
|---|---|
| 2024-08-29, from about 08:00 | 313 ×2.1, 314 ×2.2 (G0432: "changed detection level overnight on 29 Aug 2024 and 7 Nov 2024 … while a nearby piezo stayed flat") |
| 2024-09-27 to 10-04 | 280 ×2.3, 281 ×1.5, 312 ×2.5, 315 ×2.7, 322 ×1.4. The daily totals of 280, 281 and 315 rise on 10-02 and 10-03, in the middle of the school holidays. |
| 2024-11-07, from about 12:00 | 282 ×2.2, 283 ×1.6, 286 ×2.0, 313 ×2.6, 314 ×2.2, 316 ×1.8, 318 ×2.1, 319 ×2.7, 320 ×2.7, 323 ×2.1. Camera 284 went dark at 07:45 and came back on 11-12 at ×3.3; 315 went dark at 17:00. |

Cameras that stepped in October did not step again in November (280 ×1.11, 281 ×1.04).

**Evidence that these are steps, not seasons**

Camera 282, workday means per day for Oct 8 to Nov 6 of 2023, of 2024 and of 2025, with Nov 8 to Dec 6 2024 in between:

| | 2023 | 2024 | Nov-Dec 2024 | 2025 |
|---|---|---|---|---|
| Camera total | 107 | 106 | 223 | 241 |
| 360 | 32 | 41 | 94 | 79 |
| 362 | 11 | 12 | 25 | 30 |
| 363 | 13 | 11 | 16 | 22 |
| 365 | 17 | 13 | 31 | 37 |
| 366 | 15 | 13 | 35 | 47 |
| 368 | 7 | 6 | 10 | 13 |

Camera 286, same windows:

| | 2023 | 2024 | Nov-Dec 2024 | 2025 |
|---|---|---|---|---|
| Camera total | 111 | 98 | 221 | 185 |
| 390 | 8.5 | 6.8 | 34 | 36 |
| 393 | 1.1 | 0.9 | 6.8 | 6.1 |
| 394 | 20 | 16 | 33 | 29 |
| 396 | 39 | 36 | 60 | 55 |
| 398 | 15 | 14 | 34 | 21 |
| 399 | 7.4 | 5.7 | 13 | 10 |

At 286 the 390 step starts on 11-08: 390/939 reads 6, 2, 3, 5 on Nov 4-7 and 26 on Nov 8. The step is not on 11-04.

At 315, camera totals were 530 and 654 on Sep 30 and Oct 1, then 1058 on 10-02, 1334 on 10-03 and 1324 on 10-04. The redistribution between zones (447 down; 445 and 448 up) comes on 10-04, two days after the total had already doubled. The reviewer's own evidence shows the camera total against tube 158 moving from about 0.5 to about 0.8.

Nearby independent counters stayed flat: 550 read 834 then 829 (Oct → Nov), 174 read 273 then 274, and the G0338, G0347, G0432 and G0464 reviewers reported their neighbours flat.

The whole camera's IN/OUT balance also shifts at the steps: 282 goes from 1.10 to 0.80, 318 from 1.10 to 0.88, 322 from 1.00 to 1.40 and 280 from 0.85 to 0.75. A shift like that points to classification, not riding.

I could not confirm a path closure on Alison Rd in October 2024. Randwick's November 2024 cycleways committee agenda lists "Alison Road – length of shared path near Doncaster Avenue", but the PDF returned 403. Kingsford–Centennial Park cycleway works on this corridor started in December 2023 and August 2025
([Randwick](https://www.randwick.nsw.gov.au/about-us/news/related-news/december/kingsford-to-centennial-park-cycleway-now-open),
[TfNSW](https://www.transport.nsw.gov.au/projects/current-projects/kingsford-to-centennial-park-walking-cycling),
[agenda](https://www.randwick.nsw.gov.au/__data/assets/pdf_file/0004/406165/CABFAC-Agenda-November-2024.pdf)).
A diversion moves riders between zones; it does not double the camera total on the same day as three other cameras.

**Calls to reproduce**
```python
rv.monthly(rv.group_sites("G0360"), "2023-09-01", "2025-12-31")
rv.monthly(rv.group_sites("G0389"), "2023-09-01", "2025-12-31")
rv.daily(rv.group_sites("G0389"), "2024-10-28", "2024-11-20", wide=True)
rv.daily([445, 446, 447, 448], "2024-09-28", "2024-10-12", wide=True)
rv.compare(470, [550, 174], "2024-10-01", "2024-12-15")   # 318 steps, neighbours flat
```
For all cameras at once, total `TOTAL_15MIN_COUNT` per `COUNTER_SK` and date over one site file at a time (see `build.py`).

**Impact**
- G0360 and G0389: with no split, every series in these cameras shows a false 1.5 to 5 times jump in November 2024. Camera totals rise by 110 to 125%, zone 390 by 5 times.
- G0445: series 445 and 448 carry a one-month bump of about 2 to 8 times in October 2024.

**Confidence**
- High that the steps are shared and come from the detection.
- Medium on the exact cause at 315, where the zone reshuffle is mixed in.

**Recommendation**
- Re-review G0360 and G0389. Split every zone-direction at 2024-11-07, with the part before ending 2024-11-06. The step comes around midday on the 7th; for 286 zone 390 it is visible from the 8th. Extend `uncertain` to all zones.
- For G0389, correct the start date from 2024-11-04 to 2024-11-07.
- For G0445, split 445, 447 and 448 at 2024-10-02, and 447 again at 2024-07-11 and 2024-11-21 (its meaning changes each time). Reword the diagnosis.
- Tools: add a camera-network view, for example `rv.cameras(start, end)` giving each camera's daily total relative to its own median. It gives reviewers the search method without telling them the conclusion, which is the INFORMATION.md policy.

### F2. G0290 (camera 249): zone levels jump at every restart; no decision, no split

**Group and sites**: G0290, sites 293 (Moore Park Rd crossing), 290, 294, 296 and 319, all directions.

**What the verdict says**: outages are set missing. The only level issues it records are zone 297 (split 2022-06-21) and 319 (uncertain because of phantom bursts). It records nothing at the restarts.

**Anomaly**: workday means per day in the windows before and after each restart.

| Site | Oct 10 - Nov 4 2022 | Nov 9 - Dec 2 2022 | Feb 20 - Mar 17 2023 | May 15 - Jun 22 2023 | Jul 13 - Aug 11 2023 |
|---|---|---|---|---|---|
| 293 | 210 | 49 | 50 | 162 | 57 |
| 290 | 141 | 79 | 78 | 137 | 112 |
| 294 | 349 | 215 | 233 | 292 | 221 |
| 296 | 166 | 98 | 166 | 152 | 106 |

The restarts fall between the windows: after the 2022-11-05 to 11-08 outage, after the 2023-03-20 to 05-14 outage, and after the 2023-06-23 to 07-12 outage.

Day by day, 293 reads 180-246 before 2022-11-05 and 40-65 after, and 175-279 in June 2023 and 46-70 after 2023-07-12. A drop to a quarter in November, when riding rises, is not seasonal.

Camera 247 (G0274, same Cisco/Meraki generation, same restart on 2022-11-05 to 11-07) shows the same thing, and G0274 flagged it `uncertain` from 2022-11-08 to 2023-04-29 ("zone levels drift at every restart").

The 2023-07-12 restart came at about 10:30, the same morning cameras 278 to 286 started publishing, so it is probably a vendor-side intervention.

**Calls to reproduce**
```python
rv.daily([290, 293, 294], "2022-10-31", "2022-11-15", wide=True)
rv.daily([290, 293, 294], "2023-06-16", "2023-07-20", wide=True)
rv.monthly(rv.group_sites("G0290"), "2022-06-01", "2023-10-31")
```

**Impact**: false trends of ×0.25 to ×3 in 293, and ×0.5 to ×1.8 in 290, 294 and 296, across the three restarts.

**Confidence**: high that the changes are real and tied to the restarts. Which level is right is unknown.

**Recommendation**: re-review G0290. Record `uncertain`, and split series for 290, 292, 293, 294 and 296 at 2022-11-08, 2023-05-14 and 2023-07-12.

### F3. G0464 (camera 318): detection roughly halved from May to August 2024, not flagged

**Group and sites**: G0464, all 318 zones (464 to 474), 2024-04-29 to 2024-10-04.

**What the verdict says**: only the 2024-11-07 step (`uncertain`, series split). The period from 2024-03-25 to 2024-11-06 is treated as one level.

**Anomaly**: the ratio of zone 470 to piezo 550, from `rv.compare(470, [550, 174], "2024-03-25", "2024-11-06")`:

| Period | 470/550 |
|---|---|
| April 2024 | 0.082 to 0.089 |
| Late May to July | 0.026 to 0.047 |
| 2024-09-02 to 09-16, after the vendor restoration morning of 2024-08-29 | 0.087 to 0.108 |
| October, after the 09-27 to 10-04 outage and restart | 0.078 to 0.094 |

The whole camera against 550, on workday medians:

| Period | 318/550 |
|---|---|
| March to April | 0.49 to 0.51 |
| Late April to May | falling steadily |
| June to August | 0.20 to 0.26 |
| September | 0.28 to 0.33 |
| October | 0.40 to 0.43 |

Tube 174 shows the same shape. Every 318 zone dips together: 470 falls from about 450 to about 150 a week, 467 from 400 to 140, 472 from 800 to 300 and 473 from 450 to 145. From April to July, peers of the same vendor fell 25 to 40% (313, 314, 319) and nearby piezos 24 to 34% (174, 254, 541, 550); 318 fell 65%. The recovery is abrupt on the morning of 2024-08-29 (8-10 am totals: 17-27 → 35), the same morning cameras 278, 279, 285, 312 and 320 came back from outages that started in May.

**Impact**: 318's weekly totals for June to August 2024 are about half what the level before and after implies. That is about 130 against about 270 bikes a day across the camera.

**Confidence**: medium. The decline is gradual, not a clean step, and two other nearby piezos (538, 540) also dipped that winter.

**Recommendation**: add `uncertain` on all 318 sites from 2024-04-29 to 2024-10-03. Consider a dated series split so no trend runs through the dip, for example 2024-04-29 to 2024-10-03 as its own part. Do not scale it.

### F4. Network-wide outages missed or treated differently

**Anomaly**: I searched camera-wide runs of 0 or absent slots with at least 15 usual bikes, and matched them against each group's site-wide `missing` decisions.

| Event (Sydney time) | Cameras at 0 | Not covered in scope | Evidence |
|---|---|---|---|
| 2023-09-20 08:15-16:00 (Wed) | 12: 244-249 and 278-286 | **G0389** (286): no decision | 0.0 mm rain, 34 °C; no catch-up at 16:15 at any camera. 286 read 60 that day against 80-115 on nearby weekdays. `rv.zeros(rv.group_sites("G0389"), "2023-09-19", "2023-11-11", counter=True)` gives 08:15-16:00 with 92 usual bikes. |
| 2023-11-09 21:30 to 11-10 17:15 | 11 | **G0389**: `uncertain`, "maybe a very wet day" | 0.2 mm rain on 11-10. All 11 cameras end at 16:45-17:15 with no catch-up. 286 read 22 against about 105. |
| 2023-11-12 19:30 to 11-13 05:00 (Sunday night) | 8 | **G0338** (280, about 154 usual), **G0374** (284, about 160), and G0360 and G0384 (15-17 usual each) | Covered by G0290, G0314 and G0347. |
| First-day zeros before counting | – | **G0360** 2023-07-12 00:00-10:15; **G0389** 2023-07-13 00:00-10:45; **G0445** 2024-03-25 00:00-16:45 | G0314, G0338, G0347, G0374, G0464 and G0493 set their first-day zeros missing. 315 read 153 on 2024-03-25 against 530-700 on the following days. |

The two 2023 daytime outages have no dump afterwards (counts resume at usual levels), so the counts are lost and `missing` is the right action.

**Impact**
- 286: weeks of 2023-09-18 and 2023-11-06 low by about 5% and 10%.
- 315: week of 2024-03-25 (a full Monday-to-Sunday week) low by about 10% for its 5 published directions.
- 280 and 284: weeks of 2023-11-06 low by about 2%.
- G0360 and G0389 first days: partial weeks, negligible.

**Confidence**: high.

**Recommendation**
- Add `missing` for all G0389 sites for 2023-09-20 08:15-16:00 and 2023-11-09 21:30 to 2023-11-10 17:15, replacing the uncertain.
- Add `missing` for the first-day zeros in G0360, G0389 and G0445 (G0445 up to 16:45).
- Add `missing` for 2023-11-12 19:30 to 2023-11-13 05:00 in G0338 and G0374. Optional for G0360 and G0384.

### F5. Feed changes are network-wide; the `zero_fill` scopes hold up

**Groups**: all groups with `zero_fill`.

**Finding**: two feed changes happen on nearly the same dates at every camera.
- **Whole zero direction-days dropped from about 2025-06-15 to 06-24.** Zero-total direction-days published per month fall to 0 at every camera from July 2025. The last ones appear between 2025-06-04 and 06-23, with a few reappearing in October 2025.
- **Zero slots within days dropped from 2025-10-15 to 10-27.** The first partial days with no zeros appear on these dates:

| Date | Cameras |
|---|---|
| 2025-10-15 | 281, 284, 285 |
| 2025-10-16 | 282, 324 |
| 2025-10-23 | 286, 314, 318 |
| 2025-10-24 | 312, 317 |
| 2025-10-27 | 279, 280 |
| 2025-11-01 | 313 |
| 2025-11-11 | 322 |
| 2025-12-03 | 278 (after it was recommissioned) |

The reviewers' `zero_fill` starts (2023-07-12, 2024-03-25, 2024-11-18, 2025-06-01, 06-15, 06-19, 06-25, 07-16, 11-28, all ongoing) all cover the change dates. Where they start earlier, the absent direction-days they fill are quiet zones, with usual counts of 0-1 a day over Christmas 2023/24. I found no case where `zero_fill` turns a real multi-hour outage into zeros, except:
- 278 on 2026-01-31 to 02-01, recovered by the dump at 09:30 in the same week, as G0314 noted;
- the evening edges of the G0493 outages, which are negligible.

Small gaps:
- G0389 starts 2025-06-25, but 286 was already omitting zero days on 06-22 to 06-24. That leaves 9 quiet direction-days incomplete; they drop out of weekly totals and the loss is about 0.
- G0338 fills only 338, 339 and 341; every absent or partial day after July 2025 is in those sites.

Camera 315 never omits zeros; only zone 447 survives after November 2024.

**Confidence**: high.

**Recommendation**: no change to decisions. Tell reviewers, through a tool rather than the brief, that feed changes can be network-wide (see F1).

### F6. 2025-11-13 09:30-11:15: a feed outage with a backlog dump; leaving it as it is was right

Every Bosch camera publishing that day (279-286, 312-318, 322, 324) publishes explicit zeros from 09:30 to 11:15, with no warning status. Piezos and tubes count normally. At 11:30 the cameras dump a backlog: the camera sum is 2,004 against about 500-700 usual (280: 337, 313: 443, 314: 367, 324: 281). G0338, G0347, G0445, G0464, G0493 and G0512 made no decision, and their weekly totals are right. G0374's `missing` on 2025-11-13 is part of its daylight-dropout range for 284, which has no dump, and stays.

**Recommendation**: none. It is worth adding to the brief's facts that camera feeds sometimes deliver a backlog in one slot after a gap, which several reviewers found independently (G0314, G0360).

### F7. Zones with only even counts: halved in two groups, not in a third

- 281/356 (G0347): both directions, 104k non-zero slots, all even. Halved from 2023-07-12.
- 315/446, 447, 448 (G0445): all even. Halved.
- 314/444 (G0432, out of scope but the same camera family): directions 1229 and 1319, 44k non-zero slots, all even from 2024-03 to 2025-12. **Not halved.** G0432 only split it at the detection steps.

No other Secure Agility zone is below 5% odd slots over a month with 40 or more non-zero slots.

The even-only property survives the 2024 detection steps, at 356 and at 444. That fits a zone-geometry mechanism (each bike counted twice) and not a software one.

**Confidence**: high on the inconsistency.

**Recommendation**: re-review 314/444 in G0432 for `scale` 0.5.

### F8. G0374 (284): the verdict holds up; watch September 2026

G0374 gives the doubled level from 2024-11-12 to 2025-01-15 its own series and joins what comes before and after. Tube 163 bears this out: zone 377 reads 0.38-0.48 of tube 163 in 2023-24, 0.81-0.87 in the doubled period, and 0.37-0.54 from January to July 2026. So 284 got the 2024-11-07 update and later reverted, unlike the other cameras in F1.

From the week of 2026-08-31, however, 284 against tube 163 rises from about 2.0 to 3.0-3.5. Zones 374, 377, 378 and 380 are each up 25-60%. Over the same weeks, 324 against 163, 100 m away, stays at 1.1-1.2. This is data from after the review, so there is no decision to challenge.

**Confidence**: low (four weeks, spring).

**Recommendation**: flag for the next review of G0374. The series from 2025-01-16 onward may need a new split.

### F9. Checked and not supported (no action)

- **The 2024-01-24 step** is local to camera 281, where G0347 handled it. Camera 249's early-2024 rise is the 319 phantom bursts, which G0290 already covered, and 280, 278, 285 and 286 are flat at that date.
- **Phantom bursts** (340, 343, 319, 375, 380, 472, 396) share no dates across cameras once G0384's whole-period 387/388 decisions are excluded. They are local.
- **Dark-hour false detections** (G0384, zones 387/388): 0-5 am shares of 10-19% at 387/388 against camera medians of 0.2-3%. They are local. 278 on George St also reaches 10-23%, but night riding in the CBD is plausible.
- **G0445's proposal** that 315 goes blind from dusk to dawn: all 6 evenings where 315 read 0 with at least 15 usual bikes after a normal daytime were wet (0 of 6 dry). That is consistent with real low riding.
- **Whole-camera IN/OUT imbalance.** Camera 278 read IN/OUT 2.0-2.4 in 2023-24 (326 IN 169 a day against 39 OUT). G0314's split at the 14-month gap already separates it, and 278 reads 1.1-1.25 afterwards. The other imbalances (249 about 1.3, 322 about 1.4 after its step) are zone geometry, and each zone-direction is its own series.
- **The 2026-09-26 cut-off from 15:00** at every camera: the last-day decisions are rejected or left `uncertain` (G0360) everywhere. That is consistent and correct: the data is provisional.
- **324 (G0512) in July to September 2026**: zone 516 against tube 163 fell from 0.85 in June to 0.53-0.78. It had already dipped to 0.70 in late May, and the dip started on a 17 mm rain day (2026-06-25). Inconclusive, dropped.
- **2024-09-26**: a low day at every camera, with 40 mm of rain and a 15 °C maximum. It is real, and the groups keep it.
