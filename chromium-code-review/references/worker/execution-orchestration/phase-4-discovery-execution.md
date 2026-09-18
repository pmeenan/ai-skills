<!-- Generated from ../../execution-orchestration.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Execution Orchestration (Phases 4 to 6)

Discovery execution, collection audit, verification, root-cause analysis, and
reconciliation. The orchestrator loads this file when Phase 4 becomes runnable
and works from it through the end of Phase 6, then hands off to
`references/synthesis-orchestration.md` for Phases 7 to 9.

Everything the orchestrator needs for these phases is here; `SKILL.md` keeps the
standing rules that apply across all phases — the context budget, partial
returns and narrow repair, sealing, waiting on `await-workers.py`, and the
prohibition on reading helper source — and does not restate anything below.

## Phase 4 — Discovery Execution

**Wave width is a floor, not a ceiling: never spawn one agent while two or more
dependency-ready rows are queued.** Launch the whole dependency-ready set up to
available capacity, default eight. Spawn a planner and its first executor batch
together where the dependency allows it.

**Then block on `scripts/await-workers.py` until the wave returns.** Do not
poll, do not set timers, and do not end the turn.

Runs of this skill show the same pattern across models: a single agent sustains
real depth on only one or two threads per pass — whichever grab its attention —
and everything else gets a shallow read. So discovery is never one agent.

**Spawn one subagent per spawned effective plan row, with the spawn prompt "Read
and execute the brief at ⟨absolute path to briefs/THREAD.md⟩. It defines your
pin, scope, procedure, deliverable, and rules." Never inline a brief's body into
the spawn prompt.** The two generalist passes are independent; their shards may
run in parallel, but every shard covers one pass's exact edge slice and the two
passes use the same partition. Collect all generalist shards, rebuild
`indexes/topology.tsv` and `indexes/specialist-priors.tsv`, then respawn the
Planner to append the graph-routing continuation before launching any targeted
lens. This fan-in is mandatory even when the next continuation is empty. The
targeted fan-out occurs only after their graph deltas and specialist priors are
indexed. Run threads in parallel where the harness allows, and record each
thread's subagent/task identifier in `plan.md`.

**Spawn every worker at its annotated model tier** — phase briefs carry a
`Tier:` line, `plan.md` rows carry a `tier` column, and skeptics, root-cause
challengers, and synthesis challengers are always `frontier` — per the Model
Tiers contract in `references/scaling-and-indexes.md`. Tiers are a floor; when
the harness cannot select per-subagent models or thinking levels, inherit the
session model and continue.

**Derive each wave from live harness capacity, never a hard-coded batch size.**
Reserve one slot for the orchestrator; launch at most `min(runnable rows,
available child slots)` from the highest-priority dependency-ready rows in
`orchestration.tsv`. If capacity cannot be queried, start with at most eight
children, reduce the wave after a capacity rejection, and refill a slot only
after collecting its prior task. Priority: teardown and error paths, boundary
arithmetic, cross-sequence handoffs, persisted formats, and reentrancy first;
renames and plumbing last. Overlap between threads is fine — redundant coverage
is how disjoint blind spots get closed.

**Discovery ends only when every planned thread has delivered its ledger file;
outstanding threads are blocking dependencies, not background noise.** Expect
the section threads to be slowest — they read the most — and to carry the most
findings. If a thread dies to a transient harness error (capacity limits, rate
limits, timeouts), mark its attempt retryable and follow the targeted
continuation and repair rule above; only when retries are exhausted record it in
`plan.md` and `progress.md` as "terminated — scope unreviewed". Never mark an
uncollected thread Completed. If you interrupt a thread deliberately, collect
its partial ledger file before killing it and record it as "interrupted —
partial".

**If the plan contains `deferred — pending TER gate (round two)` rows, or an
already collected not-applicable roster row cites the wrong absence proof, run
the matching procedure in `references/conditional-orchestration.md`.** Deferred
is transient: no deferred row may survive to the collection audit.

**Collect ledger files; never transcribe or compress them.** Collection is:
confirm the thread's `ledger/⟨THREAD⟩.md` exists and is non-trivial (`ls`,
`wc -l`), independently run
`⟨review-dir⟩/skill-snapshot/scripts/validate-worker-artifact.py` on it, and
only after a zero exit record the outcome (row count from the thread's status
message) in `plan.md` and `progress.md`. A nonzero exit is `needs-repair`, not
`complete`; return the exact diagnostics to the owning attempt while it still
owns a new artifact, or create a narrow amendment attempt for collected
prestate. Rows are carried forward by the files themselves under their own IDs.
Deduplication is a reconciliation-time disposition (`merged →
⟨survivor-row-id⟩` plus structured equivalence), never an orchestrator
pre-processing step; severity is judged in verification, not at collection.
