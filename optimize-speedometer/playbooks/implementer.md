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
3. Stage the full diff. It must contain executable production-source changes,
   and new executable lines must explicitly reference the campaign feature;
   comments, tests, and metadata do not count as an optimization or flag guard.
4. Run the build and focused correctness test directly through
   `scripts/command_evidence.py`, producing separate build and test receipts.
   Run these on the same configured bare-metal host and boot as the candidate
   mechanism capture. Typed strings such as “tests passed” are rejected;
   the build must use tracked Chromium depot_tools `autoninja`, and the test
   must be an ELF test binary under this checkout's `out/`.

   ```bash
   python3 .agents/skills/optimize-speedometer/scripts/command_evidence.py \
     --kind build --out <build-receipt.json> -- \
     autoninja -C out/perf <test-binary-target>
   python3 .agents/skills/optimize-speedometer/scripts/command_evidence.py \
     --kind test --out <test-receipt.json> -- \
     out/perf/<test-binary> <focused-test-arguments>
   ```
   The build receipt must explicitly build the exact test binary exercised by
   the test receipt. The test output must report at least one passing gtest.
5. With the same build/probe/block protocol as baseline, run candidate blocks
   through `mechanism_evidence.py capture` (using `--story <name>` for targeted
   single-benchmark verification to maximize signal-to-noise ratio), ingest its
   manifests, then `compare --kind candidate`.
6. Stop if either lower 95% confidence bound is non-positive. Do not use a
   suite-score screen to waive this gate.
7. Measure code-size/cold-path tax where the change adds code or branches.
8. Remove temporary probes, restage the complete production/test diff, rerun
   the receipt commands against that exact staged tree, and enter review with
   `campaign.py advance --opp <id> --to review --build-manifest <build.json>
   --test-manifest <test.json> --verification-manifest <candidate.json>`.

Return only:

```json
{
  "verdict":"REVIEW|REJECT|REWORK",
  "opportunity_id":0,
  "changed_files":["..."],
  "build_receipt":"absolute path",
  "test_receipt":"absolute path",
  "candidate_raw":"absolute path",
  "verification_evidence":"absolute path",
  "staged_tree":"git tree hash",
  "reason":""
}
```
