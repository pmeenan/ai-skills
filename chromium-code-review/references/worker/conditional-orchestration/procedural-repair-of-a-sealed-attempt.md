<!-- Generated from ../../conditional-orchestration.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Conditional Orchestration

Procedures that run only when their trigger fires. The orchestrator loads a
section from here when `SKILL.md` sends it, and never as part of the default
read. Nothing in this file relaxes an artifact shape, a gate, or a validation
contract.

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
