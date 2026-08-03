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

## Brief — Delivery Gate Finalizer (Phase 9, after the final challenge)

Tier: `mechanical` (Model Tiers in `references/scaling-and-indexes.md`).

Canonical path: run
`python3 ⟨skill-dir⟩/scripts/refresh-delivery-gate.py ⟨review-dir⟩`
directly after the passing challenge. For an already inspected/revalidated
trivial delta, add `--accept-proven-trivial-delta`. Exit 0 and an affirmative
`delivery-gate.md` are required. Do not spawn an agent merely to fetch scalars
or update Freshness.

The brief below is a degraded wrapper only when the helper cannot execute. Its
Verification Notes disclosure must name the unavailable helper and wrapper
use; it must preserve the helper's exact output and exit semantics.

````text
Scope: degraded wrapper for delivery freshness and only the Freshness gate
line; do not read or edit review findings or any other reconciliation
disposition.

Procedure: first attempt the canonical command above and preserve its exit
status. Only if execution itself is unavailable, reproduce
refresh-delivery-gate.py's checks exactly: fetch/parse Gerrit scalars, verify
pin mapping and the passing exact draft revision, accept a trivial delta only
with explicit revalidation, atomically write delivery-gate.md, and replace
only the single Freshness line. Do not infer semantics or treat a timestamp
update as a patchset.

Deliverable: ⟨review-dir⟩/delivery-gate.md:

```markdown
# Delivery freshness
- Checked after challenge revision: ⟨exact draft revision named by the passing challenge index⟩
- Checked at: ⟨UTC timestamp⟩
- Pinned: PS⟨PS⟩ ⟨sha⟩
- Gerrit current: PS⟨current-PS⟩ ⟨current-sha⟩
- Result: current / historical pin verified / trivial delta verified / newer patchset / fetch failed
- Gate line: yes — current at ⟨timestamp⟩ / no — ⟨reason⟩
```

After writing an affirmative Gate line, replace only line 2 (Freshness) in
the Pre-output gate of reconciliation.md with `yes — delivery-gate.md:
⟨result and timestamp⟩`. On a non-affirmative result leave it
`pending-delivery` or set it to `no — ⟨reason⟩`; never alter another line.
After the helper or degraded wrapper returns, the orchestrator regenerates the derived indexes
before final validation.

Return: one line — current/historical/trivial-delta/newer/fetch-failed,
PS/SHA, path. Final delivery is blocked unless this artifact says current,
historical pin verified, or trivial delta verified. A trivial newer delta
passes only after its metadata draft revision and fresh full challenge; a
material delta starts a new pinned review directory.
````
