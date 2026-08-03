<!-- Generated from ../../synthesis-and-output.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Synthesis And Output

This file is executed by the late-phase worker agents: the
Reconciliation-Builder, the Draft-Writer, and the Synthesis Challenger. The
severity section also binds verification skeptics, whose CONFIRMED verdicts
must name an anchor from the table below. The orchestrator does not load
this file. Artifact shapes live in `references/templates.md`; the
contradiction checklist and Gerrit output rules live in
`references/verification-and-fixes.md`.

## Severity Calibration

- **P1:** Serious correctness, security, data loss, UAF, deadlock, or major
  regression risk. Must fix before landing.
- **P2:** Real correctness risk, missing coverage for core/default behavior,
  likely production regression, or contract ambiguity that can mislead
  callers. Normally fix before LGTM.
- **P3:** Documentation clarity, non-blocking test polish, minor efficiency,
  small consistency issues, or defensive improvements. Often optional or
  follow-up-worthy.

Calibration notes:

- In stack or foundation CLs, API contract mistakes can be P1 even before a
  production caller lands if follow-up CLs are likely to bake in the behavior.
- Do not downgrade an API-shape, sentinel, or contract issue merely because it
  is documented if the documented behavior remains a footgun for downstream
  CLs.
- A mock-time hang that can block CI is more severe than a comparable
  real-time performance nuisance.
- Avoid blocking on speculative problems, style preferences, or fixes whose
  tradeoffs have not been validated.

Anchor table — match each finding to the nearest anchor and argue any delta
explicitly. Anchors beat intuition, especially for test-gap severity:

| Finding pattern | Severity |
| --- | --- |
| Dropped completion callback on an error path (caller waits forever) | P1 |
| Success-shaped return (positive length, `OK`) after failure cleanup in a `DoLoop`-style state machine | P1 |
| Discarded accepted/written-count return (`Push`, short `Write`) — silent byte loss | P1 |
| Callback or timer bound with `Unretained` plus a reachable destroy-before-fire path | P1 |
| Documented base-interface contract clause violated by an override (buffer retention across `ERR_IO_PENDING`, `OK`-vs-byte-count semantics) | P1 |
| Renumbered or reused values of a persisted/serialized enum | P1 |
| Zero-delay self-reposting task that busy-loops `FastForwardBy` under mock time (CI hang) | P1 |
| Restriction feature (throttle, quota, block, isolation) silently degrading to unrestricted behavior on the common path | P1; P2 when the bypass needs an uncommon mode |
| Success-only metric (duration, success count, size/ratio) logged on aborted or cancelled operations | P2 |
| Load-bearing metadata written fire-and-forget (selectable-but-corrupt state) | P2 until proven unobservable |
| Missing test coverage for the default/core mode of new behavior | P2 |
| Sidecar (cache/compression/metrics) failure propagated into the primary operation's result | P2 |
| Untested kill-switch OFF branch whose OFF behavior differs from pre-CL behavior | P2 |
| Untested kill-switch OFF branch that only gates memoization of an invalidation-free value | P3 |
| Shared mutable state written and read across sequences/threads with no named happens-before edge (lock, sequence affinity, or acquire/release pair) | P1 |
| Mojo/IPC message field used for allocation, indexing, arithmetic, or authority lookup before privileged-side validation | P1 |
| Strong Oilpan reference (`Member`-equivalent reachability) missing from `Trace`, or GC object reachable from an untraced field | P1 |
| Untrusted-side (renderer/network)-controlled growth of a privileged-process queue, map, or buffer with no cap or eviction | P2 until proven bounded |
| User-identifying data (PII, credentials, stable identifiers, private URLs) emitted to logs, crash keys, traces, or telemetry | P1 |
| Histogram emission disagreeing with its metadata (unit, bucket range, enum coverage, expiry) — silent misrecording | P2 |
| Bulk-migration call site that can observe a proven old-vs-new behavioral difference (null/error/encoding/lifetime), unaccounted by the CL | P1 |
| Residue hunk in a claimed-mechanical change that alters behavior beyond the proven transformation spec | P1; P3 when provably cosmetic |
| Ambiguous boolean name (policy vs state, `should_` vs `is_`) | P3 |
| Non-ASCII punctuation in comments or developer-facing prose | P3 |
| Defensive hardening or opportunistic cleanup absent from the CL description | P3 (suggest split or description mention) |
