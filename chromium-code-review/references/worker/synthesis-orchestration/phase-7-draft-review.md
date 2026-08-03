<!-- Generated from ../../synthesis-orchestration.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Synthesis Orchestration

Load this file only when Phase 7 becomes runnable. It governs bounded drafting,
challenge rounds, and freshness-safe delivery; worker content rules remain in
`synthesis-and-output.md` and `verification-and-fixes.md`.

## Phase 7 — Draft Review

First set an **agent input budget**. If the harness exposes context capacity,
the assigned artifacts plus required reference sections may consume at most
35% of it, using a tokenizer when available and a conservative four-bytes-per-
token estimate otherwise. If capacity is unknown, cap assigned artifact input
at 128 KiB. Always leave the rest for source inspection, tool output, reasoning,
and the deliverable. A partial/continuation handoff is preferable to crossing
the budget.

Select the drafting topology from `synthesis/index.md` under that budget:

- With no cards, spawn one Frame Writer in no-card root mode; it writes the
  complete no-findings/question draft and Gerrit output directly.
- With at most 12 cards whose aggregate assigned input fits the agent budget,
  spawn one Draft Writer.
- Above either bound: spawn one Finding Writer per card and one Frame Writer,
  then spawn Draft Assembly over those parts. Assemble hierarchically by
  severity/section so each node receives at most 12 inputs and stays within
  the agent budget. The root assembly must include `FRAME.md`. Record every
  node and its measured bytes/token estimate in `draft-assembly/manifest.md`.

Finding Writers never read unrelated cards. Assembly never reopens ledgers,
verdicts, or source traces. Use the briefs in `phase-briefs.md`.

The writer reads `reconciliation.md`, `synthesis/index.md`, only its assigned
cards or parts, `context.md`, `pin.md`, `gerrit/unresolved-threads.json`, and
the worktree for verbatim source lines. It writes `draft-review.md` and
`gerrit-comments.md` per `synthesis-and-output.md`, plus exact per-item
`draft-parts/`/`gerrit-parts/` fragments and measured
`output-coverage.tsv`. Every synthesis item has one draft fragment; every
finding has one Gerrit fragment; their bytes occur exactly once in the
corresponding root output. Keep the post-synthesis freshness gate explicitly
`pending-delivery`.

Collect only finding counts by severity, the verdict line, and whether every
non-freshness gate line is answered. Repair any `no` line through a targeted
writer task.

For a root draft larger than the agent budget, assembly also writes immutable
`draft-sections/<section-ID>.md` and `gerrit-sections/<section-ID>.md` fragments
plus `draft-sections/index.tsv`. Each index row records draft revision, numeric
order, section ID/type, separate draft and Gerrit paths/bytes/SHA-256 values,
card IDs, reconciliation row IDs, and whether the section is global framing.
`draft-review.md` and
`gerrit-comments.md` are exact ordered concatenations of those indexed
fragments. The section index is the large-draft challenge input.
