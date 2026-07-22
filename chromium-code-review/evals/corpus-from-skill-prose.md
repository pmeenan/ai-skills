# Backlog: Measured Failures Cited In The Skill Prose

Every "a measured run…" war story in the skill text, extracted as a scoreable
expectation. Fill in the CL/patchset for each (`TODO` = not recorded here),
then promote groups of rows into per-CL files via `TEMPLATE.md`. Where a
likely CL is guessed from context it is marked "confirm" — do not treat a
guess as a pin.

Bug-class rows become **must-find findings**; process rows become **process
expectations**; trap rows become **known traps**.

## Bug-class rows (must-find candidates)

| # | measured failure | expectation | owning roster thread | skill citation | CL |
| --- | --- | --- | --- | --- | --- |
| B1 | Discarded `Push` return dropped download bytes (P0) | flag discarded accepted-count | Data Lineage / Mechanical Leads | inventory-and-planning.md Pass 3; checklists Mechanical Leads | TODO — likely socket-throttling stack (bug 496616821 / CL 8020646 series); confirm |
| B2 | Unchecked short inner `Write` dropped upload bytes (P0) | flag unchecked short write | Container/View Invalidation / Mechanical Leads | inventory-and-planning.md Pass 3 | TODO — same stack as B1; confirm |
| B3 | Per-packet delay without read-ahead collapsed throughput; 4 runs called it "intended design" | flag burst serialization; no in-thread benign adjudication | Async And Lifecycle | checklists Async; checklists intro | TODO — throttling stack; confirm |
| B4 | Upload throttle consulted only in buffer-full retry path — every fitting write unthrottled (3/4 models missed) | flag control not consulted on common path | Integration And Feature Control | checklists Integration | TODO — throttling stack; confirm |
| B5 | `kUnlimitedThroughput == 0` in one header fed `== UINT64_MAX` short-circuit in another — backpressure disabled | flag sentinel value mismatch | Mechanical Leads | checklists Mechanical Leads | TODO — throttling stack; confirm |
| B6 | Token cap applied only when queue empty — rate limit broken while work queued | probe "accumulating while consumers are queued" | Desk-Check + Arithmetic Drills | recipes Arithmetic Drills | TODO |
| B7 | Throttle charged front chunk while `Pull` crossed chunk boundaries — over-delivery (recurring) | chunk-boundary charge-vs-delivery comparison | Desk-Check + Arithmetic Drills / Async | recipes Arithmetic Drills; checklists Async | TODO — recurring in throttling stack; confirm instances |
| B8 | Success-shaped return after failure cleanup adjudicated benign in-thread; P1 crash (twice: `write_len_` after `OnCacheWriteFailure()`, double cleanup) | mandatory candidate row, never in-thread benign | Error-Path Walk | recipes Error-Path Walk; inventory-and-planning.md Writing Discovery Briefs rule 5 | TODO |
| B9 | NetworkContext gained isolated-sessions map; `ClearHttpCache`/`CloseAllConnections` still operated only on the primary session | new-container × host-admin-methods cells | Mode × Host-Capability Matrix | recipes Mode × Host | TODO |
| B10 | `ReadIfReady` impl stashed caller's `IOBuffer` in bare `raw_ptr` across `ERR_IO_PENDING` and returned positive count where `socket.h` requires `OK` (missed twice, two models) | open the base header; one matrix row per contract clause | Contracts And API Shape | checklists Contracts | TODO |
| B11 | Cell cited `ShouldTruncate()` as guard for `StopCaching(keep_entry=true)` but the guard runs only on the failure path | verify the named guard guards the cell's scenario on its path | Verification (skeptic) | verification-and-fixes Verifying | TODO |
| B12 | Failed transform init left per-entry compression decision re-evaluable on next chunk — mixed-format entry ("decided once per entry" asserted without the latch line) | name the latch line or the row is a candidate | State/Persistence/Cache | checklists State | TODO |
| B13 | Diff hunk wrapped old truncation check in `if (!new_flag)`; waved through as citation-free "PASS" | guard-bypass scan + citation-gated PASS | Mechanical Leads | inventory-and-planning.md Plan-Construction Rules / SKILL.md Phase 4 | TODO |
| B14 | Review praised "failures fail open safely" on the exact branch that treated failure as success | positives require guard-line citations | Synthesis | synthesis-and-output.md Output Format (Positives) | TODO |
| B15 | Synthesis challenger rejected real bug ("in-flight requests silently fall back to unthrottled factory") as "graceful, intended fallback" | fail-open inversion for restriction features | Verification / Synthesis | verification-and-fixes Evaluating Fixes | TODO — throttling stack; confirm |
| B16 | Success-only UMA logged for aborted/cancelled operations | cancellation cells × telemetry gating | State × Method Matrix | recipes SMM step 4 | TODO |
| B17 | `histograms.xml` summary claimed feature-restricted cohort while skipped bucket recorded standard non-feature cases | description-vs-logging audit | Integration And Feature Control | checklists Integration | TODO |
| B18 | Wire-artifact gate reasoned from plausible values ("responses carry no special marker") → production dead code | name the producing module + emitted values with path:line | Integration And Feature Control | checklists Integration | TODO |
| B19 | 2014-era leftover ref reviewed because `worktree add FETCH_HEAD` ran after a failed fetch in a `;`-chained one-liner | pin by explicit SHA; separate commands | Fetch And Pin | SKILL.md Fetch And Pin | TODO |

## Process rows (process expectations)

| # | measured failure | expectation | skill citation | CL |
| --- | --- | --- | --- | --- |
| P1 | Teardown recipe silently dropped from plan — only thread checking end-of-operation resource release | full roster verbatim in `plan.md` | inventory-and-planning.md Pass 3 | TODO |
| P2 | Large CL omitted Mode × Host matrix and both arithmetic techniques — 6 of 9 serious misses were their cells/drills | roster completeness | inventory-and-planning.md Pass 3 | TODO |
| P3 | Weak model collapsed roster into 12 invented thread names; Data Lineage + Container/View vanished (owned B1/B2) | no ad-hoc bundled thread names | inventory-and-planning.md Plan-Construction Rules / SKILL.md Phase 4 | TODO — likely CL 7707436 eval; confirm |
| P4 | Plan merged to a few recipe threads; skipped section rules accounted for the missed bugs | sections never folded into recipes | inventory-and-planning.md Plan-Construction Rules / SKILL.md Phase 4 | TODO |
| P5 | Self-executed 11 serial sweeps: 3 P1s in first fresh sweep, then starvation (pencil-whipped matrices, zero polish findings) | one subagent per triggered entry | inventory-and-planning.md Plan-Construction Rules / SKILL.md Phase 4 | TODO |
| P6 | Killed two slowest threads before they reported; lost 4 of 5 remaining P1/P2 findings | wait for every thread | inventory-and-planning.md Plan-Construction Rules / SKILL.md Phase 4 | TODO |
| P7 | Capacity-killed threads fully recovered by backoff-and-respawn | retry transient deaths | inventory-and-planning.md Plan-Construction Rules / SKILL.md Phase 4 | TODO |
| P8 | Interrupted thread marked Completed; P2 finding lost in its workspace | collect partial ledger file first | inventory-and-planning.md Plan-Construction Rules / SKILL.md Phase 4 | TODO |
| P9 | 18 threads hand-consolidated into renamed digest; 3 findings lost; reconciliation table protected the digest | collect files verbatim; dedup is a disposition | inventory-and-planning.md Plan-Construction Rules / SKILL.md Phase 4 | TODO |
| P10 | Error-path thread's P1 dropped between ledger and review; single-source rows vanished while multi-source survived | reconciliation table enumerates thread-emitted IDs | synthesis-and-output.md Reconciliation / SKILL.md Phase 6 | TODO |
| P11 | Overloaded mechanical-leads thread ran none of the greps; B1/B2/B4-class P0s were the unrun leads | run `scripts/mechanical-leads.sh` | checklists Mechanical Leads | TODO |
| P12 | Holistic thread implemented a P1's suggested fix and regression test in the owner's checkout | threads read-only outside own ledger file | inventory-and-planning.md Writing Discovery Briefs | TODO |
| P13 | Run escalated from "name the regression test" to rewriting owner's WIP and kicking off builds | review is read-only | SKILL.md Fetch And Pin | TODO |
| P14 | Generic "needs more coverage" buckets collapsed at synthesis into language naming nothing | test-gap rows name function + input class | checklists Tests As Specifications | TODO |

## Trap rows (must-not-report / must-calibrate)

| # | trap | correct disposition | skill citation | CL |
| --- | --- | --- | --- | --- |
| T1 | Untested kill-switch OFF branch that only gates memoization of an invalidation-free value reported as blocker | P3 test polish | synthesis-and-output.md anchor table | TODO — likely CL 7997557 (referrer caching); confirm |
| T2 | "Per the comment / by design / intended" used to close anomaly rows in-thread | anomalies are candidates; benignity is verification's call | checklists intro | TODO |
| T3 | Restriction-feature fallback dismissed as graceful degradation | inversion: silent unrestricted degradation is the finding | verification-and-fixes Evaluating Fixes | TODO |
| T4 | Blocking P2 combined with "LGTM" in one verdict | "Not LGTM until …" phrasing | verification-and-fixes Verdict Alignment | TODO |

## Promoted follow-up-review eval

- CL 8020646 (DelayedStreamSocket) PS4 is now pinned and scored in
  `cl-8020646.md`: all 16 prior comments were fixed; the remaining legitimate
  findings were P3-only (annotation-crossing fix untested;
  `SetBeforeConnectCallback` forwarding question). Keep this note only as the
  provenance pointer; the per-CL file is authoritative.
