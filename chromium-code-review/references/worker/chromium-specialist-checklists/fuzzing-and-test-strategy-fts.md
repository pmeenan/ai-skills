<!-- Generated from ../../chromium-specialist-checklists.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Chromium Specialist Checklists

Load only the sections activated by deterministic inventory triggers or the
soft-likelihood routing contract. Treat
these as discovery supplements: record every anomaly as a ledger candidate and
leave severity/disposition to verification. Close a row clean only with a
`path:line` citation to the relevant guard, owner, bound, metadata, or test.

## Fuzzing And Test Strategy (FTS)

Within a routed scope, inspect parser/decoder/deserializer/decompressor/protocol/state-machine/
structured untrusted input; fuzz targets/corpora; disabled/flaky/expectation
changes; or behavior crossing web-standard, process, profile, or platform
boundaries where the faithful test level is genuinely ambiguous. Ordinary
unit-test adequacy remains in Tests As Specifications.

In the thread ledger, produce `surface | attacker/input | state | existing
fuzzer | decision`, target corpus/dictionary/reset/oracle, `invariant | lowest
faithful level | test | negative case | configuration`, and `FTS-*` rows.

- Find fuzzers that reach the production entrypoint. Require a target for rich
  hostile parser/state space or record a concrete reason not to add one.
- Use production options/limits. Seed minimum valid, boundary, variant/version,
  and regression inputs; add dictionaries for stable tokens/magic/field names.
- Reset globals/caches/tasks/clocks/singletons per fuzz iteration. Bound resource
  use without hiding production exhaustion; fail on sanitizer findings, CHECKs,
  hangs, leaks, or cheap semantic invariant violations.
- For stateful protocols, fuzz action sequences including invalid transitions,
  reconnect/reset, reorder/duplicate, and teardown; preserve reproducers as
  deterministic regression tests.
- Choose the lowest faithful test level: unit for isolated contracts, browser
  for wiring/navigation/profile/process boundaries, WebTest for Blink behavior,
  WPT for portable web standards, platform test for OS/device integration, and
  fuzzer for hostile structured/state space.
- When a CL introduces new browser-process Mojo implementations (`*Impl`) that
  accept untrusted renderer input or implement a stateful protocol alongside a
  web-exposed API, audit all three test layers as one cohesive test-architecture
  family:
  1. **Unit tests (`*_unittest.cc`)** driving the browser-side Mojo
     implementations directly over Mojo remotes to cover browser-side validation,
     `mojo::ReportBadMessage` paths (`mojo::test::BadMessageObserver`),
     untrustworthy-origin/OTR/partition rejections that Blink pre-validation
     makes unreachable from JS `EvalJs`, and state-machine/disconnect
     interleavings (and flag pure C++ stack-constructed unit tests placed inside
     `*_browsertest.cc` fixtures that never use the browser or test server).
  2. **Web Platform Tests (WPTs)** (`external/wpt/` or `wpt_internal/` behind a
     virtual suite) for portable W3C/WHATWG/WICG spec-observable behavior
     rather than asserting JS spec behavior only via `EvalJs` in C++
     `browsertest.cc`.
  3. **Browser tests (`*_browsertest.cc`)** focused on browser-only integration
     boundaries: disabled-feature binding rejection, OTR/Incognito and
     in-memory/nonce'd partitions, worker contexts, mid-flight frame detach or
     navigation, multi-chunk streaming backpressure, and cross-context handle
     transfer (`postMessage`/`structuredClone`).
- For web-exposed behavior changes, cite the governing spec section and
  require WPT coverage (or a concrete reason none is possible — then a
  WebTest). Check that a `RuntimeEnabledFeatures` status matches the change's
  shipping intent, and record a candidate when web-visible behavior ships
  without a feature gate or spec/WPT anchor.
- Require the test to fail against parent behavior for the intended reason.
  Mutation-probe changed conditions/state/callbacks/gates and assert externally
  meaningful behavior across positive/negative/boundary/error/teardown paths.
  For V8 `test/mjsunit/` and compiler regression tests, verify optimization/tier
  flags (`%PrepareFunctionForOptimization`, `%OptimizeFunctionOnNextCall`) and
  ensure negative assertions or catch blocks do not mask dead execution branches.
- When `testing/variations/fieldtrial_testing_config.json` enables a feature
  whose C++ `BASE_FEATURE` default is `FEATURE_DISABLED_BY_DEFAULT`, require at
  least one test that explicitly exercises `InitAndDisableFeature(kFeature)` (so
  the production default-off path is not left untested on CQ), and verify
  `base::FeatureParam` combinations across enabled/disabled dependent flags.
- Keep tests hermetic and production-faithful. Do not mock away ordering,
  serialization, lifecycle, authorization, persistence, or process boundaries.
- Inspect disabled/flaky/retry/expectation/skip changes (including
  `TestExpectations` and V8 `.status` files such as `mjsunit.status` /
  `cctest.status`). Verify skips are placed in the designated architecture,
  variant, or platform section with a tracking bug ID, require narrow reasons,
  and ensure the test runs in relevant CQ/CI shards with the feature activated.
