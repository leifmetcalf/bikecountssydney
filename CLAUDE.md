# bikecountssydney

If you are a count-reviewer agent, follow your brief; the rest of this file is for the agent running the pipeline.

The repo produces one thing: a cleaned view of the TfNSW 15-minute cycling counts, used only by agents. Keep it
minimal: no README, CLI or plots, and document code in module docstrings (download.py, clean.py, review.py, check.py,
powerbi.py). The review loop (review.py, check.py, reviews/, the count-reviewer agent) is part of cleaning, not an
extra: the cleaned view is only as good as the verdicts, and a verdict covers the data up to its review, so new data
and changes to the fixes need re-review.

## Running

    uv run download.py   # fetch new counts into data/raw
    uv run clean.py      # data/clean, from data/raw and reviews/verdicts (~2 minutes)

The machine has 29 GB and this data OOMs it easily; an OOM kills the whole session and every agent with it. Run any
heavy Python under a cap, e.g.

    systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 --quiet uv run python - <<'EOF' ... EOF

(clean.py peaks around 1.5 GB: give it 6G). Scan the raw files (125M records) only lazily, with filters and
`collect(engine="streaming")`. Run about 5 agents at a time; give ad-hoc agents that write their own queries a 2G cap.

## Version control

jj-colocated: git HEAD is detached and `master` is a jj bookmark. Commit messages are always just `_` (no body, no
trailer). Commit and push only when asked:

    jj commit -m _ && jj bookmark set master -r @- && jj git push --bookmark master

## A review round

1. Pick groups (`clean.groups()`); verdicts with a `tools` key were written under the current brief.
2. `review.write_brief(group)` for each, and launch one count-reviewer agent per group whose whole prompt is the
   brief's path: nothing else, so nothing steers it. Keep about 5 running.
3. Check every verdict as it arrives with `check.report(group)` and reviews/CHECKING.md. Send the reviewer back with
   the evidence (SendMessage to its agent id) rather than editing its verdict; mark only plainly wrong decisions
   `"rejected": true` with a `"rejection"` reason.
4. `uv run clean.py`, then commit and push.

Reviewers see only their brief and the review tools. Conclusions about particular sites, dates or events belong in
reviews/ (verdicts, INFORMATION.md, CHECKING.md, audits/), which reviewers are told not to read; never in the brief,
review.py or this file. Change what reviewers are told deliberately, and record it in reviews/INFORMATION.md.

Keep actions expressive rather than restricted: `scale` takes any factor because an unprincipled factor is a smell for
checkers to catch, not something to block in code.
