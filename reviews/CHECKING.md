# Checking verdicts

Withheld from reviewers, like the rest of reviews/: it names particular sites and what we concluded about them.

## How

For each new verdict, `check.report(group)` (check.py) compares it with the previous one (git HEAD by default):
decisions, the group cleaned under each, full weeks and mean weekly bikes per counter-direction, and flags for the
mistakes below. Look into every flag, every big change, and every fix the old verdict had that the new one drops.
Check a claim against the data (the `rv` tools) before acting on it. Then send the reviewer back with the evidence, or
accept. Reject only what is plainly wrong: a factor fitted to another counter, a decision about provisional days.

## Mistakes reviewers have made

- A camera-wide outage recorded for only the camera's first site (a decision covers only its SITE_SK; the brief now
  says so).
- The provisional last day of the download set missing: later loads add its real counts (the brief now says the last
  days are provisional; clean.py leaves out days on or after a counter's latest load).
- Direction label swaps at tube reinstalls not followed by the series (G0174, G0158); a feed-wide doubled day
  (2022-02-19, most tube and piezo sites) not halved. Earlier verdicts had both.
- Whole zones set missing for phantom bursts that slot-range `missing` could remove (G0374).
- `scale` 1.2 fitted to a co-located tube (G0101, Harbour Bridge misclassification 2018-21): replaced by `missing`.
- Single-group blindness: events shared by many counters (feed outages, vendor-wide camera detection changes, the Feb
  2013 direction fault) handled differently from group to group. Only the cross-group audits catch these.

Independent reviews can disagree on joining counters (G0542): check the step against counters that ran through both
periods. Reviewers used 74k-113k tokens per single-counter group and 145k-220k per camera group; batching small groups
might save the fixed overhead but costs independence, so far one group per reviewer.

## Rounds

- 2026-09-27, round 1 (14 groups: G0158 G0160 G0162 G0163 G0174 G0314 G0338 G0347 G0360 G0374 G0384 G0445 G0493
  G0512) and round 2 (20: G0091 G0092 G0098 G0101 G0428 G0456 G0464 G0541 G0544 G0545 G0547 G0549 G0550 G0551 G0552
  G0554 G0560 G0561 G0569 G0577). With the 10 re-reviewed earlier that day, 44 of 153 groups are under the current
  brief. The other 109 have older verdicts, many carrying decisions converted from former automatic rules.
- 2026-09-27, cross-group audits: reviews/audits/2026-09-27/ (cameras, City of Sydney piezos, TfNSW tubes and piezos,
  the cleaned output).

## Pending (from the 2026-09-27 audits, not yet applied)

Verdict fixes (each report has the evidence):
- G0111, G0112, G0125 (reviewers not resumable: re-review): the Feb 2013 direction fault (2013-02-15 to 03-01, 25
  Metrocount piezos; `subtract_other` restores it at 122 but not at 111 or 125, so decide per site); feed-wide outages
  kept as zeros (2017-05-19..26, 2021-03-19..26, 2025-10-23); G0125's label swap from 2022-07-04 to about 2025-04.
- G0389, G0290 (re-review): camera detection steps (G0389 at 2024-11-07; the 2023-11-10 outage was not rain) and
  G0290's zone level changes at restarts (2022-11-08, 2023-05-14, 2023-07-12).
- G0360 (split series at 2024-11-07), G0445 (split at 2024-10-02; first day missing), G0338 and G0374 (the 2023-11-12/13
  camera outage), G0162 (the 2025-12-13 step is the Inner West GreenWay opening, so un-split), G0464 (May-Aug 2024
  detection loss: `uncertain` plus a split), G0569 (an unmatched 1640-bike burst at 574 kept where other groups set
  such bursts missing).
- Older verdicts with the same issues, for their re-review: G0172 (2022-02-19), G0179, G0191, G0203 (2025-10-20
  feed-wide zero day), G0109, G0120, G0164 (label swaps), G0107, G0121 (swaps flagged instead of followed), G0432 (an
  all-even zone not halved), G0274 (restart steps), G0256.

Tools: reviewers cannot see events shared by many counters. Proposed: extend `rv.network` to count, per day and
technology, the counters at zero, all-even, or stepping in level; pool `rv.doubled` across directions (it misses
2022-02-19 at low-volume sites); show cameras in `rv.neighbours`; add each direction's share of the morning peak to
`rv.directions`.

City of Sydney 2025 Ecocounter-to-Metrocount joins: the audit calls the step real growth and recommends joining within
about ±15% against counters that were never replaced; a quick check put the replaced sites (+19-42%) at the top of the
never-replaced range (+4-41%, median +10%). Left as reviewers chose (joined: G0541 G0542 G0550; separate: G0544 G0545
G0549 G0551 G0552 G0554 G0560 G0561) until decided.
