# Campaign independent gate challenge playbook

Run two read-only reviewers before the orchestrator accepts every campaign
gate. These are reasoning challenges in addition to the machine gate; they do
not waive or replace it.

Give both reviewers the gate name, opportunity/profile/checkpoint id, exact
artifact paths, current ledger/STATUS paths, and the command that will consume
the evidence. Do not give either reviewer the other reviewer's conclusion.

The orchestrator must actually invoke two distinct read-only subagent tasks;
it may not author either response itself. Preserve each real task id and
transcript reference with the review. Do not invent signatures or tokens: a
filesystem schema cannot authenticate model identity, so reviewer separation
is an orchestrator responsibility and the transcript is the audit trail.

## Skeptic perspective

Try to disprove the claimed performance conclusion:

- **preflight/profile:** exact score-window scope, equal suite weighting,
  capture independence, sample power, frontier completeness, build fidelity;
- **decomposition/sizing:** one invariant, target-story profiler share,
  plausible avoidable fraction, machine-recomputed local-story impact and
  floor, measured applicability, oracle validity, overlap, critical-path
  classification, CPU share versus score;
- **candidate:** paired identity, positive lower bounds, moved work, probe tax,
  code-size/cold-path tax, distinct product trees/binaries;
- **checkpoint/pilot:** `out/release`, exact preregistered target-story set for
  targeted gates, full-suite scope for regression gates, block balance, MDE,
  CI, fresh seed, cumulative direction, multiple testing, practical effect size;
- **reprofile/exhaustion:** residual work, stale evidence, hidden known paths,
  and whether stopping is supported by the latest enabled profile.

## Adversarial perspective

Try to find a way a lazy or goal-misaligned agent could have satisfied the
artifact shapes without making Chrome faster:

- comment/whitespace/test-only changes or bundled unrelated mechanisms;
- synthetic/copied logs, placeholder suites, fake commands, stale binaries,
  wrong trees, hand-authored provenance, or probes included in scored work;
- benchmark strings/data-shaped special cases, behavior changes, feature-off
  drift, lifecycle/security/privacy regressions;
- selective reruns, copied checkpoint numbers, favorable-seed hunting, or
  treating patch count as the objective.

## Output contract

Return only:

```json
{
  "schema_version":1,
  "role":"skeptic|adversary",
  "reviewer_task_id":"real subagent task id",
  "transcript_ref":"real task/transcript reference",
  "gate":"preflight|profile|decomposition|sizing|candidate|checkpoint|reprofile|exhaustion",
  "artifact_digests_checked":["sha256:..."],
  "verdict":"PASS|CHALLENGE",
  "challenges":["specific artifact-backed issue"],
  "why_this_proves_real_speedup":"one concise sentence or empty on CHALLENGE"
}
```

PASS is not “the files exist.” It means the reviewer independently opened the
raw evidence and found no credible path by which this gate could pass without
the claimed real-world conclusion. A CHALLENGE pauses the orchestrator until
the evidence is regenerated, the candidate is rejected, or the concern is
explicitly shown irrelevant. No prose review can turn a failed machine gate
into a pass.
