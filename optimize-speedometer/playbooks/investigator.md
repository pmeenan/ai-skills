# Investigator playbook

Goal: turn one profiled area into one testable mechanism and machine-validated
sizing evidence. Source inspection alone is never sizing evidence.

Inputs: discovery/mechanism id and key, profile id, exact profile artifacts,
tree-lease status, and output directory.

Procedure:

1. State one invariant in the form: “When condition C is measured true, work
   W can be avoided while preserving behavior B.” Split independent invariants
   into separate mechanism keys.
2. Use tracing to classify W as `score-critical` or `cpu-only`. Digest the
   trace artifact. Do not infer criticality from renderer CPU share.
3. Add temporary flag-controlled instrumentation in a release-like official
   PGO/ThinLTO build. Within every block, emit one row for each
   repetition/suite group (at least all 32 suites). Measure per row:
   - calls;
   - applicable calls;
   - exclusive cycles for W;
   - avoidable cycles established by a dual-path counter or oracle;
   - total cycles within exact score intervals.
4. Calibrate instrumentation with A/A. Overhead above 1% is a failure. Avoid
   raw TSC subtraction unless CPU migration, descheduling, nesting, and probe
   overhead are explicitly handled. Prefer per-thread perf hardware counters
   or the chrome-cycle-profiling harness.
5. Follow `resources/instrumented_twin.md`. Produce instrumentation overhead
   with `calibrate-aa`. Run at least three independent baseline blocks only via
   `mechanism_evidence.py capture`, then pass its capture manifests to
   `ingest`. Never invoke the harness separately, transcribe emitted rows,
   author a capture manifest, or type a computed ceiling.
6. Run `mechanism_evidence.py summarize`; it verifies log digests and counter
   quality, then computes an upper confidence
   bound on avoidable scored CPU-cycle share, not score delta. If it fails,
   reject or redesign the probe.
7. When feasible, create an intentionally incorrect oracle that bypasses only
   W, collect paired blocks, and run `mechanism_evidence.py compare --kind
   oracle`. The oracle must not enter the production diff.
8. Confirm baseline/oracle use distinct source-tree and browser identities;
   identical builds are rejected. Write a short dossier linking raw browser
   logs, capture manifests, raw JSON, and derived artifacts by path and
   digest. Return the tree clean.

Return only:

```json
{
  "verdict":"SIZE|REJECT|SPLIT",
  "opportunity_id":0,
  "mechanism_key":"component/strategy",
  "invariant":"...",
  "score_scope":"score-critical|cpu-only",
  "baseline_raw":"absolute path",
  "sizing_evidence":"absolute path",
  "oracle_evidence":"absolute path or null",
  "dossier":"absolute path",
  "reason":""
}
```

Forbidden phrases in evidence fields: “likely,” “should,” “estimated from
share,” and unmeasured percentages.
