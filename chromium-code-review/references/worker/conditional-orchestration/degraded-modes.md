<!-- Generated from ../../conditional-orchestration.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Conditional Orchestration

Procedures that run only when their trigger fires. The orchestrator loads a
section from here when `SKILL.md` sends it, and never as part of the default
read. Nothing in this file relaxes an artifact shape, a gate, or a validation
contract.

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
