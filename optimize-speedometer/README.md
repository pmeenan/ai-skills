# Speedometer optimization campaigns

This is the Speedometer adapter for [optimize-campaign](../optimize-campaign/README.md).
It uses Speedometer 3.1 and Pinpoint's 20 default workloads. `--stories=all`
explicitly selects all 32 and needs separate calibration/fleet policy.

## Start a new campaign

> Use optimize-speedometer to start `speedometer-september` in
> `~/src/chromium/src` on branch `speedometer`, from frozen baseline
> `<full commit>`. Match Pinpoint `speedometer3`: version 3.1 and its 20 default
> workloads, measuring the exact scored sync/async intervals. Use the configured
> display `:1` on VT 9 and the Mac M1 PGO Pinpoint bot for validation. Check for
> existing campaigns and active measurements first. Establish separate-session
> A/A equivalence and precision, then investigate subtree removal, reuse,
> algorithmic changes and score-critical latency. Register fixed plans before
> measurement and continue through the next checkpoint, reporting evidence and
> blockers rather than treating noisy wins as passes.

Landing evidence is the runner's own A/B manifest (recomputed at import) plus
a Pinpoint summary from the campaign's fleet bot; there is no separate
signing service to deploy.

## Resume a campaign part-way through

> Resume optimize-speedometer at `.agents/campaigns/speedometer-september` in
> `~/src/chromium/src`. Audit the existing ledger, raw profiles/measurements,
> reviews and recorded attempt history. Preserve the campaign's recorded
> version, workload set, baseline, feature state and skill digest, including
> older 3.0 or 32-workload evidence. Follow any active measurement without
> starting another. Continue at the first unfinished valid gate through the
> next checkpoint. Do not create a replacement campaign, rerun failed attempts
> under new names or upgrade old manifests to new defaults.

See [measurement policy](../optimize-campaign/references/measurement-policy.md)
and [Speedometer details](references/speedometer3.md) for evidence semantics.
