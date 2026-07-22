# Chromium Specialist Checklists

Load only the sections activated by deterministic inventory triggers. Treat
these as discovery supplements: record every anomaly as a ledger candidate and
leave severity/disposition to verification. Close a row clean only with a
`path:line` citation to the relevant guard, owner, bound, metadata, or test.

## Contents

- Shared Execution Contract
- Threading And Synchronization (TSY)
- Ownership And Blink Lifecycle (OBL)
- Mojo IPC Authorization And Sandbox (MIS)
- Performance And Resource Scaling (PRS)
- Platform And Language Semantics (PLS)
- Build API And Generated Assets (BAG)
- Privacy And Telemetry (PAT)
- Accessibility And Internationalization (AXI)
- Network Semantics (NET)
- Fuzzing And Test Strategy (FTS)

## Shared Execution Contract

For each activated section, produce the named artifact with:

1. exact trigger hits (`path:line` and symbol);
2. the required model or matrix;
3. one prefixed candidate row per unresolved invariant or omission;
4. `PASS` rows only when evidence cites code or a test by `path:line`.

Do not infer safety from comments, DCHECKs in release-only paths, type names, or
the CL description. Trace the concrete producer, consumer, owner, boundary, and
teardown/version state.

## Threading And Synchronization (TSY)

Trigger on locks, condition variables, waitable events, atomics,
`SequenceChecker`, `ThreadChecker`, cross-sequence callbacks, `ThreadPool`, task
traits, or mutable state reached from multiple sequences.

In the thread ledger, produce `state | readers | writers | synchronization |
required order`, a lock-order graph, wait/post/cancel/destroy timelines, and
`TSY-*` rows with citations to synchronization edges and interleaving tests.

- Enumerate all shared mutable fields and require one consistent protection
  strategy. Name the happens-before edge covering both publication and payload.
- Justify every atomic load/store/exchange/RMW memory order. Flag relaxed
  publication, compound invariants split across atomics, stale compare/exchange
  expected values, and ABA for reusable addresses, slots, or generations.
- Add lock-acquisition edges from success and error paths. Flag cycles,
  callbacks or blocking calls under locks, and unlocked use of invalidatable
  state.
- Require condition-variable waits to re-check a predicate in a loop. Trace
  predicate mutation/signaling under the right lock; probe signal-before-wait,
  spurious wakeup, cancellation, and shutdown for lost wakeups.
- Verify `SEQUENCE_CHECKER` construction or `DETACH_FROM_SEQUENCE` establishes
  the intended first-use sequence. Trace handoff, move, reset, and destruction;
  checked methods do not make a cross-sequence destructor safe.
- Check `ThreadPool` `MayBlock`/`WithBaseSyncPrimitives`, priority, and shutdown
  behavior. Prevent abandoned required cleanup, shutdown stalls, priority
  inversion, and blocking on latency-sensitive sequences.
- Require deterministic interleaving tests using barriers/events/task
  environments or mock time. Sleep-based timing and one schedule prove nothing.

## Ownership And Blink Lifecycle (OBL)

Trigger on owning/non-owning pointers, `raw_ptr`, reference cycles, external
handles, `GarbageCollected`, `Member`, `WeakMember`, `Persistent`, `Trace`, DOM
or event mutation, script-capable bindings, navigation, BFCache, prerender,
freeze/resume, detach, or execution-context destruction.

In the thread ledger, produce a strong/weak/raw/Oilpan/handle ownership graph,
an applicable lifecycle-state table, reentrancy timelines, and `OBL-*`
rows citing the ownership/trace edge and teardown guard.

- Give each allocation or handle one release authority. Trace early return,
  replacement, move, reset, disconnect, partial initialization, and teardown.
- Treat `raw_ptr`, raw references, spans, and views as lifetime claims. Name the
  owner and prove it outlives every synchronous and asynchronous use.
- Draw cycles through ref-counted delegates, observers, repeating callbacks,
  receivers, and remotes. Require a cycle break on errors and shutdown too.
- For Oilpan, verify all strong edges participate in `Trace`; choose `Member`,
  `WeakMember`, or `Persistent` from intended reachability. Check mixin/base
  tracing, cross-heap edges, and pre-finalizers that touch GC objects.
- Do not rely on finalization for timely OS, GPU, Mojo, or network cleanup.
- Trace active, frozen, BFCache/prerendered, detached, context-destroyed,
  navigation-replaced, and destructing states as applicable. Verify suspend is
  distinct from terminal cleanup and restore/rebind cannot duplicate work.
- Bind document-scoped work to a fresh document/navigation identity so old
  callbacks cannot mutate a replacement document or restored entry.
- Treat event dispatch, custom-element reactions, promise resolution, binding
  conversion/callbacks, DOM mutation, focus changes, and observer notification
  as script-reentrant. Revalidate pointers, indices, lifecycle, and invariants.
- Require tests for detach/destroy during callback, navigation replacement,
  freeze/restore, recursion, and collection during reachability transitions.

## Mojo IPC Authorization And Sandbox (MIS)

Trigger on `.mojom`, generated bindings, remotes/receivers, `ReceiverSet`,
associated interfaces, binder registration, messages crossing a process,
process/frame/document identity, handle transfer, broker calls, sandbox policy,
allowlists, handle inheritance, syscalls, or entitlements.

In the thread ledger, produce before/after wire contracts, an old/new peer matrix,
`sender/principal | validation | authorization | sink/capability | lifetime`,
binder-to-implementation flow, sandbox capability delta, and `MIS-*` rows.

- Preserve ordinals and existing field order. Append compatible members
  deliberately and use `MinVersion`/version queries when old peers can appear.
- Check old-to-new, new-to-old, and reconnect/update cases. Verify nullability,
  absent defaults, unknown/extensible enums, unions, and generated defaults.
- Validate sizes, values, URLs/origins, tokens, and handles before allocation,
  indexing, arithmetic, authority lookup, or resource acquisition.
- Authenticate and authorize at the privileged receiver. Treat object existence
  separately from permission to operate on it.
- Ensure `ReceiverSet` context is authentic and fresh across navigation,
  process swap, profile/storage partition, permission changes, and object reuse.
- Trace binder exposure through every factory. Do not expose an interface to a
  broader process/origin/frame state or feature configuration than intended.
- Verify associated-interface ordering only within its guarantee; handle
  disconnect/rebind and traffic on unrelated pipes/task runners.
- Minimize transferred handle type/rights; verify duplication, inheritance,
  transfer, peer closure, revocation, and release ownership.
- Bound message/array size, queued calls, outstanding replies, receiver count,
  and per-client work; disconnection alone is not resource control.
- Treat every broker operation, sandbox allowlist, syscall, entitlement,
  namespace, device, file, registry, or IPC exception as capability expansion.
  Require the narrowest platform scope and a cited caller.
- Test malformed/old-version messages, unauthorized or stale principals,
  cross-profile/document reuse, disconnect races, queue pressure, revocation,
  and bad-message isolation.

## Performance And Resource Scaling (PRS)

Trigger on hot/startup code, per-frame/tab/process state, unbounded loops or
inputs, caches/queues, allocations/copies, task hops, timers/wakeups, GPU
resources, benchmarks, or claimed performance/memory effects.

In the thread ledger, produce `operation | cost/item | bound | fanout |
worst cost`, `resource | owner | cap | eviction/release | pressure behavior`,
before/after evidence, and `PRS-*` rows citing bounds and measurements.

- Derive time/space complexity, including hidden scans, repeated sorting,
  nested callbacks, string building, and retries on adversarial input.
- Multiply by tabs, frames, documents, origins, processes, profiles, observers,
  devices, retries, and queued events as applicable.
- Require limits and eviction for queues, maps, caches, histories, pending
  requests, and buffers. Check churn, duplicates, memory pressure, and teardown.
- Count allocations, copies, serialization passes, conversions, and temporaries;
  verify the actual overload and backing-store ownership permit moves.
- Trace thread/process hops, blocking, priority inversion, and work that wakes an
  idle process/device. Quantify polling/timer wakeups in background/no-work.
- Account for startup and binary size: static initialization, eager services,
  templates, generated tables, and per-locale/config resources.
- For GPU work, calculate resource bytes, copies, synchronization, readback,
  retained surfaces, device limits, and loss/reset cleanup.
- Require representative benchmarks/profiles with units, variance, stable
  comparison, and a metric/trace isolating the changed work.

## Platform And Language Semantics (PLS)

Trigger on build/platform guards, OS APIs, paths/handles, packed or serialized
data, CPU-specific code, architecture-sized types, or Java/Kotlin, Objective-C,
Rust, JavaScript/TypeScript, Python, GN, Mojo, or proto sources.

In the thread ledger, produce applicable OS/arch/bitness/endianness/
build configurations, compiled implementation/tests per non-equivalent row,
language boundary hazards/tools, and `PLS-*` rows with build/test citations.

- Expand nested `BUILDFLAG`, preprocessor, GN, runtime-feature, and architecture
  conditions; find missing implementations, dependencies, tests, and branches.
- Check 32-bit truncation/layout, pointer/integer conversions, native-sized wire
  fields, alignment/packing, unaligned access, and endianness.
- Verify path separators/roots/case/Unicode/reserved names/permissions/atomic
  replace, plus POSIX fd and Windows handle validity/inheritance/close behavior.
- Check OS API availability/behavior across supported SDK/deployment targets,
  libc/toolchain variants, and architectures. Scrutinize platform skips.
- Java/Kotlin/Android: check component lifecycle, configuration changes, UI vs
  binder threads, JNI local/global/weak refs, exceptions/nullability, API levels,
  and R8/Proguard behavior.
- Objective-C/C++: check ARC strong/weak/autorelease ownership, block captures,
  delegates, bridging, NSError/exception boundaries, main-thread UI calls, and
  ObjC++ destruction order.
- Rust/C++ FFI: prove `unsafe`, aliasing/pinning, ownership, encoding/length,
  repr/layout, panic/unwind, `Send`/`Sync`, callback lifetime, and error mapping.
- WebUI JS/TS: check promise cancellation/rejection, listener cleanup, stale
  results, message trust, HTML/Trusted Types sinks, DOM nullability, and bundles.
- Python: check runtime compatibility, subprocess quoting, paths/encoding,
  deterministic order, timeout/error cleanup, hermetic imports, and tests.
- GN/Mojo/proto: check target/toolchain context and generated-language defaults,
  unknown values, numbering/versioning, and regeneration inputs.
- Verify each cross-language contract in producer and consumer; bindings can
  erase nullability, ownership, signedness, errors, threads, and lifetimes.

## Build API And Generated Assets (BAG)

Trigger on added/moved/deleted files, public headers, targets, component
boundaries, `BUILD.gn`, `.gni`, `DEPS`, `OWNERS`, export macros, `.grd`, `.grdp`,
`.xtb`, `.mojom`, `.proto`, WebUI bundles, or generated files.

In the thread ledger, produce `file/symbol | owner target | sources/data/public |
deps | visibility`, exported API/ABI delta, source-to-generated-output chain,
and `BAG-*` rows citing metadata and source-of-truth inputs.

- Account for files in `sources`, `public`, `data`, generated inputs, packaging,
  and tests, including platform-conditional parity.
- Check direct `deps`/`public_deps`, configs, data deps, toolchain context,
  `DEPS`, `specific_include_rules`, visibility, and `testonly`. Do not treat a
  single `gn check` configuration as universal proof.
- Check `OWNERS`, per-file rules, component ownership, and new-directory
  coverage; moves can change review/dependency policy.
- Verify component export macros, template instantiation, vtable/key function,
  symbol visibility, and static/component variants.
- Require public headers to be self-contained and expose clear ownership,
  lifetime, and threading contracts. Trace downstream signature/default/
  semantic migrations; consider virtual/layout/packing/enum ABI effects.
- Do not edit derived outputs. Identify source generator/input, regenerate
  deterministically, and reject unrelated churn.
- For GRIT, check IDs, conditions, scale factors, locale resources,
  placeholders, `.xtb` mapping, packaging, and generated consumers.
- For mojom/proto/WebUI bundles, verify inputs, versions, generated target deps,
  resource maps, bundling assumptions, and tests against regenerated outputs.

## Privacy And Telemetry (PAT)

Trigger on identity, permissions, secrets/credentials/tokens, user/profile data,
paths, incognito/storage partitions, consent/retention/deletion, crypto/random,
logging, histogram macros/XML, UKM, source IDs, metric emission changes, or
enterprise policy surfaces (`components/policy`, `policy_templates.json`,
policy-gated behavior).

In the thread ledger, produce `datum | principal/purpose | storage/transit |
readers | retention/deletion | profile/partition`, an async authorization
timeline, `metric | site | population/frequency | value/unit | metadata`, and
`PAT-*` rows citing enforcement and emission sites.

- Authenticate/authorize at the enforcement boundary and revalidate after async
  gaps, redirects, navigation, profile changes, or object replacement.
- Defend paths against traversal, alternate/encoded separators, symlink/reparse
  races, Unicode/case aliases, and unsafe archive extraction.
- Keep secrets, credentials, tokens, private URLs, user text, and stable IDs out
  of logs, crash keys, traces, errors, lower-trust IPC, and debug persistence.
- Bound attacker-controlled allocation, parsing, decompression, recursion,
  concurrency, retries, and queueing before incurring the cost.
- Use reviewed crypto/secure randomness; verify nonce uniqueness, key lifetime,
  authentication-before-use, downgrade behavior, and errors.
- Isolate regular/incognito/guest/managed/system profiles and storage partitions.
  Require purpose, minimization, consent/policy, retention, deletion, and cleanup
  across backup/sync/cache copies.
- For enterprise policies: verify schema and `policy_templates.json`
  documentation match the implementation, dynamic-refresh behavior is
  deliberate, precedence against user settings is defined, and a
  policy-disabled path is tested.
- Match histogram type, unit, range, buckets, name, summary, expiry, and XML.
  Preserve enum numbers, never reuse retired values, and cover emitted maxima.
- Count UMA emissions per logical event across retries, duplicate observers,
  restore, success, and error paths.
- For UKM, verify source/document identity freshness, consent/policy/incognito
  gates, profile isolation, cardinality, identifiability, and absence of PII.
- Test non-emission when gated plus duplicate-callback, incognito, stale
  principal, oversized input, deletion, and teardown paths.

## Accessibility And Internationalization (AXI)

Trigger on UI controls, focus/input, DOM/AX trees, roles/names/states/actions,
announcements, color/animation, user-visible strings, GRIT, locale/time zone,
plurals, formatting, text direction, or layout mirroring.

In the thread ledger, produce `control/state | role/name/state/action |
focus/keyboard | AX event`, `message | resource | placeholders/plural | locale |
direction`, representative mode/locale evidence, and `AXI-*` rows.

- Verify roles, accessible names/descriptions, state/value, actions, and AX tree
  relationships across dynamic insert/remove/reparent/visibility/errors.
- Preserve logical focus through open/close/navigation/rerender/deletion; provide
  keyboard completeness, visible focus, sensible tab order, and no trap.
- Emit correct tree/state/live-region events without stale or duplicate
  announcements. Test screen-reader-visible semantics and dynamic updates.
- Preserve contrast/meaning in high contrast and forced colors; do not use color
  alone. Respect zoom/text scaling and reduced motion.
- Localize user-visible strings without concatenated fragments. Preserve
  translator-reorderable typed placeholders and locale plural/select rules.
- New or changed translatable strings need translator context: a meaningful
  `desc`, and the screenshot metadata Chromium's translation pipeline expects
  for new UI strings. A missing screenshot/desc is a polish candidate, not a
  silent pass.
- Format date/time/duration/number/percent/currency/list/collation with intended
  locale/time zone; never use localized text as protocol/storage format.
- Check RTL mirroring, start/end semantics, bidi isolation for mixed or user
  text, directional icons, and cursor/navigation behavior.
- Test long/plural/RTL/non-Latin text, graphemes/surrogates/normalization, locale
  changes, multiline/truncation, keyboard-only use, and focus restoration.

## Network Semantics (NET)

Trigger on URLs, requests/responses, redirects, auth/proxy, cookies/credentials,
caching/retries, fetch/navigation policy, headers, DNS, TLS/certificates,
NetworkIsolationKey/partition keys, or profile-bound network contexts.

In the thread ledger, produce `stage | URL/origin | credentials | partition key |
policy | body`, redirect/auth/retry state machine, cache-key table, network-
context ownership, and `NET-*` rows citing canonicalization/policy/isolation.

- Enforce redirect limits and re-run applicable scheme/origin/credential/
  referrer/policy checks at every security transition and final URL.
- Separate server/proxy auth, prevent credential forwarding, and avoid loops or
  inappropriate prompts.
- Retry only idempotent/permitted operations; prove body replayability and handle
  partial upload/response without duplicated effects.
- Set cookie/credentials mode deliberately; preserve SameSite, secure,
  partitioned, third-party-cookie, and storage-access policy.
- Carry correct NetworkIsolationKey/NetworkAnonymizationKey, top-frame site,
  nonce, and storage partition through redirects, caches, sockets, DNS, proxy.
- Include all response-varying security/content dimensions in cache keys; honor
  `Vary`, method, credentials, range/encoding, validation, and no-store/private.
- Apply CORS, CSP, CORP, COEP/COOP, mixed-content, Private Network Access, and
  download/navigation policy to internal, cached, and preloaded paths too.
- Verify TLS/cert hostname/error/pinning/CT/downgrade/client-cert behavior and
  profile-bound exception storage.
- Use standard URL/header canonicalization. Reject CR/LF injection, conflicting
  lengths, forbidden headers, ambiguous IPs, and userinfo confusion.
- Test redirects, auth/proxy, non-replayable body, credential/partition isolation,
  `Vary`, blocked policy, malformed URL/header, cert errors, and profile teardown.

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
