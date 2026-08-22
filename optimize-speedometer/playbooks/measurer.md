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
3. A/A calibration uses `--stories all`. For a landing checkpoint, obtain the
   exact selector from `campaign.py checkpoint-targets`, pass that value to
   `remote_measure.py --stories`, and record it with `checkpoint --kind
   targeted`. Run a separate `--stories all` / `--kind full-suite` checkpoint
   at the pilot tip and whenever its ten-landing cadence is due.
4. Use at least 32 complete blocks (64 paired reps per arm), with exactly half
   ABBA and half BAAB. If the targeted pilot CI crosses zero, use its MDE to
   choose one larger preregistered balanced confirmation run; do not rerun
   repeatedly until a favorable point estimate appears. The ledger rejects a
   same-size or third same-tip targeted attempt and a duplicate same-tip
   full-suite attempt. A 32-block full-suite
   run is 128 full Speedometer repetitions, has a 64-minute enforced floor,
   and may take several hours.
   Long silence is expected. Wait for the runner and never replace it with
   manually authored JSON.
5. Report point estimate, 95% CI, MDE, blocks, seed, schedule, SHAs, feature
   state, story set, and regression guardrails. If CI crosses zero, say
   inconclusive.
6. Preserve the fetched v3 evidence directory beside the untouched remote
   manifest and summary. Feed each summary to `campaign.py checkpoint` with
   its explicit kind; it reopens every raw result and recomputes the statistic.
   The pilot passes only when the targeted checkpoint CI is positive and a
   separate same-tip full-suite checkpoint shows no stat-sig regression.

Return only the absolute summary path and a one-line verdict:
`IMPROVEMENT`, `REGRESSION`, or `INCONCLUSIVE`.
