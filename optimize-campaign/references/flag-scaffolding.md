# Shared Campaign Feature-Flag Scaffolding

## Clean Branch Candidate Isolation Pattern

All optimizations in the campaign use **one shared feature flag**: `Speedometer3Optimizations`. 

To guarantee **100% isolated measurement** and prevent cumulative false positives without adding per-candidate flags, all candidate evaluation follows the **Clean Branch Isolation Workflow**:

### 1. The Clean Branch Rule
- **Every candidate MUST be implemented and evaluated on a clean branch created directly from baseline `origin/main`** (or using a staged commit on baseline HEAD via `STAGED`).
- The candidate code is guarded by:
  ```cpp
  if (RuntimeEnabledFeatures::Speedometer3OptimizationsEnabled()) {
    // Candidate fast-path logic
  }
  ```
- **Isolated A/B Measurement:** When running `remote_measure.py --mode ab --ref <candidate_branch_sha> --feature Speedometer3Optimizations`:
  - **Arm A (Flag OFF):** The binary at `<candidate_branch_sha>` executes with the feature disabled, which is identical to clean `origin/main` baseline.
  - **Arm B (Flag ON):** Enables the flag, activating **ONLY this candidate's fast-path** (since no prior campaign commits exist on the clean candidate branch).
- **CRITICAL ANTI-PATTERN TO AVOID:** Never measure an unverified candidate on top of the main `speedometer` branch with `--feature Speedometer3Optimizations`. Toggling the shared flag on a branch with prior landed commits enables all banked commits simultaneously, falsely attributing aggregate suite gains to the new candidate.

### 2. Sizing & Verification Gates on the Clean Branch
- On the clean candidate branch, run `mechanism_evidence.py` to satisfy Gate 3 (`sized`).
- Run code review and `remote_measure.py --mode ab` on the clean branch commit to establish the isolated score impact.

### 3. Landing onto the Campaign Branch
- Once verified and approved, land the commit onto the main `speedometer` campaign branch via `campaign.py land`.
- The cumulative `speedometer` branch is used for periodic multi-candidate checkpoints and the final end-of-campaign full-suite sweep.

## Feature Implementation

In `third_party/blink/renderer/platform/runtime_enabled_features.json5`:

```json5
{
  name: "Speedometer3Optimizations",
  base_feature: "Speedometer3Optimizations",
  base_feature_status: "disabled",
}
```

In Blink C++ source:

```cpp
if (RuntimeEnabledFeatures::Speedometer3OptimizationsEnabled()) {
  // Fast-path
}
```

3. **Probe scaffolding (second commit).** Land the `[SP3_SCORE_TIME]`
   `performance.mark()` probe from
   `assets/speedometer3/performance-mark-monotonic-probe.patch` on the campaign branch
   so remote profiling never needs to patch the remote tree. On a clean-slate
   campaign this is the only timing probe; do not install the legacy outer
   `[SP3_MONO_TIME]` probe. The new probe records every sync/async timer that
   feeds the score, buffers rows, and flushes only after the scored work.

## Verification before first use

1. Build the official symbols-on `out/perf`; run a Speedometer story with and without
   `--enable-features=Speedometer3Optimizations` and a temporary
   `LOG(ERROR)` behind the check to confirm both states wire through. Remove
   the log.
2. Run the feature-registration check implicitly by running
   `run_ab_benchmark.py --feature=Speedometer3Optimizations` — it refuses
   unknown feature names.
3. Run the flag-overhead null check on the remote machine
   (`remote_measure.py --mode ab` on the scaffolding-only sha): the CI must
   span zero with no stat-sig story regressions.
4. Compile the patched Blink target with warnings-as-errors and run
   `run_cycle_benchmark.py` once. Require matched `[SP3_SCORE_TIME]` intervals
   and `interval_kind: exact-scored` before committing the fixture.
