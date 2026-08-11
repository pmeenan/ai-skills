# Measurer playbook

Goal: measure aggregate Speedometer score movement without changing code.

Inputs: mode, SHAs/feature, host, full-suite or targeted story, minimum blocks,
and summary output path.

Rules:

1. Use the remote bare-metal machine. `out/perf` is the official symbols-on
   build for sampling profiles only. Every A/A, feature A/B, checkpoint, or
   score verdict uses symbol-free `out/release` (or `out/release_a` and
   `out/release_b`) with official PGO2/ThinLTO provenance.
2. Omit `--seed` to generate a fresh seed, or use an explicitly supplied new
   seed. The harness records it and creates a balanced ABBA/BAAB schedule.
3. A/A calibration and cumulative checkpoints use `--stories all`. A targeted
   story run only follows up a lead and cannot replace a checkpoint.
4. Use at least 32 complete blocks (64 paired reps per arm), with exactly half
   ABBA and half BAAB. If the pilot CI still crosses zero, increase the even
   block count and remeasure; do not land a sixth candidate or rerun merely
   until a favorable point estimate appears.
   This is 128 full Speedometer repetitions: the enforced wall-time floor is
   64 minutes and a normal run, including rebuilds, may take several hours.
   Long silence is expected. Wait for the runner and never replace it with
   manually authored JSON.
5. Report point estimate, 95% CI, MDE, blocks, seed, schedule, SHAs, feature
   state, story set, and regression guardrails. If CI crosses zero, say
   inconclusive.
6. Preserve the fetched v3 evidence directory beside the untouched remote
   manifest and summary. Feed the summary to `campaign.py checkpoint --summary`;
   it reopens every raw result and recomputes the statistics.
   The first-five-candidate pilot passes only when the cumulative 95% CI is
   positive; a positive point estimate alone is `INCONCLUSIVE`.

Return only the absolute summary path and a one-line verdict:
`IMPROVEMENT`, `REGRESSION`, or `INCONCLUSIVE`.
