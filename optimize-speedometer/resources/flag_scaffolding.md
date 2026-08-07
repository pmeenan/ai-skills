# Campaign feature-flag scaffolding

Every optimization in the campaign is gated behind **one** feature so the
whole set can be toggled for aggregate A/B measurement:
`Speedometer3Optimizations` (the campaign ledger's `feature` value is
authoritative if it differs). This lands as the first commit on the campaign
branch, before any optimization.

## Design requirements

1. **Default off.** The flag is enabled only via
   `--enable-features=Speedometer3Optimizations` on measurement runs.
2. **Zero overhead when checked.** Hot Blink paths must see a plain static
   bool load, not a `base::FeatureList` lookup.
3. **One flag, not one per optimization.** Runtime bisection is deliberately
   traded away; each optimization is one commit, so build-level bisection
   (`remote_measure.py --mode ab2`) covers regression hunting. Do not add
   per-optimization sub-flags unless a shipped regression forces it.
4. **Fixed for process lifetime.** Code may cache flag-dependent state at
   initialization; nothing may assume a mid-process toggle.

## Implementation sketch

The exact wiring conventions move over time — read the header comments of
`third_party/blink/renderer/platform/runtime_enabled_features.json5` and copy
a current feature that uses `base_feature`, rather than trusting this sketch
blindly.

1. **Runtime-enabled feature (renderer-side check).** Add to
   `runtime_enabled_features.json5`:

   ```json5
   {
     name: "Speedometer3Optimizations",
     base_feature: "Speedometer3Optimizations",
     base_feature_status: "disabled",
   }
   ```

   This generates the `base::Feature` and wires `--enable-features` through
   to Blink automatically. Renderer hot paths then use:

   ```cpp
   if (RuntimeEnabledFeatures::Speedometer3OptimizationsEnabled()) { ... }
   ```

   (Some call sites need the `ExecutionContext`-taking overload; prefer the
   static one where the feature is not origin-trial dependent.)

2. **Browser-process / non-Blink check (only if ever needed).**

   ```cpp
   static const bool sp3_opts_enabled =
       base::FeatureList::IsEnabled(blink::features::kSpeedometer3Optimizations);
   ```

   in the containing function, referencing the generated feature constant.

3. **Probe scaffolding (second commit).** Land the `[SP3_MONO_TIME]`
   `performance.mark()` probe from
   `resources/performance_mark_monotonic_probe.patch` on the campaign branch
   so remote profiling never needs to patch the remote tree. The probe fires
   only on the two `sp3-measurement-*` mark names — two stderr lines per
   scored interval, symmetric across A/B arms, negligible.

## Verification before first use

1. Build `out/Default`; run a Speedometer story with and without
   `--enable-features=Speedometer3Optimizations` and a temporary
   `LOG(ERROR)` behind the check to confirm both states wire through. Remove
   the log.
2. Run the feature-registration check implicitly by running
   `run_ab_benchmark.py --feature=Speedometer3Optimizations` — it refuses
   unknown feature names.
3. Run the flag-overhead null check on the remote machine
   (`remote_measure.py --mode ab` on the scaffolding-only sha): the CI must
   span zero with no stat-sig story regressions.
