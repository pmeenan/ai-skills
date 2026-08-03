<!-- Generated from ../../chromium-specialist-checklists.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Chromium Specialist Checklists

Load only the sections activated by deterministic inventory triggers. Treat
these as discovery supplements: record every anomaly as a ledger candidate and
leave severity/disposition to verification. Close a row clean only with a
`path:line` citation to the relevant guard, owner, bound, metadata, or test.

## Fuzzing And Test Strategy (FTS)

Trigger on parser/decoder/deserializer/decompressor/protocol/state-machine/
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
- For web-exposed behavior changes, cite the governing spec section and
  require WPT coverage (or a concrete reason none is possible — then a
  WebTest). Check that a `RuntimeEnabledFeatures` status matches the change's
  shipping intent, and record a candidate when web-visible behavior ships
  without a feature gate or spec/WPT anchor.
- Require the test to fail against parent behavior for the intended reason.
  Mutation-probe changed conditions/state/callbacks/gates and assert externally
  meaningful behavior across positive/negative/boundary/error/teardown paths.
- Keep tests hermetic and production-faithful. Do not mock away ordering,
  serialization, lifecycle, authorization, persistence, or process boundaries.
- Inspect disabled/flaky/retry/expectation/skip changes. Require narrow reasons
  and ensure the test runs in relevant CQ/CI shards with the feature activated.
