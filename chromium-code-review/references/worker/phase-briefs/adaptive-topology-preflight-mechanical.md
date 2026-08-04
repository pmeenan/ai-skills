<!-- Generated from ../../phase-briefs.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Phase Briefs

Orchestrator-facing: these briefs and SKILL.md are the only skill content the
orchestrator loads before synthesis; Phase 7 also loads
`synthesis-orchestration.md`. Once the snapshot exists, load the per-brief
section files under `⟨skill-dir⟩/references/worker/phase-briefs/`
just-in-time — the Common Header once, then each phase's brief when that
phase becomes runnable — rather than ingesting this whole file. Each brief
below is spawned as one fresh-context subagent. Copy the brief, substitute every `⟨placeholder⟩` (all paths
absolute — subagents start cold in the repository checkout), prepend the
Common Header, and spawn. Do not paraphrase briefs or compose them freehand,
and do not inline reference-file content into them.

For every substitution, `⟨skill-dir⟩` is the verified immutable
`⟨review-dir⟩/skill-snapshot`, never the live canonical skill checkout. The
snapshot contains generated per-section worker references under
`⟨skill-dir⟩/references/worker/⟨stem⟩/⟨slug⟩.md` (each stem has an
`index.md` naming its sections); the briefs below already point at the exact
section files their workers execute, so a worker never ingests a whole
reference monolith for one section. Finish
the substituted brief and its exact input list, then register both with
`⟨skill-dir⟩/scripts/seal-work-unit.py` before spawning it. A sealed brief is
read-only; corrections use a new attempt-numbered brief and seal.

Discovery-thread and skeptic briefs are NOT here — the Planner and
Verification-Planner agents write those into `⟨review-dir⟩/briefs/`, and the
orchestrator spawns them with only: "Read and execute the brief at
⟨absolute brief path⟩. It defines your pin, scope, procedure, deliverable,
and rules."

## Adaptive Topology Preflight (mechanical)

After pinning, run `scripts/profile-review.py` to write
`⟨review-dir⟩/profile.json` and `profile.md` in the shapes from `templates.md`.
Reject a stale pin, malformed signal, unsorted/duplicate hunk ID, or
classification that does not follow the template precedence. Do not ask an
agent to estimate effort from prose.

Use the resulting `micro`, `standard`, `high-risk`, or `large` class only
to choose budgets, sharding, and mechanical fast paths. Micro requires affirmative
absence evidence for every semantic exclusion; missing or unknown evidence
falls back to standard or the signaled higher-risk class. The typed complexity graph selects analytical fan-out. Verification and reconciliation gates remain mandatory.

Profile signals also seed specialist routing, but they never remove the
Inventory agent's obligation to evaluate every hard trigger in
`inventory-and-planning.md`. A profile/subsystem proximity signal is only a
soft likelihood amplifier unless it proves the hard column's changed contract
or boundary. An absent signal is only one part of the cited negative evidence
needed for not-applicable status.

Every worker packet obeys `profile.json`'s context budget and the complete
counting rules in `references/scaling-and-indexes.md`. Measure required
headers, references, and artifacts before spawning; split or continue instead
of approaching the limit.
