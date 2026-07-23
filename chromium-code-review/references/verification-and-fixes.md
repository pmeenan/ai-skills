# Verification And Fixes

Read this before promoting ledger candidates into the review and before
recommending or endorsing any concrete fix. This file is the precision gate:
discovery deliberately over-generates, and this pass separates real findings
from plausible-but-wrong ones. Severity definitions and calibration notes live
in `references/synthesis-and-output.md`.

## Contents

- Verifying Candidate Findings
- Skeptic Verdicts
- Execution-Based Verification
- Evaluating Fixes
- Root-Cause Trigger Planning
- Root-Cause, Layering, And Fix Optimality
- Final Synthesis Pass
- Verdict Alignment And Gerrit Output Rules

## Verifying Candidate Findings

Verify each non-trivial candidate before presenting it. Prefer concrete code
traces over speculative concerns — but spend the trace: refute candidates with
code, not from memory.

- Build a minimal state or call trace from the code that demonstrates the
  issue, or demonstrates its absence.
- Cite the exact code path and any relevant tests or comments.
- Classify the issue: correctness bug, contract mismatch, missing test,
  performance risk, lifecycle risk, or polish.
- Check whether existing tests intentionally codify the observed behavior.
- Challenge the finding: look for alternate caller paths, wrappers, overrides,
  feature gates, or invariants that make it unreachable or lower its severity.
- To refute a candidate, name the specific guard (the line) that prevents it,
  or produce the concrete trace that completes safely. "Looks handled" or
  "the caller probably checks" is not a refutation — it is the shallow read
  the candidate exists to challenge. For hypotheses written as
  IF/THEN/UNLESS, refutation means filling in the UNLESS with a citation.
- If honest tracing can neither confirm nor refute a candidate, do not drop
  it: convert it into a question for the CL owner in the review's Questions
  section, stating what you traced and what remains unproven. Uncertainty
  rounded down to "probably fine" is how reviews miss real bugs.
- Never edit a discovery ledger to record a verdict. Record refutation in the
  skeptic verdict file and reconciliation; discovery rows remain append-only.
  If a worker must correct its own earlier row, use the normative Amendments
  section from templates.md, preserving the original row and ID.
- Matrix cells marked incompatible-but-guarded are verification inputs too:
  confirm that the named guard actually guards the cell's scenario, on the
  path the scenario takes. In a measured run a cell cited `ShouldTruncate()`
  as the guard for `StopCaching(keep_entry=true)` — but that guard only runs
  on the failure path, and the success path skipped it entirely.
- Distinguish observation from proposed fix. Never recommend a concrete fix
  until it has been traced through the relevant edge cases below.

## Skeptic Verdicts

Every candidate examined in verification gets exactly one verdict row in
its batch's `verification/V⟨batch⟩.md` file (shape in
`references/templates.md`), with ID `V⟨batch⟩-⟨n⟩` and a reference to the
candidate row under test. Three verdicts exist, each with mandatory
evidence fields — a verdict missing its fields is not a verdict:

- **CONFIRMED** requires: the completing trace
  (`scenario → lines visited → bad outcome`), a severity proposal matched to
  the anchor table in `references/synthesis-and-output.md` (name the anchor
  and argue any delta), and an
  origin label (`CL-introduced`, `introduced-in-PS⟨N⟩`, or `pre-existing`).
- **REFUTED** requires: the guard's `path:line`, or the concrete safe trace
  that completes without the bad outcome. For IF/THEN/UNLESS hypotheses,
  refutation means filling the UNLESS with a citation. "Looks handled",
  "the caller probably checks", and "by design" are not refutations.
- **UNPROVEN** requires: what was traced, what remains unproven, and a
  drafted question for the CL owner. UNPROVEN rows go to the review's
  Questions section — never to the bin.

A skeptic that cannot produce REFUTED's required fields has confirmed the
finding, not dismissed it. When the decisive evidence legitimately has no
`path:line` — an absence proof ("no other caller exists": cite the search
run), tool output, or a spec/standard citation — write
`evidence-exception: <nonempty reason and the actual evidence>` in the
evidence field; the validator rejects CONFIRMED/REFUTED rows that have
neither a citation nor a nonempty exception, and an exception is itself a
claim the synthesis challenger may re-check. When verification runs without subagents, the
orchestrator holds itself to the same schema — one verdict row per
candidate, same mandatory fields.

A candidate with a proposed duplicate merge is the sole exception to the
one-verdict-per-candidate rule. It may share the surviving candidate's verdict
only after reconciliation verifies equal trigger, violated invariant, and bad
outcome, with citations. Similar location or fix is insufficient. A rejected
merge returns to verification; it is never silently dismissed.

## Execution-Based Verification

Code citations and paper traces are the default standard of evidence — cheap
and almost always sufficient. Building the patchset or running tests is a
bounded, last-resort tier, not a routine step:

- Use it only in verification (never discovery), and only for a P1/P2
  candidate whose paper trace is genuinely contested — where running the
  smallest test would settle confirm-vs-refute.
- Build only the narrowest target against an existing warm build directory
  (`autoninja -C out/<existing> <test_target>`, e.g. `net_unittests` or
  `components_unittests`, plus a tight `--gtest_filter`). Never `gn gen` a
  fresh output directory in a temporary worktree: a cold Chromium build
  costs an hour-plus and buys less than an hour of tracing. If no warm
  build exists, skip execution and record the candidate as "needs
  execution verification" in Verification Notes.
- Budget it: if the build or run exceeds roughly ten minutes, stop and fall
  back to the paper trace.
- Record in Verification Notes exactly what was built or run, how long it
  took, and which candidate it settled — so the next iteration can judge
  whether the time was earned. The regression test named in a P1/P2 finding
  is a description for the CL owner, not an obligation to implement and run
  it.
- Execution never includes applying a proposed fix or a new test to the
  user's checkout or the review worktree. If trying a change is truly
  unavoidable, copy the touched files to a scratch directory outside the
  repository and experiment there; the review itself stays read-only.

## Evaluating Fixes

Review any proposed fix as carefully as the original bug: trace it through
boundary inputs, all affected state transitions, existing tests, and likely
reentrant/cancellation paths. If you cannot validate the fix, present it as an
option needing verification rather than endorsing it as the correct change.

Sanity-check fixes against common Chromium edge cases:

- Zero, empty, immediate, max-size, overflow, and negative values.
- Posted tasks, timers, delayed callbacks, and task ordering.
- Completion-delay clock origin: total observed latency vs extra latency after
  a wrapped operation completes. Verify synchronous wrapped completion, wrapped
  completion before the budget expires, and wrapped completion after the budget
  is already exhausted.
- Reentrancy from callbacks.
- Cancellation, reset, shutdown, and object destruction.
- `WeakPtr`, ref-counting, ownership transfer, and RAII handles.
- Sequence/thread affinity and destructor sequence requirements.
- Boundary capacity and backpressure behavior.
- Numeric conversion, truncation, overflow, sentinel agreement, and
  representability across signed/unsigned, `size_t`, `int`, and floating-point
  math.
- Terminal or one-shot sentinel results (EOF, closed, cancelled, no more data)
  must not be masked by status predicates added before the operation runs.
- Compile-time gate polarity: when a fix adds or edits `#if`,
  `#if defined(...)`, or `#if !defined(...)` gates — especially snippets
  suggested in review — re-verify branch polarity against the feature name,
  default build configuration, and intended platforms.

Heuristics for choosing between fixes:

- **Prefer state invalidation over partial recovery.** For components managing
  ephemeral, transient, or reconstructible state (caches, Mojo/IPC channels,
  page loading/rendering pipelines, media playback state), prefer total state
  invalidation, reset, or destruction on error/abort over complicating control
  flow to salvage partial state. Correctness and code simplicity outrank
  absolute retention efficiency.
- **Avoid conditional carve-outs for errors.** Do not introduce complex branch
  logic special-casing specific cancellation errors or sub-phases when
  resetting the component or restarting from a clean slate is valid and much
  safer.
- **Shared-helper invariants and side effects.** Before adding assertions to a
  shared helper or routing a new path through an existing completion/cleanup
  helper, trace every caller at the exact moment the helper is entered and
  account for the helper's side effects. If the helper forces success,
  cleanup, or callback state incompatible with the new path, suggest a
  narrower helper or an explicit path. (Example pattern: a fix funnels a new
  failure path through a helper that unconditionally records success and runs
  completion cleanup.)
- **Observable cascade analysis.** For state cleanup, flag-reset, or retry
  bugs, trace the downstream observable effect — a lost callback, mismatched
  result, corrupt persisted data, spurious retry, or double failure — before
  deciding severity or endorsing a fix.
- **Fail open for sidecar layers.** When fixing errors in an optimization
  layer (cache writes, compression, prefetch), prefer dooming the entry and
  letting the primary operation succeed over propagating the error to the
  consumer. The primary path's contract outranks the optimization's
  bookkeeping.
- **Fail open is for optimizations, not restrictions.** The heuristic
  inverts when the feature's purpose IS the restriction — throttling,
  blocking, isolation, quotas: a path that silently degrades to the
  unrestricted behavior is a finding, not graceful fallback. A measured
  run's synthesis challenger rejected a real bug ("in-flight requests
  silently fall back to the unthrottled factory") as "graceful, intended
  fallback" — exactly this inversion.

When a fix changes API shape or caller obligations:

- For nullable callbacks, optional dependencies, sentinels, or optional
  handles: first verify whether optionality is part of the public contract and
  whether tests or callers rely on the absent-value path. Suggest making the
  value mandatory only after comparing that API-shape change against
  preserving the optional contract with clearer tests or docs.
- Compare plausible alternatives before recommending one. Examples: reject
  invalid input vs accept a sentinel; explicit cancellation handle vs weak
  callback pruning; edge-triggered vs level-triggered notifications; owned
  task cancellation vs caller-managed weak callbacks.

## Root-Cause Trigger Planning

The Root-Cause Planner reads the actual candidate and verdict files; the
orchestrator must not infer triggers from terse status messages. It writes one
Trigger Accounting row for every CONFIRMED or UNPROVEN verdict, every
candidate with a proposed fix, and every inventory scope marked `root-cause
required`. Inventory scopes ensure risky changes receive a layering pass even
when discovery found no defect candidate. Schedule root-cause work when any of
these is true:

- proposed P1 or P2;
- risky P3 whose severity depends on reachability or invariant ownership;
- any concrete fix recommendation, regardless of severity;
- performance optimization, flaky-test fix, async/lifecycle change,
  state-machine change, cache/throttle, persisted format, or new state holder;
- a candidate whose local symptom may be shared across caller families.

Rows that meet no trigger remain in the plan as `not applicable — trigger
absence proved by <T IDs>`. Batch scheduled work by related invariant and trace cost; serious
candidates normally stand alone or in very small groups, and no fixed quota
may combine unrelated traces. Keep every generated brief bounded. Assign
distinct zero-padded `RC001`, `RC002`, ... IDs. Generated root-cause briefs inherit the
common directives, authority boundary, append/retry, and partial-return
contract from templates.md.

## Root-Cause, Layering, And Fix Optimality

Run this after candidate verification and before final synthesis. The goal is
to catch surface fixes: changes that repair the observed hunk, caller, or test
without repairing the invariant owner.

For every P1/P2 candidate, risky P3, proposed fix, performance optimization,
flaky-test fix, async/lifecycle change, state-machine change, cache/throttle,
or new state holder, record a root-cause row with these fields:

- **Symptom:** the observed failure, performance cost, race, or review concern.
- **Direct trigger:** the local branch, caller sequence, input, or timing that
  exposes it.
- **Violated invariant:** the property that should always hold, stated without
  reference to the proposed fix.
- **Invariant owner:** the class, method, helper, state enum, protocol, or
  data model that should enforce or cache that invariant.
- **Right-layer evidence:** upstream/source layer checked, local layer checked,
  downstream/caller layer checked, and any canonical state/shared helper found
  by search.
- **Callsite coverage:** whether every production caller or mode sharing the
  invariant is covered, with representative `path:line` citations.
- **Chosen-fix verdict:** validated right layer, plausible but needs owner
  confirmation, too local/surface-level, or no fix proposed.

Use these drills to fill the row:

- Walk one layer upstream to the producer/source of the value, event, state, or
  timing decision. Ask whether enforcing the invariant there would protect more
  callsites with less state or fewer special cases.
- Walk one layer downstream to the consumers/callers. Ask whether the issue is
  caller-specific or shared by all users of the same API, state, cached value,
  or callback contract.
- Search for an existing canonical state owner, shared helper, base-class
  contract, or sibling implementation before endorsing a new field, cache,
  wrapper, or special-case branch.
- For duplicated or cached state, prove why the cache belongs at the proposed
  layer instead of on the canonical object that owns the source value. A cache
  beside a derived consumer is fragile unless invalidation and all relevant
  callers are accounted for.
- For performance work, identify the unit of work whose cost is being reduced
  and the component that actually owns scheduling, batching, throttling, or
  caching for that unit. A rate limit, cache, or token bucket at an input edge
  is suspect when a central worker/state holder owns the work.
- For flaky-test fixes, separate deterministic observation from deterministic
  behavior. Name the production method/protocol whose race was exposed, then
  verify whether the new test setup prevents the race at its source or only
  waits for this test's final condition more carefully.
- For state machines, build or reuse the State × Method matrix for any
  implicated state owner. A bad-state concern must cite the transition path
  that reaches it; a refutation must cite the guard or transition that blocks
  it.
- For async operations, trace the ownership of the pending operation, the
  cancellation/reset/destruction path, and the callback completion contract.
  A local waiter fix is insufficient if the operation itself can still drop,
  duplicate, or reorder completion.

If this pass changes the likely invariant owner, exposes a missing caller
family, reveals duplicated canonical state, or opens a new state-machine or
async scenario, first write each issue as a canonical row in
`ledger/reopened/round-<N>-RC<batch>.md`, with ID
`R<N>-RC<batch>-<n>`, full evidence, origin, requested recipe (if any), and
parent candidate/verdict/RC links. A row that exists only in a brief or status
message does not exist. Run any requested narrow discovery recipe first; it
appends evidence/amendments or additional canonical reopened rows. Then rerun
the Verification Planner in delta mode over exactly that round, execute its
skeptics, and rerun the Root-Cause Planner in delta mode. Challengers do not
create skeptic briefs directly. Increment rounds until no open/triggered row
remains. Do not bury the result as a caveat: either verify it, refute it,
merge it with proven equivalence, or ask the owner before synthesis.

Examples of the intended reasoning pattern:

- Parser performance: if parser-side rate limiting controls work owned by the
  tree builder, check whether the tree builder is the invariant owner because
  it sees all sources of tree-building work.
- Site-for-cookies caching: if a document caches a value derived from
  `SecurityOrigin`, check whether `SecurityOrigin` is the canonical owner and
  whether caching there improves all callsites with less invalidation risk.
- Flaky tests: if a test's end condition is made deterministic, still verify
  whether the method under test can race under production-like sequencing.

## Final Synthesis Pass

Before final output, run a contradiction pass over the ledger and the draft
review:

- Does the final review account for every ledger entry — promoted at its
  calibrated severity (including downgrades), merged, or dismissed with a
  recorded reason?
- Did the root-cause/layering pass run for every triggering candidate or fix,
  and are any reopened rows verified, refuted, or converted into questions?
- Is the selected fix layer the invariant owner or intentionally below/above
  it for a cited reason?
- Are findings derived from actual code traces rather than assumptions?
- Do proposed fixes preserve the documented contract and nearby Chromium
  idioms? Have API-shaping fixes been weighed against reasonable alternatives?
- Did the integration trace prove the code is wired into the intended runtime
  path, and did the disabled/default-path trace prove old behavior is
  preserved?
- Do tests prove the intended behavior, or merely compile/run nearby paths?
- Are prior-review findings clearly separated from new findings?
- Is any finding contradicted by another caller path, wrapper, override,
  feature flag, or test-only restriction?
- Are any findings only style preferences that should be P3 or omitted?
- Are severities calibrated for this CL's position in any larger stack?
- What did you not verify — tests not run, callers not traced, platform paths
  not checked, assumptions that still need confirmation? State these in the
  review's Verification Notes.

Scale this pass by evidence cards rather than by ingesting the entire record.
The Challenge Planner assigns no more than six finding/question cards to a
content shard and no more than 200 reconciliation rows to a structural shard,
reducing either count whenever the assigned artifacts would exceed 35% of a
known context window or the 128 KiB unknown-capacity fallback. Every item/row
appears in exactly one shard.

For a large draft, challengers consume immutable indexed draft/Gerrit sections,
not the whole assembled output. Content shards read only assigned sections,
their bounded cards, and the global frame. Structural shards read assigned row
ranges, the gate, and frame. One global shard checks section order, hashes,
headings, verdict/finding consistency, and Gerrit target coverage from compact
indexes. Each challenge row records the section hashes audited. A collector
verifies exact card/row/section coverage and exactly one `global:consistency`
token, then writes the compact challenge index.

Any draft change after challenge creates a new draft revision and requires a
new full challenge generation: fresh plan, fresh shard IDs/artifacts, and a
fresh collected index. Rechecking only the previously reported problems is not
a contradiction pass and cannot satisfy the gate. Gerrit freshness is checked
only after the last collected challenge and is rechecked after every revision.

## Verdict Alignment And Gerrit Output Rules

### Verdict Formatting

Avoid contradictory verdicts. If there is a blocking defect (P1 or P2),
the verdict must explicitly state that the change is blocked. Do not combine
approvals with blocking conditions.

- *Incorrect:* "LGTM with optional Polish (P3) after resolving one blocking
  P2 defect"
- *Correct:* "Not LGTM until the P2 telemetry bug is fixed; remaining items
  are optional P3."

### Gerrit-Ready Comments Constraints

When formatting comments meant to be copy-pasted directly to Gerrit:

- **No local paths:** Gerrit comments must never contain local absolute
  file paths (e.g. `/usr/local/...`) or local `file:///` URLs. Use
  repo-relative references only (e.g. `net/http/http_cache_writers.cc:1010`).
- **No placeholder or fake inlines:** do not output generic placeholder
  inline comments (e.g., `L16500 (General Nit) // General Nit`). General
  feedback belongs in the main comment body; inline comments must target
  real, modified lines of code.
- **Concise, query-based inlines:** frame inline feedback as questions or
  concise queries (e.g., "Can we gate these success-only metrics...?")
  rather than writing out large diff blocks, unless a specific, simple
  replacement is optimal. Avoid repeating the same suggestion across
  multiple files/declarations; place a single comment at the most relevant
  site.
- **Exhaustive coverage without truncation:** Every promoted finding (each a
  card in `synthesis/index.md`) writes one exact
  `gerrit-parts/<item>.md` target/comment fragment and measured
  `output-coverage.tsv` row; the fragment bytes occur exactly once in
  `gerrit-comments.md`. Merged duplicates are already folded into their
  surviving finding, so they need no separate comment. Do not sample,
  compress, or truncate promoted findings to shorten output length. Presenting
  100% of actionable bugs upfront is mandatory to prevent multiple review
  rounds.
- **Normalize threads before replying:** `comments.json` is keyed by file and
  contains CommentInfo arrays. Flatten with paths retained, group replies by
  transitive `in_reply_to` root, order within each thread by `updated` (stable
  ID tie-break), and take unresolved state from that thread's latest comment.
  Target the normalized root/latest IDs. Never use the last file-array element
  or the change's latest message as unresolved-thread state.
