<!-- Generated from ../../synthesis-orchestration.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Synthesis Orchestration

Load this file only when Phase 7 becomes runnable. It governs bounded drafting,
challenge rounds, and freshness-safe delivery; worker content rules remain in
`synthesis-and-output.md` and `verification-and-fixes.md`.

## Phase 8 — Synthesis Challenge

Partition the draft and record into shards that fit the same agent input
budget. For a bounded draft requiring only one content/structural shard,
mechanically render the one-row plan/index at `challenge/round-<N>/index.md` (listing reconciliation row tokens `row:<ID>` under `expected coverage`) and spawn the independent challenger
directly; no planner agent is needed. The challenger still writes
an immutable shard artifact; then run `collect-challenge-round.py <review-dir> <round>` to mechanically update `challenge.md` and `challenge/round-<N>/index.md`, before deterministic validation checks it.
For larger inputs, spawn the Synthesis Challenge Planner and one Synthesis
Challenger per shard in capacity-derived waves.

When `draft-sections/index.tsv` exists, a content challenger reads only its
assigned draft/Gerrit sections, exact per-item fragments and coverage rows, the
bounded global frame, and its cards. A
structural challenger reads only its reconciliation-row shard, gate, and frame.
Exactly one `global:consistency` shard reads the frame, ordered section index,
section headings/digests, verdict summary, and Gerrit target index—not every
section body. No challenger receives the complete large draft merely because
it is convenient. Each result records the exact section SHA-256 values it
audited.

Challengers write immutable `challenge/round-<N>/CH*.md` results. Collect the
round by running
`scripts/collect-challenge-round.py <review-dir> <round>` directly — it
finalizes `challenge/round-<N>/index.md` and writes the `challenge.md`
pointer; spawn the Challenge Collector wrapper brief only when the helper
cannot execute. A missing shard is an incomplete round (nonzero exit), never
a pass.

If a shard is missing, repair it. If any issue exists, revise through the same
bounded topology as Phase 7: use a targeted Draft Writer only when the complete
input remains within its bounds; otherwise rerun only affected Finding Writers
or the Frame Writer and reassemble. Then plan and run a new complete challenge
round against the revised artifacts. A revision never inherits an earlier pass.

Allow at most three content-revision cycles. If substantive disputes remain,
preserve them in the immutable round, make one disclosure-only draft revision,
and run a final challenger limited to proving that each dispute is accurately
disclosed and the verdict/gate reflects it. Delivery requires this final
disclosure challenge to pass; it does not declare the disputes resolved.
