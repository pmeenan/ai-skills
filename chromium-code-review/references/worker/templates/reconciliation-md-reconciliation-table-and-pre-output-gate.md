<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## reconciliation.md — Reconciliation Table And Pre-Output Gate

One line per row ID, enumerated from the files (`ledger/*.md`,
`collection.md`, `verification/*.md`, `root-cause/*.md`) — never from a
summary of them. No ranges, no "rest dismissed": a row without its own line
blocks output. A stale manifest fingerprint blocks planning.

First regenerate `indexes/reconciliation.tsv` mechanically from defining
rows/headings, never incidental ID mentions. Its manifest fingerprints every
canonical source. Include relationship edges so rows that require joint
judgment stay together:

```tsv
row	kind	source	effective_amendment	links	disposition_state
EPW-2	candidate	ledger/EPW.md	-	V001-1,AL-1,RC001-1	pending
V001-1	verdict	verification/V001.md	-	EPW-2,RC001-1	pending
RC001-1	root-cause	root-cause/RC001.md	-	EPW-2,V001-1,R1-RC001-1	pending
```

When the relationship closures plus compact control inputs fit within
`worker_input_budget_bytes`, one Reconciliation Builder may own them. When
they do not, partition whole relationship closures into
`reconciliation/shards/RB<batch>.scope.tsv`; never split a merge survivor,
candidate/verdict pair, root-cause parent, or reopened-parent chain merely to
hit a target. A closure that alone exceeds budget gets a dedicated shard with
attempt-numbered continuations.

Each shard writes immutable disposition rows to
`reconciliation/shards/RB<batch>.md` and evidence cards only for its promoted
findings/questions. A deterministic collector rejects duplicate, missing, or
foreign row IDs; concatenates dispositions in stable definition-index order;
builds `synthesis/index.md` from the cards; and proves exact one-to-one row and
card coverage. It does not revise dispositions. A separate bounded gate shard
fills the global pre-output checklist from compact counts. `reconciliation.md`
exists only after all shards and the gate pass exact collection.

```markdown
# Reconciliation — CL 9999999 PS3

| row | thread | disposition |
| --- | --- | --- |
| EPW-1 | Error-Path Walk | refuted (V002-1: guard delay_buffer.cc:96) |
| EPW-2 | Error-Path Walk | promoted → F001 (P1, V001-1, RC001-1) |
| AL-1 | Async And Lifecycle | merged → EPW-2 |
| AL-2 | Async And Lifecycle | refuted (V002-2: timer stopped in Abort, delay_buffer.cc:97) |
| AL-3 | Async And Lifecycle | question → Q002 (V002-3: UNPROVEN) |
| ML-1 | Mechanical Leads | promoted → F003 (P3 non-ASCII em dash in comment) |
| ML-2 | Mechanical Leads | dismissed: intentional sentinel, values agree (V003-2 citation) |
| ORC-1 | Collection audit | clean (cited) |
| RC001-1 | Root-cause challenger | supports F001; reopened R1-RC001-1 |
| R1-RC001-1 | Reopened round 1 | refuted (V004-1; guard other_delay_stream.cc:88) |
```

Every `merged → <survivor-row-id>` disposition has exactly one structured
equivalence row:

```markdown
## Merge equivalence

| merged row | survivor | trigger equivalence | invariant equivalence | outcome equivalence | survivor verdict |
| --- | --- | --- | --- | --- | --- |
| AL-1 | EPW-2 | same timer-after-write-failure sequence at delay_buffer.cc:180-203 | same completion-result invariant at verification/affinity.md:/root-families/RF001 | same false-success/offset-advance outcome at delay_stream.cc:88 | V001-1 CONFIRMED |
```

The three equivalence cells each carry code or artifact evidence; an artifact
pointer is review-relative and its file must exist and be nonempty. A shared
location or fix alone is insufficient. The survivor is a direct,
verdict-owning row rather than another merge, and its reconciliation
disposition agrees with that verdict (`promoted` for CONFIRMED, `question` for
UNPROVEN, `refuted` for REFUTED).

The default is one promoted finding per root family. If a family truly has
multiple independently actionable owners or bad outcomes, add:

```markdown
## Root-family promotion exceptions

| root family | justification | evidence |
| --- | --- | --- |
| RF007 | two independent owners and fixes: parser validation versus storage rollback | parser.cc:88; store.cc:141 |
```

Without this cited exception, multiple promoted findings from the same family
fail the reconciliation gate.

The gate is filled at the bottom of the same file; the canonical checklist
lives in `references/synthesis-and-output.md` (Pre-Output Gate). Filled
lines look like:

```markdown
## Pre-output gate

1. Pin: yes — pin.md; review states PS3 / 4f2a09c1.
2. Freshness: pending-delivery — Phase 9 refresh occurs only after the final
   challenge; final delivery is blocked until delivery-gate.md passes.
3. Roster: yes — plan.md has all 30 entries; 9 not-applicable with trigger-evidence IDs; 0 unreviewed.
4. Collection: yes — 21 spawned, 21 ledger files present.
...
```
