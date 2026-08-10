# Implementer playbook

Goal: implement exactly the dossier's one invariant and prove it removes the
measured mechanism work.

Inputs: opportunity id/key, dossier, baseline raw artifact, tests, campaign
flag, tree lease, and candidate output path.

Procedure:

1. Verify a clean tree at the expected campaign tip. Change only the named
   invariant; omit adjacent cleanup and additional fast paths.
2. Keep the behavior behind the campaign flag. Preserve semantics outside the
   flag and on every fallback path.
3. Run focused correctness tests and compile checks.
4. With the same build/probe/block protocol as baseline, emit candidate logs,
   run `mechanism_evidence.py ingest`, then `compare --kind candidate`.
5. Stop if either lower 95% confidence bound is non-positive. Do not use a
   suite-score screen to waive this gate.
6. Measure code-size/cold-path tax where the change adds code or branches.
7. Remove temporary probes, stage the complete production/test diff, and enter
   review with `campaign.py advance --opp <id> --to review --tests
   <exact-command-results> --verification-manifest <candidate.json>`.

Return only:

```json
{
  "verdict":"REVIEW|REJECT|REWORK",
  "opportunity_id":0,
  "changed_files":["..."],
  "tests":"exact commands and results",
  "candidate_raw":"absolute path",
  "verification_evidence":"absolute path",
  "staged_tree":"git tree hash",
  "reason":""
}
```
