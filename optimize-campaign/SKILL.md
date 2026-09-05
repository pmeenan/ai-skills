---
name: optimize-campaign
description: Run long-horizon, evidence-bound Chromium benchmark optimization campaigns through a shared adapter pipeline. Use for campaign planning, profiling, mechanism sizing, guarded implementation, randomized A/B measurement, checkpointing, audit, or adding a Crossbench benchmark such as Speedometer or JetStream. Also use when choosing local versus SSH execution or separating functional characterization from authoritative performance evidence.
---

# Optimize benchmark campaigns

One campaign = one frozen baseline, one rendering surface, one calibration
epoch, one `ledger.json`. `campaign.py` is the only writer of campaign state;
every gate is a machine check. Read the benchmark adapter
(`../optimize-speedometer` or `../optimize-jetstream`) first, then
[measurement-policy.md](references/measurement-policy.md). Commands are in
[campaign-runbook.md](references/campaign-runbook.md); transport in
[execution.md](references/execution.md); human prompts in [README.md](README.md).

## The loop, in order

1. **Resume or init.** If `.agents/campaigns/current/ledger.json` exists: `status --print`, `audit`, continue from the recorded gate. Otherwise `init` with the frozen baseline, the host's display policy (`--display :1 --display-vt 9 --pause-service ollama` on the Linux box) and the fleet bot. Never create a second campaign, manifest or ledger to get past a gate.
2. **Calibrate.** Two separately timed A/A runs on the campaign surface, then `campaign.py calibrate`. This records each story's minimum detectable effect (MDE); the qualification floor for a story becomes twice its MDE. Nothing below that floor is worth a build.
3. **Profile.** Two independent exact-window captures (32 reps, fixed-period sampling, same display). Frontiers rank **renderer main-thread** work per story; every entry carries a portability flag and every story a score-time composition (sync vs async, busy vs idle).
4. **Investigate one story area.** Read `investigator.md`. Before proposing a Layer 1/2 mechanism, run the redundancy probe on the site and cite its packet; the claimed avoidable fraction may not exceed what the counts support. Route the hypothesis review to the strongest available model.
5. **Decompose and qualify.** `decompose` refuses impacts below the story floor and Layer 1/2 claims without redundancy evidence. Reviews must cite artifacts and numbers.
6. **Size.** Instrumented twin, three or more targeted blocks per arm, `mechanism_evidence.py`; the avoidable-share lower bound must clear the story floor.
7. **Implement, review, measure.** One invariant behind the campaign flag, build/test receipts, local code review, then the fixed-plan A/B on the same surface. Story flags in manifests are family-adjusted; unadjusted flags are noise until confirmed by a preregistered run.
8. **Land, checkpoint, reprofile.** Landed work is banked only with a local fixed-plan IMPROVEMENT manifest and a Pinpoint IMPROVEMENT on the campaign bot; targeted and full-suite checkpoints follow the adapter cadence.

## Where the model's effort goes

- **Workhorse model:** every mechanical step (captures, builds, receipts, ingest, tests, ledger commands). Follow the runbook commands literally and paste real outputs.
- **Strongest available model:** three decisions only: (a) turning a story frontier plus composition into ranked hypotheses, (b) go/no-go at sizing with the numbers in hand, (c) semantic and spec review of the diff. These are a few dozen calls per campaign against hours of host time per failed candidate.
- Spend creativity on *why the work runs* (repeated inputs, invalidation, phases that could be skipped, work off the score path), not on the leaf that happens to be hot. A leaf tweak that cannot clear the story floor is not a candidate.

## Evidence rules that are enforced by code

- Rendering surface (headless or X display), viewport and GPU renderer are recorded in every manifest and must match the frozen campaign policy and calibration; a run on the wrong surface is rejected at import.
- Story silos are renderer main-thread only; 100 nominal samples at the floor per story or the capture is rejected (raise repetitions or sampling rate, never the gate).
- Qualification floor = max(share floor, 2 × story MDE). Sizing must clear the same floor.
- Layer 1/2 proposals bind a digest-checked redundancy packet.
- PASS reviews cite an existing artifact or bound digest plus a number, with distinct evidence per check.
- Score runs keep ASLR on; cycle-probe captures turn it off. The tuner owns VT handoff and clock policy and restores everything.
- Balanced ABBA/BAAB blocks are the acceptance unit; Bonferroni bounds over all stories plus the suite; no selective reruns.
- Build/test receipts only from `command_evidence.py`; mechanism rows only from nonce-bound captures; landing evidence recomputed from runner manifests and digest-bound in the ledger.

## Stop and report when

A/A calibration fails its gate; the capture cannot reach the sample floor on the configured surface; a mechanism cannot clear its story floor; a candidate's family-adjusted regression survives; or the fresh main-thread frontier holds nothing above the floors. Say which gate stopped you and what number missed by how much. Never invent an exhaustion claim.
