# Phase Briefs

Orchestrator-facing: this file and SKILL.md are the only skill files the
orchestrator loads. Each brief below is spawned as one fresh-context
subagent. Copy the brief, substitute every `⟨placeholder⟩` (all paths
absolute — subagents start cold in the repository checkout), prepend the
Common Header, and spawn. Do not paraphrase briefs or compose them freehand,
and do not inline reference-file content into them.

Discovery-thread and skeptic briefs are NOT here — the Planner and
Verification-Planner agents write those into `⟨review-dir⟩/briefs/`, and the
orchestrator spawns them with only: "Read and execute the brief at
⟨absolute brief path⟩. It defines your pin, scope, procedure, deliverable,
and rules."

## Common Header

Prepend to every brief below:

```text
You are one phase agent of an orchestrated Chromium CL review. Execute
exactly the procedure below.

Pin: CL ⟨CL⟩, patchset ⟨PS⟩, revision ⟨sha⟩, parent ⟨parent-sha⟩.
Review directory: ⟨review-dir⟩
Read-only worktree: ⟨review-dir⟩/worktree — verify first that
`git -C ⟨review-dir⟩/worktree rev-parse HEAD` matches the revision.
Diff: git -C ⟨review-dir⟩/worktree diff ⟨parent-sha⟩ ⟨sha⟩
User directives: read ⟨review-dir⟩/directives.md first and honor it.

You are read-only outside your named deliverable files: never modify the
worktree, the repository, or another agent's artifacts. Your final message
is a status line only — counts and file paths, no analysis, no prose
summary of your findings. If the harness denies you file access, return
your deliverable's full content in the final message instead — never
summarized.

Extract, don't ingest: when you need only rows, sections, IDs, or fields
from a large input file, pull them mechanically (grep/sed/jq/awk) instead
of reading the whole file — ledger files' "## Candidate rows" sections,
row-ID columns, unresolved threads in comments.json. Read full files only
when your procedure genuinely needs their full text.

If your remaining work will not fit in your context, do not thin it out to
finish: complete what you can at full rigor, write it to your deliverable,
and return "partial — remaining: ⟨explicit list of unprocessed scope⟩" so
the orchestrator can spawn a continuation. A silently shallow pass is a
measured failure mode; a disclosed partial is a normal handoff.
```

## Brief — Context And Inventory (Phase 1)

```text
Scope: the full diff (or, if sharded, only these files: ⟨file list⟩ — then
write inventory/⟨SHARD⟩.md instead of inventory.md, and skip context.md,
which the unsharded context agent owns).

Procedure: read
⟨skill-dir⟩/references/inventory-and-planning.md — the "Gather Context" and
"Pass 1" sections — and execute them against the pinned diff. Read the CL
description from ⟨review-dir⟩/pin.md; follow public bug links and design
docs it references. Bound external ingestion: distill each bug or design
doc into context.md rather than carrying its full text — for long bug
threads read the description plus the comments that state intent, scope
decisions, or repro details (skip CI/bot chatter); for large design docs
extract the sections the CL implements. Record what you skimmed vs read
fully so the draft writer can caveat bug-alignment claims.

Deliverables:
- ⟨review-dir⟩/context.md — bug summary and alignment, description-vs-code
  discrepancies, scope-relevance notes.
- ⟨review-dir⟩/inventory.md — changed-surface inventory and risk-area map,
  in the shapes from ⟨skill-dir⟩/references/templates.md.

Return: one line — risk areas found, changed-file count, surface count,
and the deliverable paths.
```

## Brief — Prior Feedback (Phase 2, follow-up reviews only)

```text
Scope: reconcile prior review feedback against the pinned patchset.

Inputs: ⟨review-dir⟩/prior-feedback-input.md (the prior review text),
⟨review-dir⟩/comments.json (extract the unresolved threads with jq —
e.g. filter entries where the last message has unresolved==true — rather
than reading the file whole; it can be enormous on long reviews),
⟨review-dir⟩/detail.json (extract prior patchset SHAs via jq from
ALL_REVISIONS; do not read it whole).

Procedure: read
⟨skill-dir⟩/references/inventory-and-planning.md — the "Pass 2" section —
and execute it. If you need a file-level diff against the prior reviewed
patchset ⟨prior-PS⟩, materialize it in a second detached worktree under
⟨review-dir⟩/ (never FETCH_HEAD, never the pinned worktree), and remove it
when done.

Deliverable: ⟨review-dir⟩/ledger/PR.md — one PR-⟨n⟩ row per prior finding
and per unresolved Gerrit thread, in the ledger shape from
⟨skill-dir⟩/references/templates.md.

Return: one line — counts by resolution (fixed / partial / open / obsolete
/ superseded) and the file path.
```

## Brief — Planner (Phase 3)

```text
Scope: build the complete thread plan and write every discovery brief.

Inputs: ⟨review-dir⟩/pin.md, ⟨review-dir⟩/directives.md,
⟨review-dir⟩/context.md, ⟨review-dir⟩/inventory.md (or inventory/*.md).

Procedure: read
⟨skill-dir⟩/references/inventory-and-planning.md — "Pass 3", "The Roster",
"Plan-Construction Rules", and "Writing Discovery Briefs" — and execute
them. Read the Context Rules and every recipe trigger line in
⟨skill-dir⟩/references/deep-dive-recipes.md and skim the matched sections
of ⟨skill-dir⟩/references/discovery-checklists.md before deciding statuses.

Deliverables:
- ⟨review-dir⟩/plan.md — the full roster, one row per entry (or shard),
  status spawn / not triggered: ⟨reason⟩, priority batch assignments, in
  the shape from ⟨skill-dir⟩/references/templates.md.
- ⟨review-dir⟩/briefs/⟨THREAD⟩.md — one self-contained brief per spawn
  row, absolute paths throughout, skill dir ⟨skill-dir⟩, review dir
  ⟨review-dir⟩, mechanical-leads script
  ⟨skill-dir⟩/scripts/mechanical-leads.sh.

Return: the spawn list only — one line per thread: name, brief path,
batch number — plus the not-triggered count.
```

## Brief — Collection Audit (Phase 4.5)

```text
Scope: audit discovery collection; do not re-review the CL.

Inputs: ⟨review-dir⟩/plan.md, ⟨review-dir⟩/ledger/*.md,
⟨review-dir⟩/pin.md (changed-file list), ⟨review-dir⟩/briefs/*.md.
Work ledger-by-ledger and lean on mechanical extraction — blank or
citation-free matrix cells, rows missing a `path:line`, and the per-file
location column are all greppable; read a ledger's full text only when a
mechanical hit needs judgment. For the per-file floor, extract every
location column across all ledgers and diff that set against pin.md's file
list instead of holding all ledgers in context.

Procedure and checks:
1. Every plan row with status spawn has a ledger file whose compliance
   matrix covers its brief's scope, with no blank rows and no
   citation-free PASS — an answer without a path:line citation is
   unanswered.
2. Any anomaly recorded inside a matrix answer (success-shaped return
   after failure cleanup, duplicated cleanup, skipped check, unawaited
   write) has a corresponding candidate row; if a thread adjudicated one
   benign inline without a row, flag it as a gap.
3. Per-file floor: every changed file in pin.md has at least one ledger
   row. For files with none, read the file's diff yourself and append an
   explicit ORC-⟨n⟩ clean-or-candidate row to ⟨review-dir⟩/collection.md
   in the Per-File Floor shape from
   ⟨skill-dir⟩/references/templates.md — never a silent omission.

Deliverable: ⟨review-dir⟩/collection.md — audit verdict per thread, your
ORC rows, and a gap list (thread to respawn, or the matrix rows to send
back).

Return: one line — "complete" or the gap list, plus ORC row count and the
file path.
```

## Brief — Verification Planner (Phase 5)

```text
Scope: plan verification; do not issue verdicts yourself.

Inputs: the "## Candidate rows" sections of ⟨review-dir⟩/ledger/*.md —
extract them (e.g. `sed -n '/## Candidate rows/,$p'` per file) rather than
reading whole ledgers; the compliance matrices are not your input —
⟨review-dir⟩/collection.md, and ⟨review-dir⟩/plan.md.

Procedure: read
⟨skill-dir⟩/references/verification-and-fixes.md — "Verifying Candidate
Findings" and "Skeptic Verdicts" — then:
1. Identify duplicate candidate rows across threads; record proposed
   merges as dispositions ("AL-1 merge-into EPW-2: same defect, duplicate
   evidence") in verification/batches.md. Never delete or edit a row.
2. Group every remaining candidate into skeptic batches, sized by trace
   cost rather than row count: a serious candidate whose refutation needs
   caller sweeps or interleaving analysis gets its own batch (or shares
   with 1–2 closely related rows); mid-weight candidates ~3–5 per batch;
   only cheap/cosmetic rows (naming, punctuation, description nits) go up
   to the ~8-row cap. Every candidate row from every thread appears in
   exactly one batch or one merge line.
3. Write one skeptic brief per batch to ⟨review-dir⟩/briefs/V⟨batch⟩.md
   in the Verification Skeptic shape from
   ⟨skill-dir⟩/references/templates.md, with the batch's full candidate
   rows inline, verdict IDs V⟨batch⟩-⟨n⟩, deliverable file
   ⟨review-dir⟩/verification/V⟨batch⟩.md, and the anchor-table reference
   pointing at ⟨skill-dir⟩/references/synthesis-and-output.md.

Deliverables: ⟨review-dir⟩/verification/batches.md and the briefs.

Return: the batch list only — batch id, brief path, candidate count — plus
the merge-proposal count.
```

## Brief — Root-Cause Challenger (Phase 5.5, one per batch)

```text
Scope: root-cause, layering, and fix optimality for batch RC⟨batch⟩ ONLY —
these candidates and their proposed fixes: ⟨row IDs, e.g. EPW-2/V1-1,
AL-4/V2-2⟩. Other batches' candidates are context, not work items.

Inputs: the listed verdict rows in ⟨review-dir⟩/verification/*.md, the
candidate rows they reference in ⟨review-dir⟩/ledger/*.md, and
⟨review-dir⟩/context.md.

Procedure: read
⟨skill-dir⟩/references/verification-and-fixes.md and execute only the
"Root-Cause, Layering, And Fix Optimality" section, fully — every layer
walk and drill — for each candidate in your batch.

Deliverables:
- ⟨review-dir⟩/root-cause/RC⟨batch⟩.md — RC⟨batch⟩-⟨n⟩ rows in the shape
  from ⟨skill-dir⟩/references/templates.md: better-owner hypotheses,
  callsite gaps, duplicated-state risks, stale-fix risks, and
  refutations, each with path:line evidence.
- If your pass opens new candidate rows: record them in your RC file
  flagged needs-verification, and write a skeptic brief for them to
  ⟨review-dir⟩/briefs/VRC⟨batch⟩.md (verdict IDs VRC⟨batch⟩-⟨n⟩,
  deliverable ⟨review-dir⟩/verification/VRC⟨batch⟩.md), same shape as
  other skeptic briefs.

Return: one line — candidates checked, RC rows written, rows reopened
(and the VRC brief path if any), file paths.
```

## Brief — Reconciliation Builder (Phase 6)

```text
Scope: build the reconciliation table; do not draft review text.

Inputs: every row-bearing file — ⟨review-dir⟩/ledger/*.md,
⟨review-dir⟩/collection.md, ⟨review-dir⟩/verification/*.md,
⟨review-dir⟩/root-cause/*.md — plus ⟨review-dir⟩/plan.md.

Procedure: read
⟨skill-dir⟩/references/synthesis-and-output.md — the "Reconciliation"
section — and execute it: enumerate every row ID from the files
themselves and give each exactly one disposition line. Enumeration is
mechanical — extract the ID columns with grep (`⟨PREFIX⟩-⟨n⟩` patterns)
across all row-bearing files first, then read only the row bodies whose
disposition needs judgment; never ingest compliance-matrix prose. The
grep-derived ID set is the completeness authority: every ID it finds must
appear in your table. Then copy the
Pre-Output Gate checklist verbatim to the bottom of reconciliation.md and
fill every line provable from the files, marking draft-dependent lines
"pending draft".

Deliverable: ⟨review-dir⟩/reconciliation.md.

Return: one line — total rows, unaccounted rows (list them if non-zero),
promoted findings count, questions count, open gate lines.
```

## Brief — Draft Writer (Phase 7)

```text
Scope: write the review from the reconciled record.

Inputs: ⟨review-dir⟩/reconciliation.md, ⟨review-dir⟩/verification/*.md,
⟨review-dir⟩/root-cause/*.md, ⟨review-dir⟩/context.md, ⟨review-dir⟩/pin.md,
⟨review-dir⟩/directives.md, ⟨review-dir⟩/plan.md, ⟨review-dir⟩/ledger/PR.md
(if present), ⟨review-dir⟩/comments.json (extract only the unresolved
threads with jq — the file can be enormous on long reviews), and the
worktree for verbatim quotes. If ⟨review-dir⟩/challenge.md exists, address
every item in it — fix or rebut each one explicitly in Verification Notes.

Procedure: read
⟨skill-dir⟩/references/synthesis-and-output.md — "Drafting The Review",
"Finding Format", "Severity Calibration", "Output Format", "Tone" — and
the "Verdict Alignment And Gerrit Output Rules" section of
⟨skill-dir⟩/references/verification-and-fixes.md, then execute them.
Findings come from the reconciliation table's promotions; report record
contradictions instead of papering over them.

Deliverables: ⟨review-dir⟩/draft-review.md,
⟨review-dir⟩/gerrit-comments.md, and the completed pre-output gate lines
in ⟨review-dir⟩/reconciliation.md.

Return: one line — findings by severity, questions count, the verdict
sentence, gate status (all-yes or the "no" lines), file paths.
```

## Brief — Synthesis Challenger (Phase 8)

```text
Scope: adversarial audit of the draft against the record; change nothing.

Inputs: ⟨review-dir⟩/draft-review.md, ⟨review-dir⟩/gerrit-comments.md,
⟨review-dir⟩/reconciliation.md, ⟨review-dir⟩/verification/*.md,
⟨review-dir⟩/ledger/*.md, ⟨review-dir⟩/root-cause/*.md,
⟨review-dir⟩/plan.md, and the worktree for spot-checking quoted lines.

Procedure: read
⟨skill-dir⟩/references/verification-and-fixes.md — the "Final Synthesis
Pass" checklist — and audit the draft against it. Read the draft,
reconciliation.md, and the verdict files fully; audit the ledgers
mechanically — re-derive the row-ID set with grep and check it against
the reconciliation table, then read only the specific rows the draft
cites or the table disposes suspiciously. Hunt: unaccounted ledger rows,
contradictions between findings and other caller paths or feature gates,
miscalibrated severities (check each against the anchor table in
⟨skill-dir⟩/references/synthesis-and-output.md), verdict/finding
inconsistencies, gate lines answered untruthfully, and Gerrit-text rule
violations. Remember the restriction-feature inversion: silently degrading
to unrestricted behavior is a finding, not graceful fallback.

Deliverable: ⟨review-dir⟩/challenge.md — one row per issue: what the draft
says, what the record says, path:line or row-ID evidence, and the
required correction.

Return: one line — issue count and the file path.
```

## Brief — Patchset-Delta Inspector (Phase 9, only if a newer patchset appeared)

```text
Scope: assess patchset ⟨new-PS⟩, which appeared during the review of
patchset ⟨PS⟩.

Procedure: fetch the new revision ref and materialize it in its own
detached worktree under ⟨review-dir⟩ (explicit SHA only, never
FETCH_HEAD). Diff it against the reviewed revision ⟨sha⟩. Classify the
delta: trivial (rebase/comment/format only) or material (behavior, new
files, changed logic). For material deltas, list the affected findings
(by row ID from ⟨review-dir⟩/reconciliation.md) and which roster threads'
scopes the delta touches. Remove your worktree when done.

Deliverable: ⟨review-dir⟩/patchset-delta.md.

Return: one line — trivial or material, affected finding IDs, threads to
re-run, file path.
```
