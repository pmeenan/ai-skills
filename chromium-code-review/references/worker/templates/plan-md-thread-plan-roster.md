<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## plan.md — Thread-Plan Roster

For schema 3, the initial table contains the two named generalist passes. Use
one `spawn` row per pass scoped to `graph:all-inventory-edges` only when it
fits; otherwise use matching numbered shards with exact `graph:E-...` scopes,
covering every edge exactly once per pass. If there are zero edges, use one
unsharded `graph:none` row per pass. Catalog lenses are
added only through graph-routing continuations. Schema 2 retains every roster
entry. Statuses are `spawn`,
`not applicable — trigger absence proved by ⟨T IDs⟩`,
`unreviewed — ⟨reason⟩`, or — during round one of a TER review only, never
in a collected plan — the transient
`deferred — pending TER gate (round two)`; there is no "merged" status. A
round-two residue-scoped spawn row begins its scope cell with
`residue(TC⟨ids⟩): `, citing only PROVEN gate classes. Sharded entries get one row per shard, named
`⟨roster entry⟩ (shard ⟨N⟩: ⟨scope⟩)` — the parenthesized form is canonical
(the validator also accepts `— shard ⟨N⟩`), and shard N's work unit, ledger
file, and audit row are all `⟨PREFIX⟩⟨N⟩`.
The planner assigns a model tier and priority batch per the Model Tiers
contract in `references/scaling-and-indexes.md`; the orchestrator records the
subagent/task identifier when spawned, and the outcome when collected.

```markdown
## Graph routing continuation — PLAN attempt 2

| roster entry | scope | status | tier | batch | subagent | outcome |
| --- | --- | --- | --- | --- | --- | --- |
| Error-Path Walk | graph:E-ERR-2,E-STATE-1 | spawn | frontier | D02 | — | — |
| Threading And Synchronization | specialist:probe; graph:E-ASYNC-1 | spawn | frontier | D02 | — | — |
```

Graph-routing rows add new effective identities, have status `spawn`, and cite
their exact edge IDs. Specialist rows also declare `specialist:full` or
`specialist:probe`; high/either, medium/both, and concrete-trigger routes are
validated against `indexes/specialist-priors.tsv` and explicit `<PREFIX> hard`
trigger inventory.
Retry/continuation attempts retain only unresolved edge
IDs and direct dependencies; they never replay the whole catalog.

**Round two is an append-only plan continuation, never a rewrite or a second
ordinary roster table.** Append exactly one section per Planner attempt using
the heading `## Round-two residue continuation — PLAN attempt ⟨N⟩` and the
same exact ordered columns `roster entry | scope | status | tier | batch |
subagent | outcome`. Every continuation row has status `spawn` and targets an
earlier effective row whose status is exactly
`deferred — pending TER gate (round two)`. An unsharded row replaces the one
earlier unsharded row with the same roster name. Numbered shard rows either
replace one earlier unsharded deferred row one-to-many, or replace already
numbered deferred rows one-to-one by base roster name plus shard number; the
scope text inside a shard label may change. Do not mix sharded and unsharded
continuation rows for one roster name. Unknown, duplicate, ambiguous,
non-deferred, and repeated targets are invalid. Raw tables remain immutable
audit history; parsers, validators, and collectors use the collapsed effective
roster in the original roster position. A partial attempt may transition a
disjoint subset, but every deferred row must be transitioned before the
collection gate.

```markdown
## Round-two residue continuation — PLAN attempt 2

| roster entry | scope | status | tier | batch | subagent | outcome |
| --- | --- | --- | --- | --- | --- | --- |
| Error-Path Walk (shard 1: parse failures) | residue(TC1): parser error paths | spawn | frontier | D03 | — | — |
| Error-Path Walk (shard 2: consumer failures) | residue(TC1): consumer error paths | spawn | frontier | D03 | — | — |
```

**A non-deferred not-applicable proof correction uses a distinct append-only
plan-repair continuation.** It never uses the round-two heading and never
rewrites the base roster. Append exactly:

```markdown
## Plan repair continuation — PLAN attempt 4

| roster entry | expected status | scope | status | tier | batch | evidence |
| --- | --- | --- | --- | --- | --- | --- |
| Callback And Task Lifetime | not applicable — trigger absence proved by T004 | callback/lifetime edges proved by T001,T003 | spawn | frontier | D06 | T001,T003 |
| Teardown Order | not applicable — trigger absence proved by T004 | — | not applicable — trigger absence proved by T024 | — | D01 | T024 |
```

The target is the current effective row's stable roster identity (base name
plus optional shard number) and must resolve exactly once. `expected status`
is an exact compare-and-append guard: a stale or repeated repair fails. The
target must be an existing non-deferred
`not applicable — trigger absence proved by ...` row. Its replacement status
is either `spawn` with a concrete non-sentinel scope, concrete tier, and batch,
or another exact not-applicable proof while preserving scope, tier, and batch.
The repair never changes roster identity, subagent, or outcome. Evidence is
mandatory. A table is atomic: any unknown, ambiguous, duplicate, deferred,
stale, no-op, unsupported-status, or malformed row prevents the whole table
from taking effect. Round-two and repair continuation headings share one
strictly increasing, unique PLAN-attempt sequence and are collapsed in source
order; raw history remains unchanged.

```markdown
# Thread plan — CL 9999999 PS3

| roster entry | scope | status | tier | batch | subagent | outcome |
| --- | --- | --- | --- | --- | --- | --- |
| Desk-Check Simulation + Arithmetic Drills | Push/Flush size math, delay_buffer.cc | spawn | frontier | D01 | task-a1 | 9 rows |
| Data Lineage | bytes: caller → buffer → socket | spawn | frontier | D01 | task-a2 | 4 rows |
| Callback And Task Lifetime | timer_ + flush callback | spawn | frontier | D01 | task-a3 | 6 rows |
| Container And View Invalidation | spans into buffer_ | spawn | frontier | D02 | task-a4 | 3 rows |
| Error-Path Walk | Push/Flush/OnTimer error branches | spawn | frontier | D01 | task-a5 | 7 rows |
| State × Method Matrix | DelayBuffer implicit states | spawn | frontier | D02 | task-a6 | matrix + 5 rows |
| Mode × Host-Capability Matrix | — | not applicable — trigger absence proved by T007 | — | — | — | — |
| Teardown Order | ~DelayBuffer, Abort() | spawn | frontier | D02 | task-a7 | 4 rows |
| Field Propagation Matrix | pending_ and buffer_ propagation/reset sites | spawn | frontier | D02 | task-a8 | matrix + 2 rows |
| Associative Container Semantics | — | not applicable — trigger absence proved by T009 | — | — | — | — |
| Transformation Equivalence And Residue | — | not applicable — trigger absence proved by T010 | — | — | — | — |
| Mechanical Leads | script + manual leads, whole diff | spawn | standard | D02 | task-b1 | 11 rows |
| Per-Surface Invariants | DelayBuffer public API | spawn | frontier | D03 | task-b2 | 6 rows |
| Async And Lifecycle | timer, posted flush, cancellation | spawn | frontier | D03 | task-b3 | 8 rows |
| State/Persistence/Cache | — | not applicable — trigger absence proved by T012 | — | — | — | — |
| Integration And Feature Control | kDelayBufferFeature wiring | spawn | frontier | D03 | task-b4 | 5 rows |
| Security And Trust Boundaries | — | not applicable — trigger absence proved by T014 | — | — | — | — |
| Contracts And API Shape | delay_buffer.h contracts, Socket base clauses | spawn | frontier | D03 | task-b5 | 6 rows |
| Tests As Specifications | delay_buffer_unittest.cc coverage map | spawn | frontier | D04 | task-b6 | 7 rows |
| Changed-Lines Polish | all changed lines | spawn | standard | D04 | task-b7 | 5 rows |
| Threading And Synchronization | timer/task-runner shared state and sequence use | spawn | frontier | D01 | task-c1 | 6 rows |
| Ownership And Blink Lifecycle | — | not applicable — trigger absence proved by T020 | — | — | — | — |
| Mojo IPC Authorization And Sandbox | — | not applicable — trigger absence proved by T021 | — | — | — | — |
| Performance And Resource Scaling | queued bytes, wakeups, per-stream multiplication | spawn | frontier | D02 | task-c2 | 5 rows |
| Platform And Language Semantics | — | not applicable — trigger absence proved by T023 | — | — | — | — |
| Build API And Generated Assets | delay_buffer target source/dependency wiring | spawn | frontier | D03 | task-c3 | 3 rows |
| Privacy And Telemetry | — | not applicable — trigger absence proved by T025 | — | — | — | — |
| Accessibility And Internationalization | — | not applicable — trigger absence proved by T026 | — | — | — | — |
| Network Semantics | socket error/retry and request-boundary behavior | spawn | frontier | D02 | task-c4 | 5 rows |
| Fuzzing And Test Strategy | stateful network input; unit/fuzz target decision | spawn | frontier | D04 | task-c5 | 4 rows |
| Holistic-and-polish thread | bug alignment, scope, description coverage | spawn | frontier | D04 | task-b8 | 4 rows |
```

For each spawned specialist row, the generated brief's Procedure names
`references/chromium-specialist-checklists.md` and that row's exact section.
For FPM, ACS, or TER, it names `references/specialist-recipes.md` and the
exact recipe. A brief names one roster entry even when another lens covers the same
surface; shared evidence does not authorize folding rows together.
