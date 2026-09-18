<!-- Generated from ../../conditional-orchestration.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

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
