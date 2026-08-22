---
name: optimize-speedometer
description: >-
  Run a long-horizon Speedometer 3 optimization campaign in Desktop Chromium
  using exact score-window profiles, score-aware frontier discovery,
  instrumented mechanism counters, paired oracle/candidate cycle evidence,
  bound independent reviews, randomized block A/B checkpoints, and enforced
  reprofile/stopping gates. Also covers one-off Speedometer profiling.
---

# Speedometer 3 optimization campaign

Act as the tech lead. Use scripts for joins, arithmetic, gates, and state.
Agents inspect source and fill bounded artifacts; they do not estimate impact
from intuition and do not manually edit `ledger.json`.

Your objective is to **actually make Chrome faster in the symbol-free
`out/release` Speedometer score**, with a reproducible confidence interval—not
to reach `target_landed`, make STATUS green, or maximize accepted artifacts.
The target count is only a batching/planning limit. You own the aggregate
outcome: if machine-valid candidates accumulate while checkpoints stay flat,
stop producing patches and diagnose the evidence chain.

This workflow targets changes whose individual score effect is below the
benchmark noise floor. It deliberately separates three kinds of evidence:

| Question | Authoritative evidence | Never use as a substitute |
| --- | --- | --- |
| Where should we look? | exact-scored per-story silo cycle profiles | flat self-time, an outer suite window, or the full-suite diagnostic view |
| Did one mechanism remove work? | counters plus paired baseline/oracle/candidate exclusive cycles on the target story | profile share, source inspection, or a typed estimate |
| Did the landed work improve its target stories? | randomized A/B restricted to the preregistered landed target-story set | sum of candidate ceilings or a post-hoc full-suite subset |
| Did the campaign improve Speedometer overall? | randomized full-suite block A/B geomean | sum of targeted-story deltas |

## Hard invariants

1. `interval_kind` is `exact-scored`. The only admitted intervals are the
   sync and async timers used by Speedometer's score. Outer suite intervals
   are diagnostic and never contribute candidate weight.
2. Discovery uses exact-scored per-story silo analysis
   (`metric_weighting: speedometer-story-v1`): each of the 32 stories is
   analyzed in isolation, every share is relative to that story's own scored
   cycles, and frontier identities are story-qualified (`story:<name>/…`).
   The full-suite equal-weight view is diagnostic only and never sources
   campaign shares.
3. Sampling profiles discover broad areas. They never size a mechanism or
   predict score delta. The default marginal floor is 0.3%, and an analysis
   fails if the floor has fewer than 100 nominal samples.
4. A mechanism reaches `sized` only with a passing artifact emitted by
   `scripts/mechanism_evidence.py`. A candidate reaches review only with a
   passing paired candidate artifact from the same tool.
5. Implement one invariant per opportunity and commit. Do not bundle several
   “squeezes,” adjacent cleanups, or speculative fast paths.
6. A PASS review is bound to the reviewed Git tree and the exact sizing and
   verification artifact digests. Generate its checklist; never hand-author
   an unbound verdict.
7. Reprofile and record a cumulative targeted-story checkpoint after at most
   five runtime-changing landings. Record a full-suite regression checkpoint
   after the pilot and at most every ten landings thereafter. `campaign.py`
   blocks the next landing when a required artifact is stale.
8. PGO, ThinLTO, symbols, and frame-pointer state are build provenance, not
   assumptions. Profile and release builds must both be official PGO phase 2
   ThinLTO builds. Validate a mechanism in a release-like instrumented twin.
9. Chromium-owned code only. Preserve specification, security, privacy,
   lifecycle, and behavior outside the campaign flag.
10. A staged candidate must change executable production semantics and add an
    explicit campaign-feature reference on new executable lines. Comments,
    whitespace, tests, ledger artifacts, and compiler-erased no-ops are never
    an optimization; baseline and candidate executable `.text` must differ.
11. Build/test evidence comes only from `command_evidence.py`; mechanism rows
    come only from nonce-bound `mechanism_evidence.py capture` browser logs.
    Typed success strings and hand-authored counter/capture JSON are invalid.
12. The first five candidates are a fail-closed pilot. The sixth landing is
    blocked until a targeted `out/release` A/B over the exact landed
    target-story set has a positive 95% CI and a separate same-tip full-suite
    A/B shows no stat-sig regression.
13. Mechanism provenance, rebuilds, captures, and candidate build/test
    receipts run on the configured bare-metal measurement host. Their host
    name, boot id, kernel, CPU, source tree, and candidate binary must agree.
14. After the pilot, any current-tip targeted checkpoint whose 95% CI is not
    positive blocks the next landing. Any retained full-suite checkpoint with
    a stat-sig regression also blocks. Choose one larger preregistered balanced
    run from the measured MDE or diagnose/bisect; do not repeatedly peek at
    fresh 95% tests until one passes.
15. Score evidence uses the v3 runner manifest. The ledger verifies every raw
    scalar-result digest, real ABBA/BAAB position, monotonic duration, host and
    harness identity, then recomputes delta, CI, significance, and MDE.
16. Campaign init requires a clean, committed skills repository. The initial
    skill digest is bound to mechanism provenance/captures, command receipts,
    score manifests, and the tamper-evident ledger snapshot history. Run
    `campaign.py audit` before trusting a resumed or completed campaign.
    `.agents/skills` must resolve into that standalone skills Git clone;
    copied/rsynced files living only under Chromium's ignored tree are invalid.
17. Mechanism probes MUST use user-space PMU reads (`_rdpmc` via `mmap_page`)
    at ~15 cycles overhead. Synchronous kernel `read(fd)` syscalls (~1,200 cycles)
    are banned in micro-probes. Baseline and candidate probe placement MUST be
    strictly symmetric; probes must NEVER be conditionally placed inside
    `if (feature_enabled)` or optimization branches.
18. A mechanism's baseline exclusive cycle share MUST NOT exceed the total
    sample share of its enclosing function in the release `perf record` sampling
    profile (`sp3-prof-*`). Sizing artifacts that violate this physical ceiling
    fail validation automatically.
19. Mechanism probes MUST be strictly gated on `IsInScoredWindow()`. When executed
    outside Speedometer 3 scoring intervals (e.g. initial navigation, stylesheet
    parsing, unscored DOM setup, between-suite GC), probes MUST immediately return
    without reading PMU counters or accumulating cycles into the mechanism block.
    Sizing rows must be emitted only at `sp3-measurement-end` via
    `FlushSpeedometerScoreMarks()` with zero in-band I/O inside active score timers.
20. **ThinLTO & PGO Phase 2 Micro-Branching Anti-Pattern:**
    In official release configurations (`is_official_build=true`, `chrome_pgo_phase=2`,
    `use_thin_lto=true`), LLVM inlines small leaf helpers and optimizes branch layouts
    based on training profiles. Proposals and candidate diffs that attempt "micro-branch
    squeezes"—such as adding speculative early-exit checks, outer null/flag checks before
    calling an inlined function that already checks them, or vector-size/empty checks in hot
    multi-million-call loops—MUST be rejected. In practice, inserting new conditional
    branches in hot paths adds branch target buffer (BTB) pressure, pipeline mispredictions,
    and instruction cache footprint that consistently outweigh any minor skipped work,
    yielding net cycle regressions. Optimization efforts MUST focus on **Layer 1 (Subtree /
    Lifecycle Phase Elimination)** and **Layer 2 (Cross-Call State Memoization / Caching)**
    where substantial blocks of work are pruned.
21. **Per-Story Silo Focus & Target-Story Impact Ranking:**
    Speedometer 3 comprises 32 diverse framework and application workloads. Rather than
    full-suite geometric-mean weighting or dividing local story impact by 32, the campaign
    explores each story as an independent silo and ranks globally by impact on the
    opportunity's own target story:
    - **Per-Story Profile Decomposition:** Profile captures are decomposed by the analyzer
      into one silo per story (`analysis/stories/<story>/`), each down to a **0.3% local
      story marginal-share floor** with the 100-nominal-samples quality gate applied per
      story. A story below its sample floor rejects the capture — increase repetitions
      (default 16) rather than dropping the story.
    - **Target-Story Impact Ranking:** Every area and mechanism carries a `target_story`,
      and the ledger ranks all opportunities globally by
      estimated impact on that one story (local story share × avoidable fraction).
      The same symbol hot in several silos yields separate story-qualified entries, each
      ranked by its own local impact. Benefit to other stories is a bonus noted in prose;
      it is never summed into the ranking and never divided by 32.
    - **High-SNR Single-Story Sizing & Candidate Verification:** `mechanism_evidence.py`
      sizes and verifies against the mechanism's target story only
      (`--stories=<target_story>`, at least 4 repetitions per block, default 10), so
      counter shares are local to the story the change is supposed to move.
    - **Split Targeted and Full-Suite Checkpoints:** `campaign.py checkpoint-targets`
      emits the exact sorted landed target-story selector. A targeted `out/release` A/B
      over that preregistered set is the high-power landing gate. A separate full-suite
      A/B is the aggregate campaign claim and regression guardrail (mandatory for the
      pilot, then at most ten landings stale).
22. **Mandatory Remote Transfer Compression (`scp -C` / `rsync -z`):**
    The bare-metal measurement host is remote with constrained upstream/downstream bandwidth.
    Any time agents or automation scripts transfer files, patches, build logs, sizing manifests,
    or capture directories to or from the remote host, they MUST use compression flags:
    - **`scp`**: Always specify `-C` (e.g. `scp -C <src> <dest>`).
    - **`rsync`**: Always specify `-z` / `--compress` (e.g. `rsync -avz <src> <dest>`).
    Uncompressed file transfers waste bandwidth and slow iteration cycles.

If a required field or artifact is unavailable, stop that opportunity. Do
not replace missing evidence with prose.

## Files and roles

| Role | Playbook | Output |
| --- | --- | --- |
| Profiler | `playbooks/profiler.md` | two capture summaries and one reconciled frontier |
| Investigator | `playbooks/investigator.md` | one mechanism, raw counter files, sizing/oracle evidence |
| Implementer | `playbooks/implementer.md` | one staged production diff and candidate raw counters |
| Skeptic | `playbooks/skeptic.md` | bound effectiveness review JSON |
| Adversary | `playbooks/adversary.md` | bound correctness review JSON |
| Measurer | `playbooks/measurer.md` | A/A or A/B summary JSON |
| Gate challengers | `playbooks/gate_review.md` | independent skeptic and adversary challenge JSON |

Give each agent its playbook, opportunity id/key, input artifact paths, output
paths, and the instruction to return only the playbook output contract.

Before accepting **every** preflight, profile, decomposition, sizing,
candidate, checkpoint/pilot, reprofile, or exhaustion gate, run two independent
read-only challenges from `playbooks/gate_review.md`: one skeptic and one
adversary. Give them raw artifacts, not the orchestrator's summary, and keep
their conclusions independent. Resolve every CHALLENGE before advancing.
These reviews are defense in depth: they can pause a superficially valid gate,
but can never waive a machine rejection. Save their JSON under the campaign's
`reviews/gates/` directory.
Actually invoke distinct subagent tasks and retain their real task/transcript
references; never self-author both reports or fabricate reviewer signatures.
For every machine-gated command, append both
`--gate-skeptic <skeptic-challenge.json>` and
`--gate-adversary <adversary-challenge.json>`. The command verifies the exact
artifact digests and refuses missing, shared-task, CHALLENGE, or unbound files.

The Chromium tree and build directories are exclusive resources. Only the
investigator holding the instrumentation lease or the implementer may dirty
the tree. Reviewers are read-only. Do not run concurrent builds in one output
directory. Verify `git status --porcelain` before transferring the lease.

## Resume or initialize

Work from Chromium `src`.

- If `.agents/campaigns/current/ledger.json` exists, run `campaign.py status
  --print` and resume the recorded gate. Do not recreate state from prose.
- Otherwise confirm the name, branch, target, host, remote source path, and
  skill sync. A human must first commit the local skill changes; init rejects a
  dirty skills repository. Then initialize:

  ```bash
  python3 .agents/skills/optimize-speedometer/scripts/campaign.py init \
    --name sp3-YYYY-MM --branch speedometer --target 20 \
    --share-floor 0.3 --feature Speedometer3Optimizations \
    --remote-host linux
  ```

Create the feature flag using `resources/flag_scaffolding.md`. On every new
clean-slate campaign, install
`resources/performance_mark_monotonic_probe.patch` as the permanent campaign
probe. It **replaces**, rather than supplements, the legacy outer-window
`[SP3_MONO_TIME]` probe. Existing branches must remove that legacy probe and
install the exact `[SP3_SCORE_TIME]` patch before capturing a frontier. Run
`git apply --check`, compile the patched Blink target with warnings-as-errors,
and run the exact-interval smoke test. The probe intentionally leaks its
thread-local mark buffer, buffers score marks, and flushes outside score
timers. Never apply/remove it around individual remote runs.

Before optimizing, have the measurer run:

1. a fresh-seed, full-suite A/A calibration;
2. a flag-on/off null check on the scaffolding-only commit.

Keep both summary JSON files. Do not proceed if A/A is unstable or the empty
flag has a measurable cost.

Before authorizing a long campaign, run the 3–5-candidate end-to-end pilot in
`resources/instrumented_twin.md`. Continue only when the emitted-counter,
oracle, and candidate gates pass, the preregistered targeted A/B has a
positive 95% CI, and a separate same-tip full-suite A/B has no stat-sig
regression.
An inconclusive pilot permits more balanced measurement, not a sixth landing.

## Loop

Follow these steps in order. `campaign.py` is the state machine; if a command
rejects an artifact, repair or regenerate it instead of bypassing the gate.
At the end of each numbered step, run both independent gate challenges before
the next numbered step.

### 1. Capture a fresh frontier

Have the profiler produce at least two independent full-suite captures with
the campaign flag enabled, sixteen repetitions each (per-story silos need
enough samples in every story to clear their local floors):

```bash
python3 .agents/skills/optimize-speedometer/scripts/remote_measure.py \
  --mode profile --ref <campaign-tip> --stories all --repetitions 16 \
  --share-floor-pct 0.3 --enable-features Speedometer3Optimizations \
  --summary-out <capture-1.json>
```

The analyzer decomposes each capture into 32 independent story silos
(`analysis/stories/<story>/`) whose shares are local to each story's scored
cycles. Every summary must report:

- `interval_kind: exact-scored`;
- `metric_weighting: speedometer-story-v1`;
- all 32 story silos analyzed and accepted, each with at least 100 nominal
  samples at its local floor (a failing story means rerun with more
  repetitions);
- `stories: all`, matching SHA/features/floor, complete inventory, and unique
  capture/perf/artifact provenance.

Generate and review the reconciliation scaffold, then import it:

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py profile-scaffold --capture-summaries <captures.json> \
  --out <reconciliation.json>
python3 .agents/skills/optimize-speedometer/scripts/campaign.py profile --id <profile-id> --sha <campaign-tip> \
  --areas <reconciliation.json> --capture-summaries <captures.json> \
  --enable-features Speedometer3Optimizations \
  --gate-skeptic <profile-skeptic.json> \
  --gate-adversary <profile-adversary.json>
```

Profile entries are broad discovery areas. Nested stacks overlap; never add
their shares. Exclude wait/idle and payload-only shells. Keep residual work
from already-landed mechanisms visible until a follow-on profile shows it
### 2. Decompose and qualify candidate opportunities

For each candidate discovery area (a story-qualified silo entry, e.g. Style
Recalc in `TodoMVC-jQuery`, Canvas paint in `Charts-chartjs`):

1. **Invoke an Independent Investigator Subagent:**
   - The investigator analyzes the target story's own `analysis/stories/<story>/profile.collapsed` and the target subsystem using the **4-Layer Investigation Framework** in `resources/decomposition.md` (favoring Layer 1 Subtree Elimination and Layer 2 Caching/Sharing over leaf tuning). The full-suite view never sources shares.
   - Generates an Opportunity Investigation Proposal with the exact target-story stack share and estimated avoidable fraction ($\text{Estimated Target-Story Impact} = \text{Local Story Share} \times \text{Avoidable Fraction} \ge 0.30\%$ of that story).

2. **Run Independent Adversarial Candidate Qualification:**
   - An independent Adversary subagent reviews the proposal against Web specs, profile ground truth in the target story's `profile.collapsed`, lifecycle safety, and avoidable plausibility (`playbooks/adversary.md` Gate 1).
   - Only proposals that **PASS** adversarial review become official qualified candidates.

3. **Global Ranking & Sizing Gate:**
   - All qualified candidates across all story silos rank globally by **Verified Estimated Target-Story Impact (biggest to smallest)** — each entry judged only against its own target story, with any cross-story benefit left out of the ranking as a bonus. The ledger's `campaign.py next` implements this ordering.
   - We advance and instrument the top candidate in the ranking. If its mechanism key already exists from another story, link it (`known`/`covered-by`) instead of duplicating it.

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py advance --opp <discovery> --to investigating
python3 .agents/skills/optimize-speedometer/scripts/campaign.py decompose-scaffold --opp <discovery> --out <paths.json>
python3 .agents/skills/optimize-speedometer/scripts/campaign.py decompose \
  --opp <discovery> --children <paths.json> \
  --gate-skeptic <decomposition-skeptic.json> \
  --gate-adversary <decomposition-adversary.json>
```

Each novel path has one stable `component/strategy` mechanism key and one
testable invariant. “Make function faster” is not an invariant. Reuse known
keys; do not retry landed, rejected, or reverted mechanisms without genuinely
contradictory new evidence. Follow the exactly-one-primary and `covered-by`
rules in `resources/decomposition.md`.

### 3. Instrument and size the mechanism

The investigator adds temporary flag-controlled counters to a release-like
instrumented twin. Sizing runs only the mechanism's target story: emit one
row per repetition of that story inside each block (at least 4 repetitions,
default 10); the reducer gives every repetition equal weight, so shares are
local to the target story's scored cycles. Count at minimum in each row:

- calls and applicable calls;
- exclusive mechanism cycles;
- avoidable exclusive cycles, identified by a dual-path counter or oracle;
- total cycles inside the exact scored intervals;
- blocks independently, never one aggregate run.
- Minimum avoidable threshold: `avoidable_low >= 0.30%` (enforced by `mechanism_evidence.py summarize`).

Use `resources/instrumented_twin.md` for the build/probe/emission recipe and
`resources/mechanism_evidence.md` for exact field meanings.

Run provenance, mechanism captures, and command receipts directly in the
configured bare-metal campaign checkout against its fully staged tree.
`remote_measure.py` is for committed/STAGED profile and score jobs; never
substitute locally fabricated JSON for a remote staged-tree artifact.

Before every variant capture, use `bind-instrumentation` to prove the same
instrumentation-only patch maps its probe-free `product_tree` to the staged
instrumented `source_tree`. Baseline/candidate comparisons require different
product trees and binaries but the identical patch digest. Review and command
receipts bind to the probe-free candidate product tree.

Classify the work as `score-critical` or `cpu-only` using a digested trace
artifact. Raster/GPU/worker work is not score-critical merely because it is
on-CPU during an outer suite window.

Generate a metadata skeleton and fill only trace/instrumentation fields. Use
`provenance` plus `attach-provenance` for every build field; never type SHA,
tree, binary, GN, toolchain, or PGO identities. Then let `capture` run each
target-story block. Never invoke Crossbench separately or type/paste counter
rows or capture manifests:

```bash
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py scaffold --opp <id> \
  --mechanism-key <component/strategy> --profile-id <profile> \
  --target-story <story> --min-avoidable-pct 0.3 \
  --variant baseline --out <baseline.metadata-skeleton.json>
# Follow resources/instrumented_twin.md to bind the instrumentation tree,
# emit build-provenance.json, and create baseline.metadata.json.
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py capture \
  --metadata <baseline.metadata.json> --variant baseline \
  --browser out/perf_instrumented/chrome --block 1 --repetitions 10 \
  --enable-features Speedometer3Optimizations \
  --out-dir <baseline-block-1> --out <baseline-capture-1.json>
# Repeat capture for blocks 2 and 3 using distinct output paths.
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py ingest \
  --metadata <baseline.metadata.json> \
  --capture-manifest <baseline-capture-1.json> \
  --capture-manifest <baseline-capture-2.json> \
  --capture-manifest <baseline-capture-3.json> --out <baseline.raw.json>
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py summarize \
  --raw <baseline.raw.json> --out <sizing.json>
python3 .agents/skills/optimize-speedometer/scripts/campaign.py advance --opp <id> --to sized \
  --evidence-manifest <sizing.json> \
  --gate-skeptic <sizing-skeptic.json> \
  --gate-adversary <sizing-adversary.json>
```

The capture runner verifies a staged source tree, browser/GN digest, fresh
nonce, the exact target story's score marks (and only that story), natural
run variance, and the byte-exact extraction from raw browser logs. The stored
bound is an upper confidence bound on the avoidable share of the target
story's scored CPU cycles, not a predicted score delta. Use at least three
blocks. Record full build identity, GN-args digest,
toolchain id, PGO-profile digest, probe revision, probe A/A overhead, and the
trace digest. Probe A/A overhead above 1% fails the artifact.

When feasible, implement an intentionally incorrect oracle that bypasses only
the proposed work. Compare it with the same blocks:

```bash
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py compare --kind oracle \
  --baseline <baseline.raw.json> --variant <oracle.raw.json> \
  --out <oracle.json>
```

An oracle is a ceiling, not permission to change semantics. Reject the path
if applicability is low, the oracle does not remove exclusive cycles, or the
work is off the scored critical path and no CPU-only goal justifies it.

### 4. Implement and verify exactly one invariant

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py advance --opp <id> --to implementing
```

The implementer preserves the temporary counters while developing and repeats the same blocks with
`variant: candidate`. Validate the paired reduction:

```bash
python3 .agents/skills/optimize-speedometer/scripts/mechanism_evidence.py compare --kind candidate \
  --baseline <baseline.raw.json> --variant <candidate.raw.json> \
  --out <candidate.json>
python3 .agents/skills/optimize-speedometer/scripts/command_evidence.py \
  --kind build --out <build.json> -- autoninja -C out/perf <test-binary-target>
python3 .agents/skills/optimize-speedometer/scripts/command_evidence.py \
  --kind test --out <test.json> -- out/perf/<test-binary> <focused-args>
python3 .agents/skills/optimize-speedometer/scripts/campaign.py advance \
  --opp <id> --to review --build-manifest <build.json> \
  --test-manifest <test.json> --verification-manifest <candidate.json> \
  --gate-skeptic <candidate-skeptic.json> \
  --gate-adversary <candidate-adversary.json>
```

Run both receipt commands on the same configured bare-metal host and boot as
the candidate mechanism capture. The build runner accepts only tracked
Chromium depot_tools `autoninja`; the test runner accepts only an ELF test
binary under this checkout's `out/` that reports at least one passing gtest.
The build receipt must explicitly name that test-binary target. The ledger
rejects host, tree, tool, binary, and skill-digest mismatches.

The lower 95% confidence bounds for both relative exclusive-cycle reduction
and net scored-cycle share saved must be positive. Inspect
`total_scored_cycle_change_ci95_pct`; a `moved_work_warning` cannot be called
net work removal without resolving where total work moved. Remove temporary
probes from the staged production diff unless the instrumentation is an
intentional, reviewed product metric.

### 5. Run bound reviews

For each role, generate the report after entering review:

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py review-scaffold --opp <id> --role skeptic \
  --out <skeptic.json>
python3 .agents/skills/optimize-speedometer/scripts/campaign.py review-scaffold --opp <id> --role adversary \
  --out <adversary.json>
```

Reviewers inspect the staged diff and raw artifacts referenced by their
digests, set every bounded check to JSON `true` only when verified, replace
every `check_evidence` and notes placeholder with artifact-specific reasoning,
add findings, and set the verdict. Record it:

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py review --opp <id> --role skeptic --verdict PASS \
  --report <skeptic.json>
python3 .agents/skills/optimize-speedometer/scripts/campaign.py review --opp <id> --role adversary --verdict PASS \
  --report <adversary.json>
```

A PASS requires all checks true and no findings. A FAIL returns to one of at
most two rework rounds or rejects the mechanism.

### 6. Land, checkpoint, and reprofile

Commit the exact reviewed tree and record it:

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py advance --opp <id> --to landed --commit <sha>
```

After at most five landings, print the ledger-derived target selector and run
a cumulative flag A/B restricted to that exact set. This targeted checkpoint
is the landing efficacy gate. For the pilot, also run a separate same-tip
full-suite checkpoint; afterward the full-suite regression/aggregate-claim
checkpoint may be at most ten landings stale. Both use symbol-free official
PGO2/ThinLTO `out/release`, a fresh recorded seed, and at least 32 balanced
blocks. Record machine output, not copied numbers:

```bash
TARGETS=$(python3 .agents/skills/optimize-speedometer/scripts/campaign.py checkpoint-targets)
python3 .agents/skills/optimize-speedometer/scripts/remote_measure.py \
  --mode ab --ref <campaign-tip> --feature Speedometer3Optimizations \
  --stories "$TARGETS" --blocks 32 --summary-out <targeted-ab-summary.json>
python3 .agents/skills/optimize-speedometer/scripts/campaign.py checkpoint \
  --kind targeted --summary <targeted-ab-summary.json> \
  --gate-skeptic <checkpoint-skeptic.json> \
  --gate-adversary <checkpoint-adversary.json>

# Required at the pilot tip and whenever the ten-landing full-suite cadence is due.
python3 .agents/skills/optimize-speedometer/scripts/remote_measure.py \
  --mode ab --ref <campaign-tip> --feature Speedometer3Optimizations \
  --stories all --blocks 32 --summary-out <full-suite-ab-summary.json>
python3 .agents/skills/optimize-speedometer/scripts/campaign.py checkpoint \
  --kind full-suite --summary <full-suite-ab-summary.json> \
  --gate-skeptic <full-checkpoint-skeptic.json> \
  --gate-adversary <full-checkpoint-adversary.json>
```

Thirty-two blocks means 128 repetitions of the selected story set. Full-suite
runs have a 64-minute hard duration floor and may take several hours. If the
targeted CI is too wide, use its MDE to choose one larger preregistered balanced
confirmation run; do not repeatedly test fresh runs until one is favorable.
The ledger rejects a same-size confirmation, a third targeted look at the same
campaign tip, and any duplicate same-tip full-suite checkpoint.

Also reprofile the enabled campaign tip after at most five runtime changes,
and immediately after two candidate verification misses or a checkpoint that
does not move in the expected direction. Downstream mechanisms must be sized
against the residual profile, not a stale baseline.

When all child paths of a discovery are terminal, generate and record the
digest-bound skeptic exhaustion review, then run `campaign.py exhaust` as
shown in `resources/decomposition.md`. Unbound discovery prose cannot retire
profiled work.

## Stop rules

Stop and report when any condition holds:

- an exact-scored capture or build provenance cannot be produced;
- A/A or empty-flag calibration fails;
- a persistent regression survives confirmation and bisect;
- three consecutive mechanisms fail the machine evidence gate;
- the fresh enabled frontier is exhausted under `campaign.py audit-exhaustion`;
- the human target is met with a sufficiently powered full-suite A/B.

Do not claim an aggregate improvement when the confidence interval crosses
zero. Report the point estimate, 95% CI, MDE, blocks, seed, SHAs, and build
provenance.
Before any final claim, run `campaign.py audit`; a changed skill tree,
snapshot, raw result, receipt, review, or evidence artifact invalidates it.

## One-off profiling

For discovery only, run `remote_measure.py --mode profile` as above and read
`candidate_frontier.md` plus `resources/analyzer_reference.md`. Do not use a
one-off profile share as an optimization forecast.
