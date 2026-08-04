<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## The Review Directory

```
<scratchpad>/cl-9999999-ps3/       # small control/evidence artifacts only
  pin.md                  # patchset pin block (scripts/fetch-cl.sh writes this)
  detail.json             # Gerrit change detail (ALL_REVISIONS)
  comments.json           # published comments; unresolved threads live here
  skill-snapshot/         # immutable SKILL/references/scripts used by this run
  skill-snapshot/snapshot-manifest.json # verified sizes/hashes for the snapshot
  gerrit/unresolved-threads.json # normalized root/latest thread records
  profile.json            # deterministic effort class, signals, hunk map, budgets
  profile.md              # compact human-readable profile summary
  directives.md           # review mode + user directives (orchestrator)
  progress.md             # orchestrator phase log; the resume point
  orchestration.tsv       # structured attempt manifest + resumable queue
  context.md              # Phase 1: bug/design context, scope-relevance notes
  inventory.md            # Phase 1: inventory + risk map (inventory/<shard>.md when sharded)
  indexes/inventory.tsv   # compact derived surface/trigger index
  indexes/topology.tsv    # effective typed evidence graph
  indexes/specialist-priors.tsv # independent generalist risk assessments
  indexes/manifest.json   # source fingerprints for every derived index
  prior-feedback-input.md # Phase 2 input (follow-up reviews only)
  plan.md                 # Phase 3: thread-plan roster with statuses
  briefs/EPW.md           # Phase 3: one brief per spawned thread
  input-manifest.tsv       # exact bounded inputs for every spawned worker
  briefs/V001.md          # Phase 5: one brief per skeptic batch
  mechanical-leads.md     # output of scripts/mechanical-leads.sh
  ledger/EPW.md           # one file per spawned thread
  ledger/AL.md
  ledger/...
  collection.md           # Phase 4.5: collection audit + ORC per-file floor rows
  collection/index.tsv    # exact thread/file ownership for audit shards
  collection/shards/CA001.md # bounded audit shard when collection is sharded
  indexes/candidates.tsv  # compact derived candidate index
  verification/batches.md # Phase 5: candidate→batch map + merge proposals
  verification/planning/index.tsv # planner-shard scopes + reserved V-ID intervals
  verification/planning/VPLAN001.md # immutable planner-shard result
  verification/V001.md    # skeptic verdict rows, one file per batch
  verification/affinity.md # global root families + cross-batch audit
  indexes/verdicts.tsv    # compact derived verdict/trigger index
  root-cause/batches.md   # trigger-to-RC-batch map
  root-cause/planning/index.tsv # planner-shard scopes + reserved RC-ID intervals
  root-cause/planning/RCPLAN001.md # immutable planner-shard result
  root-cause/RC001.md     # root-cause/layering rows, one file per batch
  ledger/reopened/round-1-RC001.md # canonical reopened candidate rows
  reconciliation.md       # reconciliation table + filled pre-output gate
  indexes/reconciliation.tsv # compact derived row/relationship index
  reconciliation/shards/RB001.md # bounded disposition shard when needed
  synthesis/index.md     # bounded synthesis-handoff manifest
  synthesis/EPW-2.md     # bounded evidence card per promoted/question row
  draft-parts/F001.md    # exact review fragment for one finding/question
  gerrit-parts/F001.md   # exact Gerrit fragment for one finding
  output-coverage.tsv    # exact card→draft/Gerrit fragment hashes
  draft-parts/FRAME.md   # large-review summary/plan/notes fragment
  draft-assembly/L01-N001.md # bounded hierarchical assembly node
  draft-sections/index.tsv # large-draft immutable section/digest index
  draft-sections/ISSUES-P1.md # immutable review section fragment
  gerrit-sections/ISSUES-P1.md # matching Gerrit fragment
  draft-review.md         # Phase 7: full review text
  gerrit-comments.md      # Phase 7: Gerrit-ready comments
  challenge/round-1/index.md # immutable challenge-round manifest/result
  challenge/round-1/CH001.md # immutable challenge shard
  challenge.md            # pointer/summary for current challenge round
  delivery-gate.md        # Phase 9: post-challenge freshness/delta result
```

The detached checkout is external and reusable at
`<src-parent>/codereview/worktrees/cl-9999999-ps3/`. It is never nested in,
or symlinked from, the review directory. `pin.md` is the authority for its
absolute path.

Create `skill-snapshot/` once, immediately after the pin, with
`scripts/snapshot-skill.py`. Every `⟨skill-dir⟩` substituted into a brief and
every manifested reference/helper input points into this snapshot. The live
canonical skill checkout is never a worker input and changing it cannot
invalidate in-flight hashes. `--check` verifies the frozen files against their
own manifest by design; it does not compare them with later live-skill edits.

Thread ledger files are append-only records of discovery: later passes never
rewrite them. A row's life-cycle state advances in `verification/V⟨batch⟩.md`
(verdicts) and `reconciliation.md` (dispositions), not by editing the row.
A row, once written, is never deleted or edited, and every row is carried to
synthesis: promoted (at its calibrated severity, including a downgrade),
merged, or dismissed with a one-line recorded reason. Information silently
lost at consolidation time is a common source of incomplete reviews.

### Append-only retry and amendment contract

Every row-bearing artifact and audit artifact becomes append-only after its
producer passes `validate-worker-artifact.py` and the orchestrator collects
that attempt. Before collection, its single assigned producer corrects its own
draft in place and must not return while local validation fails. A continuation
or retry first inspects the collected headings, last complete row, and
amendment tail, then appends only the explicit remaining scope. It must not
regenerate the file or reuse an existing row ID. The
orchestrator assigns a monotonically increasing attempt number in
`orchestration.tsv`; attempts do not alter row IDs. A state transition updates
the existing row for that attempt atomically; `progress.md` preserves the
event history. The TSV never contains two rows for the same
`work_id`/`attempt` pair.

If an earlier row or matrix answer is incomplete or wrong, preserve it and add
an amendment at the end of the same file:

```markdown
## Amendments

| amendment | target | operation | replacement / reason | evidence | attempt |
| --- | --- | --- | --- | --- | --- |
| EPW-A1 | matrix:3 | replace-fields | {"answer":"N/A — Flush has no early returns","evidence":"net/streams/delay_buffer.cc:150-171"} | net/streams/delay_buffer.cc:150-171 | 2 |
| EPW-A2 | EPW-2 | supersede | corrected trace: caller propagates the failure; candidate withdrawn | net/streams/delay_stream.cc:88-94 | 2 |
```

Valid operations are `replace-fields`, `replace`, `supersede`, and
`retract-duplicate` (only when the same attempt emitted an identical row
twice). Use `replace-fields` for any structurally parsed table cell. Its
`replacement / reason` is a non-empty JSON object whose keys exactly match
table headers. Targets are a stable row ID, `matrix:<1-based-row>`,
`descriptor:<candidate>`, `trace:<candidate>:<obligation>`,
`affinity:<candidate>`, `family:<RF-id>`, `audit:<check>`, or
`root-family:<RF-id>`. Indexers,
validators, and collectors all apply these replacements before checking the
effective row. Use the narrative operations only for candidate lifecycle
text. The latest valid amendment for a target is authoritative, but the
original row keeps its reconciliation obligation and its disposition cites
the amendment. If a crash leaves a syntactically truncated final row, the
retry appends a newline, records an amendment identifying the discarded
fragment, and resumes at the next unused ID.

Draft outputs are versioned rather than appended. Before revising
`draft-review.md` or `gerrit-comments.md`, preserve the prior files as
`draft-review.revision-⟨n⟩.md` and `gerrit-comments.revision-⟨n⟩.md`; then write
the new current files and increment the revision recorded in the current
`challenge/round-<N>/index.md`. Challenge shards and evidence cards are
immutable once written. Index files
may be replaced only after their previous revision is archived under the
explicit revision name in their artifact contract.
