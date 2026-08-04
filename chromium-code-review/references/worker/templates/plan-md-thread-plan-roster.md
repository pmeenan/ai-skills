<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## plan.md — Thread-Plan Roster

The initial table contains the two named generalist passes. Use
one `spawn` row per pass scoped to `graph:all-inventory-edges` only when it
fits; otherwise use matching numbered shards with exact `graph:E-...` scopes,
covering every edge exactly once per pass. If there are zero edges, use one
unsharded `graph:none` row per pass. Catalog lenses are
added only through graph-routing continuations. Statuses are `spawn`,
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
| Generalist Semantic And State Discovery | graph:all-inventory-edges | spawn | frontier | D01 | task-a1 | 9 rows |
| Generalist Adversarial And Integration Discovery | graph:all-inventory-edges | spawn | frontier | D01 | task-a2 | 7 rows |
```

For each spawned specialist row, the generated brief's Procedure names
`references/chromium-specialist-checklists.md` and that row's exact section.
For FPM, ACS, or TER, it names `references/specialist-recipes.md` and the
exact recipe. A brief names one roster entry even when another lens covers the same
surface; shared evidence does not authorize folding rows together.
