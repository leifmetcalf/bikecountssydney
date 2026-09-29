# Audit: TfNSW and council Metrocount piezo and tube groups

Scope: G0111, G0112, G0122, G0125, G0158, G0160, G0162, G0163, G0174, G0190, G0210, G0540, plus network-wide
scans (a) and (b) over every site. No repository file was changed. My intermediate tables (direction-day,
hourly and pair summaries built from the raw records) are in
a session scratchpad (not kept; the `rv` calls below reproduce every claim). Every claim below was checked against the raw data, and each finding lists
`rv` calls that reproduce it.

## Summary

- **The 2013-02-15 → 2013-03-01 direction artefact is feed-wide and handled five different ways.** At 25 of the
  27 Metrocount piezo sites with counts then (all but 96 and 101), one direction also counted the other direction's riders: it is
  ≥ the other direction in 100% of slots, and subtracting slot by slot restores the normal peak profile. Only G0122
  uses the right fix (`subtract_other`). Ten older groups set the inflated direction `missing`. G0111, G0115 and
  G0125 left `uncertain` notes (G0111 even calls it "a real route change" because M7 site 114 shifted the same way).
  Eleven groups have nothing at all, G0112 among them. The inflated weeks are +30% to +150% for one direction.
- **G0112 keeps two network-wide week-long outages as real zeros.** These are 2017-05-19 → 05-26 and
  2021-03-19 → 03-26, each a clean Friday-midday to Friday-midday cut at 12–16 counters at once. Every other
  group sets them `missing`. G0112's flood explanation for March 2021 doesn't hold, because the same cut hit
  counters far from any river. Four G0112 weeks read 30–60% low.
- **Feed-wide one-day events were missed by some groups:**
  - 2025-10-23 (37 Metrocount counters at zero): missed by G0112 and G0125, and by G0091 (under re-review).
  - 2025-10-20 (a second zero day, 25 counters): missed by G0179, G0191 (site 192) and G0203.
  - 2022-02-19 doubling: missed by G0172.
- **G0162's "unexplained" 2–3× step at Hawthorne Canal on 2025-12-13 is the Inner West GreenWay opening**
  (officially 14 Dec 2025). It is new infrastructure, so the series split and the `uncertain` note should go.
- **Label swaps that the series don't follow:**
  - G0125 (in scope): swapped from the 2022-07-04 restart to about 2025-04.
  - G0109: two swaps, at the 2012 and 2022 reinstalls.
  - G0120: swap at the Dec 2011 reinstall.
  - G0164: swapped 2022-08-17 → 2022-09-06.
  - G0107 and G0121 mark their swaps `direction_unreliable` rather than switching series parts, which is not how
    newer verdicts handle the same thing.
- **Smaller issues:**
  - Heavy-rain zero days are handled inconsistently; for example, adjacent sites 190 and 191 are treated
    differently on 2020-02-09.
  - G0112 leaves a dry-weather local outage (2021-02-26 → 03-02) as zeros.
  - G0540 has an uncovered near-zero stretch on 2026-09-01 → 09-03.
  - G0163's westbound decline gets support from a co-located camera that the reviewer never saw (the default
    `rv.neighbours` hides cameras).
- **What holds up:**
  - G0122's decisions and G0158's decisions and series.
  - G0160.
  - G0174's three swaps.
  - G0190's series and outages.
  - G0210.
  - G0540's doubling. Its 2023-10 → 2024-05-19 doubling is shared with 537, 538, 543, 548 and 559, all handled.
  - G0125's 2015-17 works period: the M4 widening ran from March 2015 to July 2017.
  - G0111's 2016-12 → 2019 `missing`.

---

## (a) Feed-wide days: every group whose verdict does not handle them

Method: I built a direction-day table from all raw records, one site at a time with the streaming engine, and
flagged these patterns:

- Isolated all-even days (≥ 12 non-zero slots, every one even, with the neighbouring days odd).
- Zero days on a counter that usually has ≥ 10–20 bikes that weekday.
- Days with records per slot ≥ 1.25× the month's usual.
- Days where one direction covers the other in every hour.

I counted each pattern per date and vendor. Coverage means a non-rejected decision of the matching action
spanning that site, direction and date.

| Date(s) | Vendor / sites | What | Groups not handling it |
|---|---|---|---|
| 2013-02-15 → 03-01 (2013-02-08 → 02-21 at 121; 02-15 → 02-21 at 103, 110, 115) | Metrocount piezo, 25 sites | one direction = own + other's riders | G0091, G0092, G0093, G0094, G0095, G0098, G0112, G0113, G0119, G0123, G0124 (nothing); G0111, G0115, G0125 (`uncertain` only); G0103, G0105, G0106, G0107, G0109, G0110, G0114, G0116, G0120, G0121 (`missing` where `subtract_other` recovers). Only G0122 is right. See F1. |
| 2014-10-31 → 11-06 | 5–6 Metrocount | zeros | all handled |
| 2017-05-19 ~12:00 → 05-26 ~12:00 | 15 Metrocount | week of zeros | **G0112** (uncertain). See F2. |
| 2021-03-19 ~11:00 → 03-26 ~11:00 | 12 Metrocount | week of zeros | **G0112** (uncertain). See F2. |
| 2022-02-19 | 19 Metrocount tube and piezo sites | all even at 1.8–3.2× | **G0172** (site 172, dirs 101/102). See F4. |
| 2023-10 → 2024-05-19; 2025-11-18 | Metrocount 537/538/540/543/548/559 | long doubling | all handled |
| 2025-10-20 | 25 Metrocount (mostly council) | zero day | **G0179** (179), **G0191** (site 192), **G0203** (203). See F3. |
| 2025-10-23 | 37 Metrocount | zero day | **G0112**, **G0125**, G0091 (under re-review). See F3. |
| 2012-01-20..23, 2018-05-25..31, 2019-06-02..07, 2020-10-30..11-04, 2023-06-30..07-02, 2023-08-11..17 | Ecocounter | zero runs | all handled |
| 2013-08-18 | Ecocounter, 6 sites | zero day | G0256 (site 256; ref 32/day, minor) |
| 40 days 2022-04-10 → 2024-11-30 (e.g. 2022-09-08/10, 2023-10-06, 2024-01-09, 2024-03-24/25) | Ecocounter, 7–14 sites | repeated records (all-even) | G0253 (2024-01-22, dir 314), G0258 (2024-02-26, dir 325; only `uncertain`), G0554 (2024-02-26, dir 334; re-review), G0561 (2022-07-31 and 2022-09-10, dir 349; re-review). Every other day is handled. |
| 14 days 2024-03-06 → 2025-10-07 | VivaCity, 6–14 zones | all-even ~2× | G0404 (only a blanket `uncertain` 2023-10-23 → 2026-03-18 for dirs 1101/1105/1119/1133/1135/1138/1140/1157/1160/1173/1176); G0423 (dirs 1110, 1124: nothing) |
| 2025-10-13 → 10-31 | Secure Agility, 10–35 zones | 2 records per slot | nothing needed: `rv.duplicates` finds no repeated values (second load of 0) |
| 2026-03-01 → 03-08 | Secure Agility G0569, G0577 | real repeats (e.g. dir 1817: 185, dir 1820: 276 repeated bikes) | G0569, G0577 (being re-reviewed; pass to their reviewers) |

Heavy-rain days (2016-06-05, 2020-02-09, 2021-08-24, 2022-07-03) show up as zero clusters too. They are weather,
not feed events (see F7). I found no feed-wide partial-day cut-offs: every clustered run of zero hours falls on a
wet day.

---

## F1. The Feb 2013 "one direction counts both" artefact is feed-wide (G0111, G0112, G0125; G0122 is the model)

**Verdicts:**
- G0122: `subtract_other` on dir 45, 2013-02-15 → 03-01 14:00 (correct).
- G0111: `uncertain`, "the neighbouring M7 counter shifted its split the same way, which points to a real cause".
- G0125: `uncertain` on dir 50, "no mechanism is evident".
- G0112: nothing.
- Older groups: see the table above.

**Explanation:** a processing artefact across the whole Metrocount piezo feed. From 2013-02-15 00:00 until
2013-03-01 (about midday), one direction at each site was published as its own count plus the other direction's.
This is not a route change. The M7 counter G0111 cites is one of the 25 sites affected.

**Evidence:**
- Share of slots with bikes in the other direction where the inflated direction has at least as many (per site,
  before → during → after):
  - 111 dir 16: 0.33 → **1.00** → 0.25
  - 112 dir 10: 0.47 → **0.94** → 0.46
  - 125 dir 50: 0.24 → **1.00** → 0.28
  - 122 dir 45: 0.27 → **1.00** → 0.31
  - 114 dir 35: 0.37 → **1.00** → 0.37
  - The pattern is the same at 92, 93, 94, 95, 98, 105, 107, 109, 113, 116, 119, 120, 123 and 124, and for 7 days
    at 103, 110 and 115. At 121 it runs from 02-08 to 02-21. Sites 96 and 101 are unaffected; 97 and 104 have no
    data.
- Subtracting restores the direction's normal profile. Weekday means (other hours / 16–19h / 06–09h):

  | Site | Inflated minus other, during | Inflated direction before | Inflated direction after |
  |---|---|---|---|
  | 112 | 38/45/18 | 42/48/25 | 46/50/25 |
  | 122 | 23/9/32 | 22/11/25 | 25/9/29 |
  | 114 | 56/73/54 | 55/71/49 | 62/73/43 |
  | 111 | 9.5/10.8/9.5 | 8.4/10/6.2 | 7.1/5.5/5.4 |
  | 125 (AM only) | 22.5 | 11 | 18 |

  Negative slots after subtracting: 0 at 111, 122 and 114; 1 at 125; 32 of 479 at 112.
- Extra bikes over the fortnight: 111 +129, 112 +859, 125 +286. At other sites: 92 +4136, 98 +1266,
  103 +5468 (7 days), 106 +5108, 107 +3205, 114 +1987, 116 +2646, 121 +5031, 124 +1567.

**Reproduce:**
- `rv.directions([111,112,125,122,114], "2013-02-04", "2013-03-10")`: the `b_covers_a`/`a_covers_b` columns
  read 1.0 in the week of 02-18.
- `rv.daily([111,112,125], "2013-02-04", "2013-03-10", wide=True)`.

**Impact:** the inflated direction is +30% to +150% for weeks 2013-02-11 (Fri–Sun), 02-18 and 02-25. Site totals
rise by 1.2–2×.

**Confidence:** high.

**Recommend:**
- G0111: add `subtract_other` on dir 16, 2013-02-15 00:00 → 2013-03-01 ~14:00, and reject the `uncertain`
  (caveat: dir 15 also ran low that fortnight, 9/day against 18–22).
- G0112: add `subtract_other` on dir 10, same window.
- G0125: replace the `uncertain` with `subtract_other` on dir 50.
- When the older groups are re-reviewed:
  - Replace `missing` with `subtract_other` in G0103, G0105, G0106, G0107, G0109, G0110, G0114, G0116, G0120
    and G0121 (the brief says to recover counts).
  - Add `subtract_other` to G0091, G0092, G0093, G0094, G0095, G0098, G0113, G0115, G0119, G0123 and G0124.
  - Pin the end slot per site (G0122 found 03-01 14:15; low-volume sites cannot pin it).

## F2. G0112 keeps two network-wide week-long outages as zeros

**Verdict (G0112):**
- `uncertain` 2017-05-19 10:45 → 05-26 12:30: "a counter outage or a path closure".
- `uncertain` 2021-03-19 11:00 → 03-26 11:00: "coincide with the March 2021 NSW flood rain".

**Alternative:** both are feed or retrieval outages that hit most TfNSW Metrocount counters at once, and the other
15 groups set them `missing`.

**Evidence:** longest zero run per counter in each window:

| Window | Counters | First zero slot | Last zero slot | Run length |
|---|---|---|---|---|
| 2017-05 | 113, 112, 110, 101, 105, 104, 103, 120, 122, 124, 109, 106, 123, 96, 98 | 2017-05-19 10:15–12:45 | 2017-05-26 11:45–12:45 | 672–683 slots |
| 2021-03 | 93, 91, 109, 94, 114, 122, 103, 95, 92, 105, 112, 106 | 2021-03-19 07:45–11:30 | 2021-03-26 10:45–12:30 | 671–689 slots |

- The 2021 counters include Gore Hill Fwy, Warringah Fwy and Falcon St, nowhere near a river.
- `rv.network`: zero sites go 10 → 28 → 7 across 2017-05-20..25, and 6 → 19 → 5 across 2021-03-20..25.
- Neighbours never reached zero during the floods (G0122 cites site 193 at 128–138 on 03-24/25).

**Reproduce:** `rv.network("2017-05-17","2017-05-28")`, `rv.network("2021-03-17","2021-03-28")`,
`rv.zeros([112,122,124,109])`.

**Impact:** G0112 weekly totals (dir 9 / dir 10) against the neighbouring weeks:
- 2017-05-15: 255/312; 2017-05-22: 169/282 (neighbouring weeks ~450/600).
- 2021-03-15: 235/382; 2021-03-22: 290/649 (neighbouring weeks ~590/970).

That is 40–70% low.

**Confidence:** high.

**Recommend:** replace both G0112 `uncertain` notes with `missing` over the same slot ranges.

## F3. Feed-wide zero days 2025-10-23 and 2025-10-20: groups that miss them

**2025-10-23:**
- 37 Metrocount counters read 0 with 192 warning records each (network: 0–3 zero sites on the days either side).
- G0122, G0158, G0160, G0162, G0163, G0174, G0540 and 30 others set it `missing`.
- Missed:
  - **G0112**, site 112: 0 against 222 and 229 on the days either side.
  - **G0125**, site 125: 0 against 63 and 57.
  - G0091, site 91: re-review.

**2025-10-20:**
- A second zero day hit 25 Metrocount counters, mostly the Parramatta and council units (G0154, G0176–G0208,
  G0273, …). G0190 already treats it as a shared outage.
- Missed:
  - **G0179** (site 179; ref 32/day).
  - **G0191**, site 192 (ref 21).
  - **G0203** (site 203; ref 31).

**Reproduce:** `rv.daily([112,125,122], "2025-10-20", "2025-10-25", wide=True)`,
`rv.network("2025-10-18","2025-10-25")`.

**Impact:**
- 112: about −200 (−12%) in week 2025-10-20.
- 125: about −69 (−15%).
- 179, 192, 203: −20 to −30 each.

**Confidence:** high.

**Recommend:** add a whole-day `missing` on each (site, date) above. Its source should be recorded as
a feed-wide outage.

## F4. 2022-02-19 doubling not handled at G0172

**Evidence:** site 172, dir 101: 38 bikes over 18 non-zero slots, 0 odd, level 2.71. Dir 102: 48 bikes over
16 non-zero slots, 0 odd, level 3.0. Every other Metrocount tube site doubled that day is halved (18 groups).
`rv.doubled` misses 172 because each direction has fewer than 20 non-zero slots (MIN_EVEN_NONZERO), but together
that is 34 all-even slots on the feed-wide day.

**Reproduce:** `rv.daily([172], "2022-02-17", "2022-02-21")` (`odd_slots` = 0 on 02-19).

**Impact:** +43 bikes, about +10% for week 2022-02-14.

**Confidence:** high.

**Recommend:** add `scale 0.5` on site 172, 2022-02-19. Also let `doubled` pool a counter's directions, or report
runs that match a feed-wide day even when they have fewer than 20 slots.

## F5. G0162: the 2025-12-13 step is the GreenWay opening, not a counting change

**Verdict:** `uncertain` from 2025-12-13 (ongoing): "stepped to 2–3× … a counting change cannot be ruled out".
The series is split at 2025-12-13 ("new level", low confidence).

**Alternative:** the Inner West GreenWay, a 6 km path along Hawthorne Canal from the Cooks River to Iron Cove,
opened end to end on Sunday 14 Dec 2025, with new tunnels and underpasses including one under Parramatta Road
([Bicycle Network](https://bicyclenetwork.com.au/newsroom/2025/12/15/sydney-greenway-opens/),
[Inner West Guide](https://www.innerwestguide.com.au/p/greenway-opens-december-2025)).

**Evidence:**
- Site 162 by day: Sat 12-06 219 → Sat 12-13 697 → Sun 12-14 (opening) 2052 → weekdays 12-15..17 at 1126, 1332
  and 1121 (against 440 before).
- Site 160 (1 km away, not on the GreenWay) is unchanged: 898 and 1162 against 852 and 937.
- TfNSW installed new cameras on the "Cooks to Cove Greenway" at Marion St from 2025-12-29 (sites 569–576).
- The reviewer saw normal odd counts, speeds and seasonality, which fits real new riding.

**Reproduce:** `rv.daily([162,160], "2025-12-06", "2025-12-20", wide=True)`, `rv.neighbours(162, cameras=True)`.

**Impact:** no totals change. The split breaks the longest continuous Hawthorne Canal series exactly at a real
infrastructure effect, which is what the data is meant to show.

**Confidence:** high.

**Recommend:** reject the `uncertain` from 2025-12-13, and merge the two "new level" series into the AM- and
PM-peak series (617 AM-heavy and 597 PM-heavy after the Nov 2025 swap, as the verdict already has). Add the
opening to `events.csv`.

Also possible: the 2025-06-19..25 partial drop (`uncertain`) may be GreenWay works on the canal path. I could not
confirm it, so leave it as it is.

## F6. Direction label swaps the series do not follow

Method: for every two-direction piezo or tube counter, I took the workday AM share (06–09h ÷ (06–09h + 16–19h))
of each direction per week, and flagged lasting changes in which direction carries the morning peak. The swaps
handled correctly:

- 106 (2022 reinstall).
- 158 (2023-09-18).
- 161 (2021-11-05).
- 162/148 (2025-11-11).
- 168 (2026-04-23).
- 174 (2022-07-27, 2022-11-08, 2024-10-18).
- 175 (2026-06-09).

Counter replacements at 172, 183, 187, 537, 541, 544, 548, 550, 552 and 559 are all joined by flow. The swaps
that are not followed:

| Group | Swap | Evidence (mean workday bikes per hour, `rv.hourly`) | Recommend | Confidence |
|---|---|---|---|---|
| **G0125** (in scope) | swapped from the 2022-07-04 restart after the 269-day gap (possibly from mid-2021 lockdown) to about 2025-04-14 (no gap there) | 2018–21H1: dir 49 7–8h 0.8/0.7, 16–17h 1.9/1.7; dir 50 1.6/1.3, 0.9/0.9. 2022-07 → 2024: dir 49 2.0/2.4, 1.1/2.0; dir 50 0.9/2.0, 2.3/2.4 (swapped). 2025-05 → 2026-09: dir 49 17h 4.2 vs 2.9, dir 50 8h 2.8 vs 2.2 (original again). Weekly AM-share difference 2012–21 about −0.2; 2022-07 → 2025-04 +0.1 to +0.3; after 2025-04-14 −0.1 to −0.3. TfNSW's site comment for 125 mentions a "setup spacing issue (can fix)", which fits a swap and a later fix without a gap. | dated series parts: NE = 49 until 2021-10, 50 from 2022-07-04 to about 2025-04-13, 49 after; SW the mirror. Re-reviewer to pin the 2025 date. | medium |
| G0109 | swaps at the Mar–Aug 2012 reinstall and at the 2022-05 reinstall | 2019–21H1: dir 12 6–8h 11.2/7.6/4.8, dir 11 5.4/4.5/4.2; 2022-06 → 2026: dir 11 10.4/7.6/5.8, dir 12 4.8/4.3/3.3; 2011H2 as in 2022. | dated series parts | high |
| G0120 | swapped 2011-07 → 2011-12, before the Dec 2011 outage | 2011-07..11: dir 24 7h 9.8 / 17h 6.4, dir 23 3.5/10.7; 2012: dir 24 6.1/12.5, dir 23 9.6/7.8 | dated series parts for 2011 | medium–high |
| G0164 | swapped between the 2022-08-17 and 2022-09-13 restarts | 07-25..08-12: dir 105 8h 35 / 18h 20, dir 106 13/38; 08-18..09-05: dir 105 13/40, dir 106 39/18; 09-14..10-07: back | dated parts 2022-08-17 → 2022-09-06 | high |
| G0107, G0121 | swaps 2018-05 → 2019-12 (107) and 2020-10-21 → 12-03 (121) | the verdicts found them | replace `direction_unreliable` with dated series parts, as G0158, G0162, G0174, G0106, G0161 and G0168 do: the swap is recoverable, so the directional totals need not be flagged unreliable | high (consistency) |

**Impact:** each direction's weekly total carries the other flow for the affected periods. That is 2–3.5 years at
G0125 and G0109; at 125 the volumes are similar, so the totals shift by about ±10–20%, but the peak and direction
meaning is inverted.

Possible but unconfirmed: 105 (G0105) in 2026, where dir 31's AM share fell and dir 32's rose, is gradual and not
a clean swap (low confidence; left out).

## F7. Heavy-rain zero days are handled inconsistently

**Evidence:**
- 2020-02-09 (176 mm): 9 Metrocount sites read 0, and the rest ran at a median 1.3% of usual.
  - Set `missing`: G0091, G0092, G0188, and G0191 for site 191.
  - Kept at 0: G0093, G0094, G0113, G0122, G0189, **G0190** (site 190, 10 m from 191), and G0191 for site 192.
- 2022-07-03 (flooding):
  - Set `missing`: G0169, G0186, and G0191 for site 191.
  - Kept at 0: G0179, G0197, G0200, G0201, G0202, G0203, and G0191 for site 192.
- 2016-06-05 (68 mm): G0092 and G0121 set `missing`; G0112 and G0113 keep the zero.

**Why it matters:** the expected count on such days is 0–5% of usual (190: about 6 bikes), so keeping 0 is nearly
exact. `missing` instead drops the week below 7 complete days, which loses the week or inflates a scaled total.

**Reproduce:** `rv.daily([190,191,210,124], "2020-02-07", "2020-02-14", wide=True)`,
`rv.weather("2020-02-07","2020-02-14")`.

**Impact:** small per week (under 1%), but it changes which weeks count as complete.

**Confidence:** medium.

**Recommend:** keep rain zeros where comparable sites run under about 5% of usual (reject G0191's `missing` on
191 for 2020-02-09 and 2022-07-03, matching G0190). Add this to the brief, or have `rv.network` report the median
level against usual for the day.

## F8. G0112 2021-02-26 11:15 → 03-02 07:30: a local outage kept as zeros

**Verdict:** `uncertain`, "counter outage or a short path closure; no neighbour".

**Evidence:**
- Both directions cut in the same slot and returned together at the morning peak.
- The weather was dry (0–0.2 mm).
- No other Metrocount counter was zero on 02-27 or 03-01.
- The zero weekend days replace 114–136 N / 190–226 S.
- G0122 (2024-02-22) and G0125 (2018-10) set the same pattern `missing`.

**Impact:** weeks 2021-02-22 (249/413 against 389/803 the week before) and 2021-03-01, about −40%.

**Confidence:** medium. A bridge-path closure cannot be excluded, but no source for one was found.

**Recommend:** `missing` over the zero slots.

## F9. G0540: near-zero stretch on 2026-09-01 → 09-03 not covered

**Evidence:**
- Counter 350, both directions:
  - 2026-09-01: nothing from 08:30 to 13:30, normal afternoon.
  - 2026-09-02: 31 bikes (sporadic 1s), against 243–347 on the days around it.
  - 2026-09-03: near zero until 16:15.
- The weather was dry, and 537 and 538 were normal (1782/631 on 09-02).
- The records are "good" status zeros, not warnings. 2026-07-23 midday (7 bikes in 10–15h against about 80) is
  similar.

**Reproduce:** `rv.slots([540], "2026-09-01", "2026-09-03")`.

**Impact:** week 2026-08-31 about −500 of about 1,900 (−25%).

**Confidence:** medium, whether a counter fault or a works closure.

**Recommend:** a re-reviewer should decide between `missing` (fault) and keeping the data (closure). At minimum
record it as `uncertain`.

## F10. G0163 westbound decline: a co-located camera supports a fault from 2026-08-31

**Verdict:** `uncertain` on dir 103 from 2026-07-29 (ongoing).

**Evidence:**
- Camera 324 at Oxford St / York Rd, 0.1 km away, has bicycle-path zones 512 and 516. `rv.neighbours` hides
  cameras by default, so the reviewer never saw them.
- Ratio of 163 westbound to camera zone 516 West (dir 1501): 1.53 in the week of 08-24, then 1.04, 1.01 and 1.04
  from 08-31.
- Ratio of 163 eastbound to zone 516 East (dir 1524): 1.47 → 1.57 → 1.50, steady.
- On 07-29 the site total fell by about 200 (westbound only), which is an undercount, not a reclassification.
- The camera itself dropped about 40% in both directions in late June to July 2026, so it cannot confirm the 07-29
  step.

**Reproduce:** `rv.weekly([163,512,516], "2026-06-01", "2026-09-20", wide=True)`.

**Impact:** westbound −25% to −35% from 2026-07-29, and −45% to −50% from 2026-08-31.

**Confidence:** medium for 08-31 onward, low for 07-29.

**Recommend:** keep the `uncertain`, or set dir 103 `missing` from 2026-08-31 once the service step appears. Make
`rv.neighbours` show cameras whose zone names mention a bicycle path, or default `cameras=True`.

## F11. Decisions that hold up, and alternatives checked

- **G0125 2015-07-29 → 2017-12-01 `missing` ("work-site traffic"):** matches the M4 widening, Parramatta to
  Homebush, which ran from March 2015 until it opened in July 2017 and diverted the M4 cycleway
  ([WestConnex](https://en.wikipedia.org/wiki/WestConnex),
  [TfNSW M4 cycle detour map](https://www.transport.nsw.gov.au/sites/default/files/media/documents/rww/projects/01documents/m4/m4-cycle-detour-map.pdf)).
  The recorded counts are symmetric weekday work-hours traffic, not bikes, so `missing` is right.
- **G0125's other outages** (2011-11 → 2012-03, 2018-10, 2025-09 → 10): local, with neighbours normal.
- **G0111:** the 2016-12-15 → 2019 `missing` (mirrored weekly Friday windows; the only mirrored period in the
  dataset) holds. The low winter-2016 `uncertain` is fair: the ratio to 114 falls from 0.15 to 0.03–0.04 in
  Jun–Jul 2016 and recovers to 0.10 by October, with no step or gap, so it can't be settled.
- **G0122:** all decisions hold. Its 2017-05, 2021-03 and 2025-10-23 `missing` and its `subtract_other` are the
  templates for F1–F3.
- **G0158, G0160, G0174, G0190, G0210:** no uncovered feed-wide day, split anomaly or unexplained low day. My scan
  flagged days where the site was under 35% of usual while the network was above 60%; every one was a public
  holiday or a flood also seen at the adjacent site. G0210 ends on 2025-10-19, before both October 2025 feed days.
- **The TfNSW "MetroCount comments 16/07/21–13/08/21" site note** is attached to 17 sites (91–125). It is an audit
  note, not a fault in that window. G0112's `uncertain` for it is harmless; no other group acted on it, which is
  consistent.

## Changes to the brief and tools

1. **Add a cross-site view of feed events.** For a date range, `rv.network` (or a new `rv.feed_events`) should
   return per day:
   - sites with all-even days;
   - sites where one direction covers the other in every slot;
   - zero sites (by vendor);
   - the median level against usual.

   Reviewers see one group; F1–F4 are all feed-wide and were handled differently per group. This gives search
   methods, not conclusions, so it fits INFORMATION.md.
2. **`rv.doubled`:** pool a counter's directions, or lower MIN_EVEN_NONZERO on days that are all-even network-wide
   (F4).
3. **`rv.directions`:** add a weekly AM-share column per direction (06–09h ÷ (06–09h + 16–19h)) so swaps stand out
   (F6).
4. **`rv.neighbours`:** list bicycle-path camera zones by default (F10).
5. **Brief:** state that a label swap is fixed with dated series parts, not `direction_unreliable` (F6 G0107/G0121),
   and that zero days in heavy rain are kept when comparable sites are near zero (F7).
6. **`events.csv`:** add the GreenWay opening (2025-12-14) and the M4 cycleway closure for the widening
   (2015–2017). These are real-world events, which the file is meant to hold.

## Groups to fix or re-review

- **Current-brief verdicts in scope:**
  - G0111: F1.
  - G0112: F1, F2, F3, F8.
  - G0125: F1, F3, F6.
  - G0162: F5.
  - G0540: F9.
  - G0163: optional, F10.
- **Older verdicts** (fix at re-review):
  - G0172: F4.
  - G0179, G0191, G0203: F3.
  - G0109, G0120, G0164: F6 swaps.
  - G0107, G0121: F6, swap handling.
  - G0191: F7.
  - Every F1 group listed in (a).
  - G0253, G0258: Ecocounter duplicate days.
  - G0256: 2013-08-18.
  - G0404, G0423: VivaCity even days.
- **Being re-reviewed now** (pass to their reviewers):
  - G0091 (2025-10-23; F1).
  - G0098 (F1).
  - G0101 (fine for 2022-02-19; not in the F1 list).
  - G0554, G0561 (Ecocounter duplicate days).
  - G0569, G0577 (March 2026 repeated records).
