# Conditional Orchestration

Procedures that run only when their trigger fires. The orchestrator loads a
section from here when `SKILL.md` sends it, and never as part of the default
read. Nothing in this file relaxes an artifact shape, a gate, or a validation
contract.

## TER Gate

**Only when the plan contains `deferred — pending TER gate (round two)` rows.**
Such a plan runs discovery in two rounds.

After the Transformation Equivalence And Residue thread collects, spawn the
**TER Gate-Brief Builder** (phase brief; `mechanical`, work unit `VTERB`,
`depends_on` TER). The orchestrator cannot read TER ledgers, so the builder
enumerates the exact gate inputs, writes `briefs/VTER.md`, and emits a manifest
fragment. Merge the fragment atomically, record the `VTER` work unit
(`frontier`, `depends_on` VTERB, artifact `verification/VTER.md`), and spawn the
gate skeptic.

Its verdict file uses the dedicated PROVEN/REJECTED/UNPROVEN schema, is excluded
from the ordinary verdict pipeline, and counts only with this execution
provenance — the validator rejects a gate file with no VTER work unit behind it,
a VTER that does not depend on VTERB, or a VTERB that does not depend on every
spawned TER shard.

When it collects, respawn the Planner in residue mode to transition every
deferred row through the canonical append-only
`## Round-two residue continuation — PLAN attempt ⟨N⟩` table (never an in-place
rewrite or a second ordinary roster table) to a concrete `spawn` row whose scope
cites its PROVEN classes (`residue(TC…): `) and whose orchestration attempts
record `depends_on` VTER or the round-two Planner. The validator rejects residue
scoping without a PROVEN verdict, without that dependency, and any malformed
residue-like scope.

Deferred is transient: no deferred row may survive to the collection audit.

## Plan Repair Continuation

**Only when an already collected, non-deferred, not-applicable roster row cites
the wrong absence proof.**

Append the separate canonical `## Plan repair continuation — PLAN attempt ⟨N⟩`
table from `references/templates.md`. Its stable roster identity and exact
expected status guard the replacement; it may correct only the proof status or
transition the row to a concretely scoped spawn. It cannot target deferred rows,
rename identities, or alter subagent/outcome history.

Round-two and proof-repair headings share one increasing, unique attempt
sequence.

## Procedural Repair Of A Sealed Attempt

**Only when a collection-audit gap is confined to a sealed historical attempt's
brief, input, or dependency procedure** — not its content.

Preserve that attempt byte-for-byte and create a later complete attempt whose
brief has the exact line `Procedural repair targets: ⟨work-id⟩:⟨attempt⟩`
(comma-separated for multiple targets). It must use the same canonical artifact,
directly depend on every prior attempt of that work ID, manifest every target
brief and every absolute input named by those briefs, and manifest the artifact
as `prestate`.

This repairs only the declared procedural defects; it never excuses
artifact/content validation or authorizes reanalysis. An invalid repair
declaration remains an error unless a later complete, authenticated repair
explicitly targets that failed attempt.

## Degraded Modes

- **The harness cannot spawn subagents:** execute the plan yourself as serial
  sweeps in plan order, completing each thread's rows before starting the next,
  and keep every artifact-and-gate obligation. Verification Notes must say so
  and name the limitation. Watch your own context: write rows to files as you
  go, and prefer finishing the ledger over holding analysis in memory.

    This path is for harnesses with no subagent-spawning tool at all. Never
    downgrade to it while such a tool exists.

- **Subagents cannot write files:** their briefs' fallback applies — the full
  matrix and rows come back in the final message, never summarized. The
  orchestrator writes each returned payload verbatim to the artifact path the
  worker would have written, without re-reading it afterward, and disclosure in
  Verification Notes names the degraded handoff.
