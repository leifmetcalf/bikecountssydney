# What reviewers are told

Reviewers (people or agents) review each review group's whole record. What we tell them shapes
what they find, so this file records what they get, what is withheld, and why. Change it
deliberately; the brief itself is `BRIEF` in `review.py`.

**Aim:** give reviewers facts about the instruments and the data, and the purpose of the review,
and withhold our hypotheses and our knowledge of particular cases, so that decisions come from
the data.

## Given

- **The purpose**: the data is used mainly for weekly totals per series, so problems that change a
  week's total matter most. This tells reviewers what matters, not what to find.
- **What a series is, and the task of defining them** where a site has several counters: reviewers
  are told to decide from the data which directions of different counters carry the same flow, and
  to keep counters apart when they cannot tell whether they read comparably. They are not told that
  TfNSW's direction labels are sometimes inconsistent; the instruction to use the data covers it.
- **How the counters work**: piezo strips, pneumatic tubes, multi-channel units and intersection
  cameras (zones, IN/OUT directions). Reviewers need this to tell a fault from real behaviour.
- **What the data means**: slots, records, `raw` vs `count`, status codes, local clock time,
  hourly-binned days, and that the last few days are provisional (TfNSW loads a day's counts over the
  following days). Added after a reviewer set the last day's not-yet-delivered slots missing, which would
  erase their counts once they arrive.
- **A way to mark an ongoing fault** (`end` null), which also covers data downloaded after the review.
- **The data as published**, with nothing fixed (only VivaCity's UTC times are moved to Sydney time,
  so that every decision's times mean Sydney time). Every fix is a reviewer's decision.
- **Tools that list candidates for common faults** (`zeros`, `doubled`, `duplicates`, `spikes`,
  `absent_zeros`) and that compare sites, directions and the whole network (`compare`, `directions`,
  `counter_days`, `network`), and that a stopped counter may keep reporting zeros. Revised from
  reviewers' feedback in their verdicts' `tools`. These were automatic rules;
  reviewers overruled them hundreds of times, so the rules now only point and reviewers decide. This
  gives reviewers our search methods, though not our conclusions about particular sites.
- **Principled fixes only**: every fix must follow from how the counts went wrong (counted twice:
  scale by 0.5), never from making a counter agree with its neighbours or its past. `scale` takes any
  factor, so this rule is what stops it becoming a calibration knob; checkers reject decisions that
  break it.
- **A fixed list of actions**, and a way to propose new ones (`proposals` in the verdict). Giving-up
  actions (`missing`) must say why the counts cannot be recovered, so that a missing action is not a
  reason to discard data.
- **TfNSW's own metadata** for the sites, counters and directions, including TfNSW's site comments.
- **Calendar data** (public and school holidays), **daily weather** in central Sydney (BOM rain and maximum
  temperature, added after reviewers asked for it to judge low days), and `events.csv`, labelled as a
  hand-curated list.
- **A default of trusting the data**: a fault needs a good explanation that the data bears out
  (the example given is even counts at twice the usual level, which `doubled` looks for); small
  spikes and dips are plausibly noise or real riding. Added after the
  first round, where reviewers removed single unusual slots, including a group ride that a nearby
  counter confirmed.
- **Encouragement to look at the raw 15-minute records** as well as the summaries, because you
  can sometimes learn things from them that summaries don't show.
- **Tool documentation**: function signatures and neutral placeholder examples.

## Withheld

| Withheld | Why |
| --- | --- |
| Earlier verdicts, known cases, code comments, the README | They carry our conclusions about specific sites |
| Earlier decisions | The review tools read the raw records only, so earlier decisions never show |

Reviewers are told to use only the review tools and their brief.

## Measured

Leaving information out does not make reviews unbiased by itself, so:

- **Second reviews**: some groups are reviewed twice, independently. Disagreement shows how much a
  decision depends on the reviewer.
- **Comparisons across rounds** that differ only in the information given show how much that
  information moves decisions.
- **Spot checks** of decisions by a person; a decision found wrong is marked `"rejected": true` in its verdict.
- **Cross-group audits** (`reviews/audits/`): agents that read the verdicts and the data of many groups at once,
  looking for shared causes (feed- or vendor-wide events), inconsistent treatment and faults no decision covers.
  They carry conclusions about particular sites, so reviewers never see them.
