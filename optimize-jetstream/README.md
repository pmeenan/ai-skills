# JetStream characterization and campaign preparation

JetStream currently supports local integration checks and immutable-payload
score/component parsing. Exact-window profiling and the authenticated fleet
contract still require JetStream-specific validation. A full admission
campaign must stop at that capability boundary.

## Start a new campaign preparation session

> Use optimize-jetstream and optimize-campaign in `~/src/chromium/src` to prepare
> a new JetStream campaign `<name>`. Check for an existing campaign or active
> measurement first. Characterize a small workload with the existing
> `out/Default/chrome` and matching chromedriver, preserve component output and
> payload identity, and treat all development-build numbers as diagnostic.
> Identify the pinned payload and calibration work needed for authoritative
> scores. Report the remaining exact-window and signed fleet prerequisites;
> do not copy Speedometer thresholds or bypass those gates to start admission.

## Resume preparation part-way through

> Resume optimize-jetstream using the existing campaign/work directory
> `<absolute path>` in `~/src/chromium/src`. Inspect its ledger if initialized,
> retained characterization outputs, payload digest and unresolved integration
> checks. Preserve workload selection, component semantics and all prior
> attempts. Follow an active measurement before launching another. Continue the
> first unfinished supported step, and report the exact-window/fleet blockers
> honestly rather than creating a parallel campaign or relabeling diagnostics
> as performance evidence.

See [the adapter reference](references/jetstream3.md) and
[shared measurement policy](../optimize-campaign/references/measurement-policy.md).
