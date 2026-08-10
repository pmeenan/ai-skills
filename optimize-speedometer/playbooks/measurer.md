# Measurer playbook

Goal: measure aggregate Speedometer score movement without changing code.

Inputs: mode, SHAs/feature, host, full-suite or targeted story, minimum blocks,
and summary output path.

Rules:

1. Use the remote bare-metal machine and release-like official PGO/ThinLTO
   builds. Record build provenance.
2. Omit `--seed` to generate a fresh seed, or use an explicitly supplied new
   seed. The harness records it and creates a balanced ABBA/BAAB schedule.
3. A/A calibration and cumulative checkpoints use `--stories all`. A targeted
   story run only follows up a lead and cannot replace a checkpoint.
4. Use at least five complete blocks. Extend to 10–15 when MDE exceeds the
   expected batch effect; do not rerun until a favorable point estimate.
5. Report point estimate, 95% CI, MDE, blocks, seed, schedule, SHAs, feature
   state, story set, and regression guardrails. If CI crosses zero, say
   inconclusive.
6. Feed the untouched remote summary to `campaign.py checkpoint --summary`.

Return only the absolute summary path and a one-line verdict:
`IMPROVEMENT`, `REGRESSION`, or `INCONCLUSIVE`.
