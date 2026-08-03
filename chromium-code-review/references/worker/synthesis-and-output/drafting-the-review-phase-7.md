<!-- Generated from ../../synthesis-and-output.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Synthesis And Output

This file is executed by the late-phase worker agents: the
Reconciliation-Builder, the Draft-Writer, and the Synthesis Challenger. The
severity section also binds verification skeptics, whose CONFIRMED verdicts
must name an anchor from the table below. The orchestrator does not load
this file. Artifact shapes live in `references/templates.md`; the
contradiction checklist and Gerrit output rules live in
`references/verification-and-fixes.md`.

## Drafting The Review (Phase 7)

Inputs: `reconciliation.md`, `synthesis/index.md`, assigned
`synthesis/*.md` cards, `context.md`, `pin.md`,
`directives.md`, `ledger/PR.md` (follow-ups),
`gerrit/unresolved-threads.json` (for replies to existing threads), and the
worktree for verbatim quoted lines. Write
`draft-review.md` in the Output Format below and `gerrit-comments.md` under
the Verdict Alignment And Gerrit Output Rules in
`references/verification-and-fixes.md`, then complete the remaining
pre-output gate lines in `reconciliation.md`. Producing review text while a
gate line is blank is the failure mode the gate exists to stop.

### Comprehensive Output Mandate (No-Truncation Guarantee)
To avoid multiple review rounds and ensure exhaustive feedback delivery:
- **Exhaustive coverage:** Every promoted finding and owner question in
  `reconciliation.md` — equivalently, every card in `synthesis/index.md` —
  MUST have one exact `draft-parts/<item>.md` fragment included byte-for-byte
  once in `draft-review.md`; every finding also has one exact
  `gerrit-parts/<item>.md` fragment included byte-for-byte once in
  `gerrit-comments.md`. The measured hashes and paths live in
  `output-coverage.tsv`. The synthesis cards, not raw `verdicts.tsv` rows, are
  the coverage set: a
  CONFIRMED verdict that reconciliation merged into a survivor is represented
  by that survivor, and a severity-downgraded finding remains a promotion at
  its calibrated severity. The validator first proves reconciliation
  promotions/questions
  equal the card index, then proves the card index equals the coverage
  manifest. An item ID in framing prose is not coverage.
- **Zero truncation or sampling:** Never cherry-pick, sample, or compress
  promoted findings into a "top priority" or "representative" subset to reduce
  draft size. Presenting a partial subset causes multiple review iterations
  and violates workflow objectives.
- **Deduplication without omission:** When multiple discovery workers report
  overlapping observations of the exact same root defect, reconciliation
  merges them into one surviving row citing all applicable code locations.
  Never discard a distinct technical defect during merging; a genuinely
  distinct defect keeps its own promoted card and finding.

The Draft Writer reads cards one at a time and does not ingest all verdict or
root-cause files. It writes the exact per-item fragments and measured
`output-coverage.tsv` rows before assembling the final outputs. If a card is
missing required evidence or conflicts with reconciliation, report the gate
failure instead of searching the entire record and silently repairing it.

The single Draft Writer path is allowed only when the card index has at most
12 cards and its assigned artifacts plus required reference sections fit the
agent input budget: at most 35% of a known context window, or 128 KiB when
capacity is unknown. Above either bound, Finding Writers produce one bounded
`draft-parts/<card>.md` plus (for findings) `gerrit-parts/<card>.md` per card,
and a Frame Writer produces `draft-parts/FRAME.md`. Draft Assembly then
combines only those parts
through a bounded tree: each node consumes at most 12 children while remaining
within the same input budget, writes a versioned intermediate, and records its
children, measured bytes, and token estimate in the assembly manifest.
Assembly may order and join framing, but per-item fragment bytes are immutable:
it must never edit, summarize, deduplicate, or omit them. It must never reopen
the corpus or change a claim, severity, origin, fix, question, or citation.
Add levels instead of exceeding a bound. Only the root writes the current
draft/Gerrit outputs and canonical coverage manifest.

With zero cards, the Frame Writer may operate in no-card root mode and write
the complete draft/Gerrit outputs directly; it still consumes context, plan,
pin, directives, and gate state and remains independently challenged. When the
root output exceeds the agent input budget, assembly emits immutable bounded
draft/Gerrit sections plus an index containing their order, byte count,
SHA-256, source cards/rows, and global-frame flag. The root outputs are exact
concatenations of the indexed sections.

Findings come from the reconciliation table's promotions — the draft writer
does not re-adjudicate verdicts. If the record looks contradictory
(a promotion without a CONFIRMED verdict, a verdict without a disposition),
that is a gate failure to report to the orchestrator, not a judgment call
to paper over.

After the synthesis challenge, any changed draft is a new numbered revision.
Archive the prior challenge index, generate fresh challenge shards over the
entire revised draft, and collect them again. Resolving the old issue list is
necessary but not sufficient: no revised draft may proceed to freshness or
delivery without a new contradiction pass.
