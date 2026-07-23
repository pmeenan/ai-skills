# Synthesis Orchestration

Load this file only when Phase 7 becomes runnable. It governs bounded drafting,
challenge rounds, and freshness-safe delivery; worker content rules remain in
`synthesis-and-output.md` and `verification-and-fixes.md`.

## Contents

- [Phase 7 — Draft Review](#phase-7--draft-review)
- [Phase 8 — Synthesis Challenge](#phase-8--synthesis-challenge)
- [Phase 9 — Delivery](#phase-9--delivery)

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
`gerrit-comments.md` per `synthesis-and-output.md`. Keep the post-synthesis
freshness gate explicitly `pending-delivery`.

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

## Phase 8 — Synthesis Challenge

Partition the draft and record into shards that fit the same agent input
budget. For a bounded draft requiring only one content/structural shard,
mechanically render the one-row plan/index and spawn the independent challenger
directly; no planner or collector agent is needed. The challenger still writes
an immutable shard artifact; the orchestrator mechanically finalizes the
one-row index from that artifact/status, then deterministic validation checks it.
For larger inputs, spawn the Synthesis Challenge Planner and one Synthesis
Challenger per shard in capacity-derived waves.

When `draft-sections/index.tsv` exists, a content challenger reads only its
assigned draft/Gerrit sections, the bounded global frame, and its cards. A
structural challenger reads only its reconciliation-row shard, gate, and frame.
Exactly one `global:consistency` shard reads the frame, ordered section index,
section headings/digests, verdict summary, and Gerrit target index—not every
section body. No challenger receives the complete large draft merely because
it is convenient. Each result records the exact section SHA-256 values it
audited.

The collector writes immutable `challenge/round-<N>/CH*.md` results and
`challenge/round-<N>/index.md`; `challenge.md` points to the current complete
round. A missing shard is an incomplete round, never a pass.

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

## Phase 9 — Delivery

Refresh Gerrit detail into a temporary file, strip the XSSI prefix, and extract
only current patchset number, revision SHA, and updated timestamp. Write those
scalars to `delivery-gate.md`. Do not read bulk JSON into orchestrator context.
The Delivery Gate Finalizer may update only the Freshness line in
`reconciliation.md`; it never changes findings or dispositions. Regenerate
the derived indexes after that mutation so final validation cannot accept a
pre-delivery reconciliation fingerprint.

- Historical mode: verify the pinned SHA still maps to the selected patchset
  in `ALL_REVISIONS`; record `historical pin verified` and current PS context.
  Do not chase or delta-review the current patchset.
- Current SHA unchanged: record `current` with the check timestamp.
- Newer non-historical patchset: spawn the Patchset-Delta Inspector against
  the exact old/new SHAs. A trivial result must revalidate every cited line and
  conclusion and record exact PS/SHA pairs in `patchset-delta.md`; then run a
  metadata-only revision through the current bounded drafting topology (Draft
  Writer, or Frame Writer plus root reassembly) and a fresh Phase 8 challenge.
  A repeated refresh may record `trivial delta verified` only if Gerrit still
  equals the inspected new PS/SHA.
- Material delta: stop without delivering. Release the superseded pin's lease,
  then run `fetch-cl.sh` with a new sibling review directory for the new
  patchset, copy only user-authored directives, reference
  the immutable old review and delta as prior-feedback input, initialize a new
  manifest, and restart at Phase 1. Never mutate the old pin or reuse its
  ledgers or verdicts for a new SHA.

Repeat freshness after every revision or restart. State the exact reviewed base
PS/SHA and any separately inspected trivial-delta PS/SHA in the draft.

Run `scripts/validate-review-dir.py <review-dir> --phase final
--require-active-lease`. Only after it
passes, the latest draft has a passing challenge, and `delivery-gate.md` is
affirmative may the orchestrator read `draft-review.md`, `gerrit-comments.md`,
and `delivery-gate.md` for delivery. Limit the final check to formatting and
verdict/finding consistency; route content changes back through Phase 8.

After final artifacts are read, run `scripts/worktree-lease.py release
<review-dir> "review complete"` for every pin owned by the review. This is the
last mandatory gate before sending the final response: every release must
succeed. The command atomically removes the active `cl-<CL>-ps<PS>.log` path;
the `.released-*` file is inactive audit history. If any release fails, do not
claim the review is complete—report the cleanup failure and active path. Leave
clean cached worktrees in place; later invocations remove released or expired
entries. Preserve review directories and manifests as the audit trail.
