# Synthesis And Output

This file is executed by the late-phase worker agents: the
Reconciliation-Builder, the Draft-Writer, and the Synthesis Challenger. The
severity section also binds verification skeptics, whose CONFIRMED verdicts
must name an anchor from the table below. The orchestrator does not load
this file. Artifact shapes live in `references/templates.md`; the
contradiction checklist and Gerrit output rules live in
`references/verification-and-fixes.md`.

## Contents

- Reconciliation (Phase 6)
- Drafting The Review (Phase 7)
- Finding Format
- Severity Calibration
- Output Format
- Pre-Output Gate
- Tone

## Reconciliation (Phase 6)

Synthesis produces a **reconciliation table** in `reconciliation.md` as a
required artifact: every row ID mapped to its disposition — promoted (to
finding N), refuted (with the citation), converted to a question,
merged (into row M), or clean (cited). A severity downgrade is not a terminal
disposition: the confirmed finding remains `promoted → F<number>` at its
calibrated severity. Build the table by
enumerating the row IDs present in `ledger/*.md`, `collection.md`,
`verification/*.md`, and `root-cause/*.md` — the files themselves, never a
summary of them, with no ranges and no "rest dismissed". Output is blocked
until every row has a disposition.

  In a measured run, a P1 candidate recorded by the error-path thread was
  silently dropped between ledger and review; findings reported by several
  threads survived consolidation while single-source rows vanished — the
  table exists to protect the single-source rows.

Cross-checks while building the table:

- Every verdict-bearing candidate has a verdict-consistent terminal
  disposition: CONFIRMED is promoted (`promoted → F<number>`), structurally
  merged, or assigned one of the explicit audited follow-up/note dispositions
  (`note → N<number>`, `suppressed — unchanged since prior review (...)` for
  `P3`, `pre-existing`, or justified `below round-<N> bar:` `P2` items on
  mechanically verified unchanged code — never `P1`, `subordinated → thread
  <root_id> (...)`, or
  `launch-gate note (...)`); UNPROVEN becomes an owner question
  (`question → Q<number>`), reviewer note (`note → N<number>`),
  `subordinated → thread <root_id> (...)`, or structural merge; and REFUTED is
  refuted/dismissed with its verdict or code citation, or structurally merged.
  `dismissed: duplicate` cannot bypass the merge contract.
- **Same-Reviewer Round 2+ / Round 3+ Interdiff-First Promotion Gate:** When
  `profile.json:/prior_context/reviewer_history/same_reviewer_followup` is
  `true` and `indexes/interdiff-hunks.tsv` is present, apply full promotion
  rigor to `latest_prior_reviewed_sha..revision_sha` interdiff hunks, incomplete
  fixes to posted prior comments, and regressions or new interactions triggered
  by those fixes. Meanwhile, the validator mechanically rejects promoting
  (`promoted → F<number>`) any candidate overlapping a `not-posted` `PR-<n>`
  location whose code path does not overlap `indexes/interdiff-hunks.tsv`. For
  candidates targeting code **unchanged** since `latest_prior_reviewed_sha`
  (mechanically verified not to overlap any hunk in
  `indexes/interdiff-hunks.tsv`), prevent late-round scope creep without
  dropping audit rows: (1) suppress newly discovered `P3` nits and `Origin:
  pre-existing` observations via `suppressed — unchanged since prior review
  (<V-id>)`, and suppress `CL-introduced` / earlier-round `P2` items that fall
  below the late-round bar only with an explicit justification `suppressed —
  unchanged since prior review (<V-id>, below round-<N> bar: <specific reason>)`
  (**P1** defects are strictly non-suppressible even on unchanged code — the
  validator rejects any `P1` suppression, any `P2` suppression without `below
  round-<N> bar: <reason>`, and any suppression whose location overlaps
  `indexes/interdiff-hunks.tsv`); (2) fold newly noticed pre-launch
  completeness gaps on unchanged code behind a `FEATURE_DISABLED_BY_DEFAULT`
  flag into `launch-gate note (<V-id>)`, surfaced as a non-blocking
  **Launch-Gate Note** in `FRAME.md`; (3) subordinate candidates whose scope is
  already covered by an open `reviewer decision pending` Gerrit thread via
  `subordinated → thread <root_id> (<V-id>)`; (4) route subtle edge cases or
  external-spec tensions in code implementing `Reviewer email`'s own prior
  suggestion to `note → N<number> (<V-id>)` (Reviewer Note in `draft-review.md`
  only); and (5) apply a **P1 ship-stopper bar** (reachable security/privacy
  violation, memory corruption/UAF, crash, hang, or data loss) before promoting
  any newly noticed blocker on unchanged code already reviewed by `Reviewer
  email`.
- Every serious candidate has a verdict row; a candidate with no verdict is
  an unaccounted row, not an implicit dismissal, except a candidate with an
  explicit merge proposal. A merged candidate does not need a redundant
  verdict only when reconciliation verifies the same trigger, violated
  invariant, and outcome as the survivor and cites the survivor's verdict. If
  equivalence fails, reject the merge and return the row for verification.
- Merge dispositions use exactly `merged → <survivor-row-id>` and have one
  matching `Merge equivalence` row in the templates.md shape. That row
  separately cites equal trigger, violated invariant, and outcome, plus the
  survivor's exact verdict. The survivor exists, owns a verdict, is not itself
  merged, and has the verdict-consistent terminal disposition. When both rows
  have verdicts their verdict classes match; when affinity assigned both,
  their root family matches. Free-form `merged because ...` prose is invalid.
  Equivalence cells require actual code citations or canonical artifact
  pointers whose review-relative files exist and are nonempty;
  `evidence-exception:` is not sufficient for a semantic merge.
- Every UNPROVEN verdict maps to a Questions entry (or a Reviewer Note
  `note → N<number>` / `subordinated → thread <root_id>` when applicable); every
  reopened root-cause row maps to a verdict, question, or note.
- Every row amendment is applied in order; the original row remains present
  and its disposition cites the effective amendment.
- `root-cause/batches.md` accounts for every trigger, including not-applicable
  rows with reasons.

For each promoted finding, owner question, and reviewer note, write one
immutable bounded evidence card under `synthesis/<ROW-ID>.md` in the
templates.md shape and add a manifest row to `synthesis/index.md`. Write each card using harness-native file creation tools or write a standalone script file (`cat << 'EOF' > gen_cards.py` with a quoted `'EOF'` delimiter) to avoid shell command-substitution errors on verbatim code lines containing backticks. A card is at most
`profile.json:/context_budget/evidence_card_budget_bytes`. It
contains the effective candidate row, verdict, root-cause result, merge
support, severity/origin, Gerrit-thread target, verbatim line, and caveats
needed for that item — not entire source artifacts. Every finding card also
carries the root-cause pass's Suggested edit decision. An applicable decision
includes the exact changed-side target range, verbatim selected lines, and
replacement, plus exact `Root cause` and `Root family` bindings; reconciliation
must not substitute a locally attractive snippet for an RC omission. When no
root-cause pass ran, record both bindings as `none` and the decision as omitted
because no fix was validated. An omitted decision includes a specific reason. Split excess supporting
material into numbered parts; never truncate a row. This card set,
not all verdict and ledger files, is the Draft Writer's synthesis input.

Then write the Pre-Output Gate checklist (below) verbatim at the bottom of
`reconciliation.md`, filling every line you can prove from the files
(roster, collection, matrices, per-file floor, reconciliation, verdicts,
root cause). Leave draft-dependent lines for the Draft Writer marked
`pending draft`. Mark only Freshness `pending-delivery`; it cannot be yes
until metadata is refreshed after the final challenge.

ID enumeration extracts row-definition columns/headings, including the
reopened form `R<round>-RC<batch>-<n>`; an ID merely cited inside evidence is not a new
row definition. Deduplicate the definition set before testing one-disposition
coverage.

## Drafting The Review (Phase 7)

Inputs: `reconciliation.md`, `synthesis/index.md`, assigned
`synthesis/*.md` cards, `context.md`, `pin.md`,
`directives.md`, `ledger/PR.md` (follow-ups),
`gerrit/unresolved-threads.json` (for replies to existing threads), and the
worktree for verbatim quoted lines. Write
`draft-review.md` in the Output Format below and `gerrit-comments.md` under
the Verdict Alignment And Gerrit Output Rules in
`references/verification-and-fixes.md`, then complete the remaining
pre-output gate lines in `reconciliation.md`. Producing review text while a
gate line is blank is the failure mode the gate exists to stop.

### Comprehensive Output Mandate (No-Truncation Guarantee)
To avoid multiple review rounds and ensure exhaustive feedback delivery:
- **Exhaustive coverage:** Every promoted finding, owner question, and reviewer
  note in `reconciliation.md` — equivalently, every card in
  `synthesis/index.md` — MUST have one exact `draft-parts/<item>.md` fragment
  included byte-for-byte once in `draft-review.md`; every `CL-introduced` and
  `introduced-in-PS<N>` finding also has one exact `gerrit-parts/<item>.md`
  fragment included byte-for-byte once in `gerrit-comments.md` (while questions
  `Q<number>` and reviewer notes `N<number>` use `-` for Gerrit coverage, and
  `Origin: pre-existing` findings may optionally use `-` with `Suggested edit:
  omitted — <reason>` when omitting Gerrit inline output). The measured hashes
  and paths live in `output-coverage.tsv`. The synthesis cards, not raw
  `verdicts.tsv` rows, are the coverage set: a CONFIRMED verdict that
  reconciliation merged into a survivor is represented by that survivor, an
  audited non-promoted disposition (`suppressed — unchanged since prior review`,
  `subordinated → thread <root_id>`, `launch-gate note`) is accounted in
  `reconciliation.md` (and `FRAME.md` for `launch-gate note`), and a
  severity-downgraded finding remains a promotion at its calibrated severity.
  The validator first proves reconciliation promotions/questions/notes equal the
  card index, then proves the card index equals the coverage manifest. An item
  ID in framing prose is not coverage.
- **Zero truncation or sampling:** Never cherry-pick, sample, or compress
  promoted findings into a "top priority" or "representative" subset to reduce
  draft size. Presenting a partial subset causes multiple review iterations
  and violates workflow objectives.
- **Deduplication without omission:** When multiple discovery workers report
  overlapping observations of the exact same root defect, reconciliation
  merges them into one surviving row citing all applicable code locations.
  Never discard a distinct technical defect during merging; a genuinely
  distinct defect keeps its own promoted card and finding.

The Draft Writer reads cards one at a time and does not ingest all verdict or
root-cause files. It writes the exact per-item fragments and measured
`output-coverage.tsv` rows before assembling the final outputs. If a card is
missing required evidence or conflicts with reconciliation, report the gate
failure instead of searching the entire record and silently repairing it.

The single Draft Writer path is allowed only when the card index has at most
12 cards and its assigned artifacts plus required reference sections fit the
agent input budget: at most 35% of a known context window, or 128 KiB when
capacity is unknown. Above either bound, Finding Writers produce one bounded
`draft-parts/<card>.md` plus (for findings) `gerrit-parts/<card>.md` per card,
and a Frame Writer produces `draft-parts/FRAME.md`. Draft Assembly then
combines only those parts
through a bounded tree: each node consumes at most 12 children while remaining
within the same input budget, writes a versioned intermediate, and records its
children, measured bytes, and token estimate in the assembly manifest.
Assembly may order and join framing, but per-item fragment bytes are immutable:
it must never edit, summarize, deduplicate, or omit them. It must never reopen
the corpus or change a claim, severity, origin, fix, question, or citation.
Add levels instead of exceeding a bound. Only the root writes the current
draft/Gerrit outputs and canonical coverage manifest.

With zero cards, the Frame Writer may operate in no-card root mode and write
the complete draft/Gerrit outputs directly; it still consumes context, plan,
pin, directives, and gate state and remains independently challenged. When the
root output exceeds the agent input budget, assembly emits immutable bounded
draft/Gerrit sections plus an index containing their order, byte count,
SHA-256, source cards/rows, and global-frame flag. The root outputs are exact
concatenations of the indexed sections.

Findings come from the reconciliation table's promotions — the draft writer
does not re-adjudicate verdicts. If the record looks contradictory
(a promotion without a CONFIRMED verdict, a verdict without a disposition),
that is a gate failure to report to the orchestrator, not a judgment call
to paper over.

After the synthesis challenge, any changed draft is a new numbered revision.
Archive the prior challenge index, generate fresh challenge shards over the
entire revised draft, and collect them again. Resolving the old issue list is
necessary but not sufficient: no revised draft may proceed to freshness or
delivery without a new contradiction pass.

## Finding Format

Record and report every finding with:

- **Synthesis item:** its unique `F<number>` from the reconciliation
  disposition and `synthesis/index.md`.
- **Claim:** one sentence describing concrete behavior, not vibes.
- **Location:** repo-relative `path:line` against the reviewed patchset.
- **Evidence:** the minimal state/call trace or citation that demonstrates it.
- **Severity:** P1/P2/P3 per the calibration below, naming the matched anchor.
- **Origin:** `CL-introduced`, `pre-existing`, or — in follow-up reviews —
  `introduced-in-PS<N>` for regressions the newer patchset added.
- **Fix status:** validated fix, option needing verification, or no fix
  proposed.
- **Suggested edit:** `applicable — replaces path:start-end`, followed by the
  exact fenced `suggestion` replacement, or
  `omitted — <specific reason>`. Applicability is decided and evidenced in
  the root-cause/evidence card, not improvised while drafting. The same
  replacement block must appear byte-for-byte in the Gerrit-ready comment.
- For P1/P2 findings: the smallest regression test that would have caught it.
- **Rows:** the ledger row and verdict IDs behind the finding (e.g.
  `EPW-2 / V001-1`) — an internal trail for the gate; omit it from
  Gerrit-ready text.

Record every owner question as its own exact draft fragment with non-empty
`Synthesis item` (`Q<number>`), `Question`, `Why it matters`, and `Rows`
fields. Record every reviewer note (for example, an edge case or verbatim
external-spec tension on code implementing `Reviewer email`'s own prior
suggestion) as its own exact draft fragment with non-empty `Synthesis item`
(`N<number>`), `Note`, `Why it matters`, and `Rows` fields. Questions and
reviewer notes do not get Gerrit fragment rows (`-` in `output-coverage.tsv`).

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
- Defense-in-depth checks on inputs supplied exclusively by trusted
  browser-process code (e.g. re-verifying a browser-computed staging digest,
  guarding a browser-constructed file path where a side effect inside
  `DLOG(ERROR)` is unreachable in production, or guarding against `>2 GiB`
  single-message buffers), base-interface contract discrepancies where no
  external caller can hold or mint the required token/handle, hazards that
  require a caller to violate a documented "call at most once" contract, and
  browser-side Mojo behaviors that are unreachable through normal client/Blink
  code because the primary Mojo reply already populates the client state (so
  only a compromised renderer calling a secondary Mojo method directly on a
  capability it already holds can reach the path, affecting only a resource it
  is already authorized to access) are **P3**, never P1/P2.
- Micro-optimizations and style bikeshedding below the review-noise bar—such as
  a single small string, path, or struct copy on an asynchronous IPC or disk I/O
  path, recommending `std::string_view` over `const std::string&` on a test-only
  helper called a few times, recommending `const T&` on a `base::BindOnce` /
  `PostTask` value-sink parameter, or asking to reorder methods when `.h` and
  `.cc` already match each other and follow a coherent logical grouping—must be
  marked **REFUTED** in verification rather than promoted as P3 noise.
- State propagation or bookkeeping bugs (e.g. copying a permission flag by
  value instead of sharing state) whose sole consumer method is explicitly
  unimplemented/stubbed (`TODO`, `NOTIMPLEMENTED`, `kOperationFailed`) in the
  current CL are capped at **P3** (non-blocking) and framed as "fix before or
  with the follow-up CL that implements `<consumer>`," never P1/P2.
- Missing follow-up integrations already tracked by an explicit in-code `TODO`
  (such as `BrowsingDataRemover`, storage quota enforcement, or missing
  DevTools observer wiring on Early Hints preloads) or by an open Gerrit thread
  waiting on the reviewer's own input are not new P2 blockers; defer them to
  non-blocking Questions / Notes unless the landed code causes immediate active
  harm (such as an unguarded OTR profile writing to the regular profile
  directory). When an explicit `TODO` defers cumulative quota/eviction or cap
  enforcement on a newly web-exposed write path behind a default-off feature
  flag, surface it prominently as a non-blocking **Launch-Gate Note** in the
  High-Level Summary / Next Steps and the Patchset-Level Gerrit comment rather
  than burying it or promoting it as a P1/P2 blocker.
- Never fault a CL for lacking unit tests in a file it did not modify (`pin.md`
  / `gerrit/changed-files.txt`), and never allow anchoring a finding on a
  modified `*browsertest.cc` or `*unittest.cc` file to request test coverage for
  branches in an untouched implementation file or for pre-existing validation
  guards upstream of the diff hunks (`REFUTED`). When a CL already includes a unit test for the
  changed function and/or an end-to-end test proving the primary new behavior
  works, requests for extra test permutations (such as latency/throughput cases
  in addition to offline emulation) or assertions on downstream stages
  unchanged by the CL are at most optional **P3**, never P2. However, when a CL
  introduces a new multi-branch browser-process Mojo `*Impl`, service, or storage
  backend tested only via happy-path `content_browsertests` (zero
  `*_unittest.cc` exercising validation/error/edge branches over a bound
  `mojo::Remote`), or tests portable web-exposed Blink IDL/spec behavior only via
  C++ `EvalJs` in `browsertest.cc` instead of WPTs, that missing test layer is a
  **P2** gap — consolidate all missing test-layer and test-placement findings
  into a single P2 finding rather than splitting them across multiple findings.
- Only `CL-introduced` (or `introduced-in-PS<N>`) P1/P2 findings block `LGTM`;
  `pre-existing` findings are reported for reference/follow-up only and never
  turn a review into `Not LGTM`.

Anchor table — match each finding to the nearest anchor and argue any delta
explicitly. Anchors beat intuition, especially for test-gap severity:

| Finding pattern | Severity |
| --- | --- |
| Dropped completion callback on an error path when an actual external caller, Mojo IPC response, or JS promise waits forever (vs P3 `nit:` when all production callers in the CL settle their external callback independently) | P1 (or P3 when caller-settled) |
| Success-shaped return (positive length, `OK`) after failure cleanup in a `DoLoop`-style state machine | P1 |
| Discarded accepted/written-count return (`Push`, short `Write`) — silent byte loss | P1 |
| Callback or timer bound with `Unretained` plus a reachable destroy-before-fire path | P1 |
| Documented base-interface contract clause violated by an override (buffer retention across `ERR_IO_PENDING`, `OK`-vs-byte-count semantics) | P1 |
| Implementation (and/or its unit tests) contradicts a normative clause of the governing external specification or RFC (e.g. wrong origin/site matching granularity, missing required metadata field, wrong error/exception type, or violated algorithm step) | P1 when it weakens a security/privacy/isolation boundary or corrupts persisted/wire state; P2 for functional/API spec divergence |
| Renumbered or reused values of a persisted/serialized enum | P1 |
| Zero-delay self-reposting task that busy-loops `FastForwardBy` under mock time (CI hang) | P1 |
| Restriction feature (throttle, quota, block, isolation) silently degrading to unrestricted behavior on the common path | P1; P2 when the bypass needs an uncommon mode |
| Success-only metric (duration, success count, size/ratio) logged on aborted or cancelled operations | P2 |
| Load-bearing metadata written fire-and-forget (selectable-but-corrupt state) | P2 until proven unobservable |
| Missing test coverage for the default/core mode of new behavior, or missing `*_unittest.cc` / WPT test layer for a new browser Mojo `*Impl` or web-exposed API (consolidated into one finding) | P2 |
| Extra test permutations when core new behavior is already unit-tested, or commit-message body line exceeding 72 columns | P3 |
| Async sequencing race on a single `SequenceBound<T>` FIFO runner with sticky error latching where only UI-thread callback ordering on raw Mojo IPC is affected | P3 |
| Mojom/IDL comment vs implementation mismatch behind an unenabled `Experimental` flag when a dedicated test asserts the implemented behavior and no security boundary is weakened | P3 |
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
| Defense-in-depth validation on trusted browser-internal caller inputs, caller misuse of a documented one-shot API contract, or browser-side Mojo fallback reachable only by a compromised renderer calling a secondary method directly on an already-authorized capability | P3 |
| Single non-hot-path string/path/struct copy on an async IPC/disk hop, test-only helper `std::string_view` micro-nit, `const T&` on a `BindOnce` value sink, `.h`/`.cc`-consistent callback grouping, or test-gap request targeting an untouched implementation file / pre-existing guard | REFUTED (below review-noise / scope bar) |
| State propagation / bookkeeping bug whose sole consumer method is unimplemented/stubbed (`TODO` / `kOperationFailed`) in the current CL, or base-interface / `DLOG` guard discrepancy with no reachable untrusted caller path | P3 |
| Doc/behavior mismatch on out-of-order post-`Finish()`/post-`Discard()` cleanup or redundant no-op I/O / rehash | P3 |
| Include hygiene, missing `OWNERS` file, dead enum enumerator, or internal numeric sentinel preferring `std::optional` | P3 |
| Ambiguous boolean name (policy vs state, `should_` vs `is_`) | P3 |
| Non-ASCII punctuation in comments or developer-facing prose (excluding standard `§` section symbols in spec citations) | P3 |
| Defensive hardening or opportunistic cleanup absent from the CL description | P3 (suggest split or description mention) |

## Output Format

Format the final review as:

Start with `- Draft revision: ⟨n⟩`. This control field binds the current draft
to its immutable challenge round and delivery gate; it is not Gerrit prose.

1. **CL-Introduced Issues & Suggestions:** Findings introduced by the CL, ordered
   by severity, with file/line references and actionable guidance. Separate blocking
   issues from optional polish. In follow-up reviews, label
   `introduced-in-PS<N>` findings as such within this section.
2. **Pre-Existing Codebase Issues (For Reference/Follow-up):** Issues observed
   in the surrounding codebase but not introduced by the CL. These must be clearly
   labeled as pre-existing and do not block landing of this CL.
3. **High-Level Summary:** State whether the CL accomplishes its goal, name the
   patchset and revision SHA, and summarize bug alignment (citing the exact
   `Bug:` ID(s) from `pin.md` / `context.md` verbatim; never guess or substitute
   another issue ID).
4. **Prior Review Follow-Up:** If prior issues were supplied, summarize their
   status with evidence.
5. **Positives:** Briefly note important good decisions. A praised safety
   property is a claim like any other — name its guard line. (A measured run
   praised "failures fail open safely" about the exact branch that treated a
   failure as success.)
6. **Questions (and Reviewer Notes, if any):** Only owner questions (`Q<number>`)
   whose answers affect correctness, API contract, or landing readiness. Every
   author-facing UNPROVEN verdict lands here. When reconciliation emits any
   reviewer-only note (`N<number>`, such as a subtle edge case or verbatim spec
   tension in code implementing `Reviewer email`'s own prior suggestion, with
   optional guidance on reopening the prior Gerrit thread), include a distinct
   **Reviewer Notes (Internal — Not Posted to Gerrit)** subsection in
   `draft-review.md` only. Each question and reviewer note carries its
   originating row/verdict ID trail (e.g. `Rows: AL-7 / V003-2`) — internal,
   like the finding trail; omit it from Gerrit-facing text — so the pre-output
   gate can prove no promoted card was dropped.
7. **Verification Notes:** State tests run or not run, production wiring traced
   or not traced, and any important areas not verified.
   - Name subagents by human-readable thread name (e.g. "the Error-Path Walk
     thread"), never by internal conversation IDs or task UUIDs.
   - Claim test execution only if the exact commands ran successfully against
     the pinned patchset; otherwise state: "No local test execution was
     performed during this review."
   Reproduce the full thread plan from `plan.md` with each thread's outcome:
   rows returned (count), not-applicable (with trigger-absence proof), "terminated — scope
   unreviewed", or "interrupted — partial". Include each thread's
   human-readable name (mapped to its task identifier in `plan.md`), or
   "self-executed" plus the harness limitation that forced it. A proved
   not-applicable thread is not an unverified dimension; a trigger that was
   not evaluated is `unreviewed`, never `not applicable`. Any plan deviation —
   a folded or unspawned entry, a degraded file-access
   handoff — is disclosed here as an unverified area. On large CLs the full
   compliance matrices live in the review directory with Verification Notes
   pointing at it — every per-row answer must exist somewhere retrievable; a
   "combined audit summary" that discards rows defeats the accounting. Also
   state the root-cause/layering pass outcome: candidate count checked, any
   better owner or broader invariant found, and any discovery/verification
   rows reopened because of it.
8. **Next Steps:** State what is required before `+1 LGTM` (only `CL-introduced`
   or `introduced-in-PS<N>` P1/P2 findings can block `LGTM`; `pre-existing`
   findings never block `LGTM`) and what is optional.

For full CL reviews, append compact **Gerrit-Ready Comments** unless the user
asks for a short summary only, following the Verdict Alignment And Gerrit
Output Rules section of `references/verification-and-fixes.md`:

- **Main body (`## Main comment` / `## Patchset-Level Comment`):** brief
  landing-readiness summary, blockers (`P1`/`P2`) vs optional polish (`P3`),
  any non-blocking **Launch-Gate Note** for explicit `TODO`-deferred or
  default-off pre-launch requirements (such as quota/eviction on a default-off
  feature), and prior review status. On Round 2+ follow-up reviews
  (`same_reviewer_followup: true`), keep `## Main comment` to 1–3 concise,
  natural sentences plus any `[Reviewer decision on thread <id>: Option A ... /
  Option B ...]` placeholder or brief **Launch-Gate Note** — keep exhaustive
  `file:line` lists of fixed prior comments in `draft-review.md` only. Keep
  internal `Verification Notes` (such as `"No local test execution was performed
  during this review"` or subagent audit summaries) in `draft-review.md` only —
  omit internal verification-note bullets from `gerrit-comments.md`.
- **Replies to existing unresolved threads (and controlled thread reopening):**
  file and thread line, status, and the exact response, using normalized
  root/latest IDs from `gerrit/unresolved-threads.json`. Do not open duplicate
  new threads for an existing topic. By default, never reply to a thread that is
  already resolved on Gerrit (absent from `gerrit/unresolved-threads.json`);
  the sole exception is an explicit `- Status: reopen — <reason>` (with exact
  `- Latest comment id: <id>` verified against `comments.json`) for a direct
  follow-up on a prior Gerrit thread originally authored by `Reviewer email`.
  Never attach `- Reply-To: root <root_id>, latest <latest_id>` to a `###
  path:line` inline comment whose `path` or `line` differs from the thread
  root's location, never attach unrelated new findings to a resolved thread, and
  when an open thread is awaiting a decision from the reviewer running the
  review (`Reviewer email` in `pin.md`), present a `[Reviewer decision on thread
  <id>: Option A ... / Option B ...]` placeholder in `## Main comment` instead
  of emitting an open `Q<N>` question to the CL author or writing third-person
  `"awaiting reviewer confirmation"`.
- **New inline comments:** repo-relative file (or `/COMMIT_MSG:<line>` for
  commit-message findings, where line 7 is the subject line after Gerrit's 6
  synthetic header lines), exact line or range, verbatim line
  text from the reviewed patchset, and concise author-facing comment text (1–3
  sentences stating the bug/impact and the concrete ask, without internal trace
  dumps or unmodified external subsystem `path:line` coordinates).
  When the finding's Suggested edit decision is applicable, attach the comment
  to that exact selected range and include its fenced `suggestion` block;
  Gerrit replaces the attached lines with the block contents. Prefix all P3
  optional polish comments with `nit:`.

For both `draft-review.md` and `gerrit-comments.md`, cite all code locations as
repo-relative `path:line` against the reviewed patchset, extract quoted code
verbatim, and verify every file path, line number, and backticked
function/method/variable/symbol identifier against the pinned worktree before
sending (the validator mechanically checks file existence, line-number bounds,
verbatim `- Line:` quotes, symbol existence in the cited file, and off-by-one
line citations). Neither file may ever
contain local filesystem or worktree paths (`/codereview/worktrees/`,
`/usr/local/`, `/tmp/`, `/home/`), `file://` URLs, or LaTeX math notation
(`$...$`, which Gerrit does not render — use backticked plain text such as
`` `O(entries)` `` instead). When the orchestrator renders a user-facing review
report in chat or as a conversation artifact outside `REVIEW_DIR`, strip
internal gate-accounting fields (`- **Synthesis item:**`, `- **Fix status:**`,
`- **Suggested edit:** omitted — ...`, `- **Rows:**`, severity anchor/delta
parentheticals, and the raw `plan.md` roster table) so the user receives a clean
engineering review while `REVIEW_DIR/draft-review.md` retains the full
machine-validated audit trail.

`comments.json` is a map from path to CommentInfo arrays, not a globally
ordered list. Thread targeting uses the normalized
`gerrit/unresolved-threads.json`: comments are grouped by transitive
`in_reply_to` root, ordered within that group, and unresolved state comes from
that thread's latest comment. A response records both root ID and latest ID;
never infer thread state from the last entry in a file array or the change's
latest message.

## Pre-Output Gate

Copy this checklist verbatim to the bottom of `reconciliation.md` under the
heading `## Pre-output gate`. Before the
draft, lines may be `pending draft`; before the final challenge only Freshness
may remain `pending-delivery`. Every other line is answered "yes" with a
citation or "no" with the deviation disclosed in Verification Notes. Final
delivery is blocked while any line is pending or blank.

1. **Pin:** `pin.md` exists; the review text states its patchset number and
   revision SHA.
2. **Freshness:** after the final synthesis challenge (and after every draft
   revision/re-challenge), `delivery-gate.md` records a successful Gerrit
   metadata refresh; the current PS/SHA equals the pin, an explicitly
   requested historical pin is verified in ALL_REVISIONS, or a newer trivial
   delta is recorded in `patchset-delta.md`, followed by a metadata draft
   revision and a fresh passing challenge. A material delta blocks delivery
   and restarts in a new pin.
   Reconciliation and drafting record this as `pending-delivery`; only Phase 9
   may finalize it.
3. **Plan topology:** every entry required by the active topology appears in
   `plan.md`. For `evidence-graph-v1`, both generalist passes cover the same
   complete edge partition (or both use `graph:none`) and every required graph
   continuation is present. No
   required entry is missing, bundled, or renamed.
4. **Collection:** every spawned thread has a collected `ledger/<THREAD>.md`,
   or is disclosed as terminated/interrupted with its partial rows preserved.
5. **Matrices:** no compliance-matrix row is blank or a citation-free PASS;
   each is evidence-closed, N/A-with-reason, or disclosed as unreviewed
   (per `collection.md`).
6. **Per-file floor:** every changed file has at least one ledger row
   (thread rows or `ORC` rows in `collection.md`).
7. **Reconciliation:** every row ID across `ledger/*.md`,
   `ledger/reopened/*.md`, `collection.md`, `verification/*.md`, and
   `root-cause/*.md` has exactly one disposition line — no ranges, no "rest
   dismissed".
8. **Verdicts (comprehensive and non-truncated):** authenticated budget gaps
   retain the exact `unreviewed — budget exhausted` disposition and visible
   limited-review disclosure from the templates; they are not refutations,
   owner questions, or validated merges. Every other candidate retains normal
   verification obligations, and every promoted finding
   cites a CONFIRMED verdict with its trace (or uses an audited follow-up/note
   disposition: `note → N<number>`, `suppressed — unchanged since prior review`
   for `P3`/`pre-existing` only, `subordinated → thread <root_id>`, or
   `launch-gate note`), and every promoted finding, owner question, and reviewer
   note has exactly one measured draft fragment included in draft-review.md and,
   for `CL-introduced` / `introduced-in-PS<N>` findings (plus any
   `pre-existing` finding not opting out with `-`), exactly one measured Gerrit
   fragment included in gerrit-comments.md, with reconciliation→card→coverage
   sets equal and no truncation, sampling, or
   "representative subset"; every independently refuted row cites its guard or
   safe trace; every UNPROVEN row appears in Questions (or `note → N<number>` /
   `subordinated → thread <root_id>`); every merged candidate
   either has its own verdict or has validated trigger/invariant/outcome
   equivalence to a survivor whose verdict is cited (a merged candidate is
   represented by its survivor, never dropped).
9. **Root cause:** `root-cause/batches.md` accounts for every trigger; the
   layering pass ran for every triggering candidate and
   fix; reopened rows were re-verified, refuted, or converted to questions.
10. **Severity and origin:** every finding names its anchor-table match (or
   argues the delta) and carries an origin label.
11. **Verdict consistency:** if any `CL-introduced` (or `introduced-in-PS<N>`)
    P1/P2 finding stands, the recommendation reads "not LGTM until <finding>";
    `pre-existing` findings never block `LGTM`; no approval is combined with
    blocking conditions.
12. **Gerrit text:** no local paths or `file://` URLs; no placeholder
    inlines; quoted lines re-checked verbatim against the pinned patchset;
    every applicable Suggested edit has identical apply-ready `suggestion`
    blocks in the review and Gerrit fragment, and every omitted edit names a
    specific reason;
    replies target normalized root/latest IDs from
    `gerrit/unresolved-threads.json` instead of duplicating them (or explicitly
    declare `- Status: reopen` with the exact `Latest comment id` verified
    against `comments.json`).
13. **Honesty:** the test-execution statement matches what was actually run;
    Verification Notes reproduce the plan with outcomes and human-readable
    thread names; orchestration.tsv has a terminal state for every spawned
    attempt; the current draft revision has a complete fresh challenge index.

## Tone

Follow Chromium review norms: assume competence and goodwill, lead with concrete
findings, explain why each requested change matters, ask "why" when intent is
unclear and affects correctness, label optional polish as optional, and make
landing blockers explicit.
