<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## Per-Worker Input Manifests

Run `scripts/seal-work-unit.py` only after a brief's text and explicit input
list are final. The helper hashes the final inputs, registers the queued
orchestration row, and makes the brief read-only in one guarded transaction.
Never edit or repoint a sealed brief; create and seal a new attempt-numbered
brief. After an interrupted seal, rerun the exact command; an identical queued
row and manifest return `already sealed` without duplication. A mismatched row
still fails and must be inspected rather than papered over with a spurious new
attempt. Every spawned phase, analytical, planner-shard,
continuation, repair, assembly, and challenge brief has rows; direct
deterministic helper invocations have no worker and are exempt.

```tsv
work_id	attempt	phase	brief	input_path	role	bytes	sha256
VPLAN001	1	5	/tmp/scratch/cl-9999999-ps3/briefs/planning/VPLAN001.md	/tmp/scratch/cl-9999999-ps3/briefs/planning/VPLAN001.md	brief	6210	⟨sha256⟩
VPLAN001	1	5	/tmp/scratch/cl-9999999-ps3/briefs/planning/VPLAN001.md	/tmp/scratch/cl-9999999-ps3/indexes/candidates.tsv	control	18842	⟨sha256⟩
VPLAN001	1	5	/tmp/scratch/cl-9999999-ps3/briefs/planning/VPLAN001.md	/tmp/scratch/cl-9999999-ps3/packets/VPLAN001-candidates.md	candidate-packet	9201	⟨sha256⟩
```

Rows are addressed by `(work_id, attempt)` and joined exactly to
`orchestration.tsv`: every orchestration attempt with a brief must have
manifest rows for that exact `(work_id, attempt)` — including the mandatory
brief self-row — and the manifest's brief must equal the orchestration
row's brief. A continuation attempt therefore gets its own manifest rows
for its own attempt-numbered brief; relabeling a group's `work_id` breaks
the join instead of borrowing another unit's tier budget.

Columns and roles are exact. `role` is one of `brief`, `control`, `reference`,
`assigned`, `candidate-packet`, `card`, `frame`, `section`, or `prestate`.
`prestate` is for the one canonical artifact a continuation attempt appends
to: its bytes/SHA-256 cover the immutable pre-attempt prefix, and the
validator verifies the current file still begins with exactly that prefix —
append-only growth, never a rewrite. Every other role's hash must match the
file exactly. A path containing spaces is written backtick-quoted in briefs
so the validator can parse it. Each work ID
includes its brief as a `brief` row and every control, reference, or assigned
file the worker must load. The generated per-section files under
`references/worker/⟨stem⟩/` exist precisely so a single section is its own
immutable, measurable packet; name those in briefs and manifests, and use the
whole canonical reference file only when the worker genuinely needs most of
its sections. `brief` and `input_path` are
absolute explicit files — never relative paths, globs, directories, ranges,
or "the rest". Every byte
count and SHA-256 covers the exact file bytes; stale/missing files block spawn.

For each work ID, sum `bytes` over unique `input_path` values and require the
total to fit `profile.json`'s `worker_input_budget_bytes`; when one path has
multiple roles, count it once in the total. `candidate-packet` role bytes also
sum to at most `candidate_packet_budget_bytes`. A Finding Writer's `card` input
also obeys `evidence_card_budget_bytes`. Assembly lists every exact child path.
A sectioned challenge lists exact assigned draft/Gerrit section paths, bounded
`frame`, scoped cards, and routing/control files; full `draft-review.md` and
`gerrit-comments.md` are forbidden. Those full files are allowed only for the
explicitly bounded single-shard challenge.

Regenerate the TSV atomically whenever a brief or input changes. **The root
TSV has exactly one writer at a time.** A non-sharded planner, running alone,
appends its generated briefs' rows via atomic rewrite. Parallel planning
shards never write the root TSV: each records its generated briefs' manifest
rows inside its own immutable shard deliverable, and the exact collector —
after verifying coverage — merges those rows into the root TSV atomically
before any generated brief spawns. The validator
compares generated analytical briefs, manifest rows, hashes, sizes, index
fingerprints, and work-kind budgets before spawn. Source/worktree reads and
tool output discovered during reasoning are not preassigned artifact inputs,
but the brief still bounds their semantic scope. The exception is the
generated scope packet: when `packets/⟨WORK⟩.spec.tsv` exists, the
orchestrator materializes `packets/⟨WORK⟩-code.md` before sealing and the
brief lists it as an `assigned` input, so each worker's scoped code is
measured input instead of an invisible per-worker re-derivation.
