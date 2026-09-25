# What reviewers are told

Reviewers (people or agents) review each review group's whole record. What we tell them shapes
what they find, so this file records what they get, what is withheld, and why. Change it
deliberately; the brief itself is `BRIEF` in `src/bikecount/review.py`.

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
  hourly-binned days.
- **The automatic fixes, described mechanically**, because they change `count`, and the `restore`
  action to undo one where it was wrong.
- **TfNSW's own metadata** for the sites, counters and directions, including TfNSW's site comments.
- **Calendar data** (public and school holidays) and `events.csv`, labelled as a hand-curated list.
- **Encouragement to look at the raw 15-minute records** as well as the summaries, because you
  can sometimes learn things from them that summaries don't show.
- **Tool documentation**: function signatures and neutral placeholder examples.

## Withheld

| Withheld | Why |
| --- | --- |
| A checklist of fault types or methods | It is our search strategy; reviewers would find what we would find |
| Earlier verdicts, known cases, code comments, the README | They carry our conclusions about specific sites |
| Earlier decisions in the data | Run a round's reviews before applying its decisions; the review tools hide `direction_unreliable` |

Reviewers are told to use only the review tools and their brief.

## Measured

Leaving information out does not make reviews unbiased by itself, so:

- **Second reviews**: some groups are reviewed twice, independently. Disagreement shows how much a
  decision depends on the reviewer.
- **Comparisons across rounds** that differ only in the information given show how much that
  information moves decisions.
- **Spot checks** of decisions by a person, recorded as `status` in `decisions.csv`.
