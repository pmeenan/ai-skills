# Optimization campaign runbook

Use this runbook for the shared campaign state machine. Read the selected
benchmark skill and reference first; they define the metric, workload set,
payload, exact scored interval, and calibrated measurement policy.

Act as the tech lead. Use scripts for joins, arithmetic, gates, and state.
Agents inspect source and fill bounded artifacts; they never estimate impact
from intuition or edit `ledger.json` directly.

The objective is reproducible positive movement in the selected benchmark's
release-role aggregate metric. `target_landed` is a planning limit, not a
success criterion. If machine-valid candidates accumulate while checkpoints
remain flat, stop producing patches and diagnose the evidence chain.

## Capability gate

Resolve these capabilities from the benchmark reference before beginning:

| Capability | Required for | If unavailable |
| --- | --- | --- |
| score parsing and immutable payload | A/A and score A/B | stop the campaign |
| exact scored-window profiling | frontier discovery | characterization only; do not import a profile |
| mechanism capture inside exact windows | sizing and candidate verification | do not advance a mechanism to `sized` |

Speedometer currently supports all three capabilities. JetStream supports
score characterization and immutable-payload score evidence, but its exact
profile and mechanism paths remain fail-closed pending end-to-end verification.

## Evidence layers

Keep these questions and artifacts separate:

| Question | Authoritative evidence | Never substitute |
| --- | --- | --- |
| Where is CPU opportunity? | adapter-qualified exact scored-window workload profiles (ranked by inclusive ceiling) | flat self-time, whole-page time, or outer-suite samples |
| Did one mechanism remove work? | paired baseline/oracle/candidate counters inside the same scored scope (`mechanism_evidence.py compare`) | profile share, source inspection, or an estimate |
| Did landed work move its targets? | randomized A/B over the preregistered target workload set | summed mechanism ceilings or a post-hoc subset |
| Did the campaign improve overall? | randomized default-suite block A/B | targeted deltas or diagnostic components |

## Shared invariants

1. Bind every artifact to `benchmark`, `metric_model`, workload selector,
   payload provenance, build role, source tree, and skill-tree digest.
2. Admit profile evidence only when the selected adapter defines and verifies
   its `exact-scored` interval. An outer suite or page interval is diagnostic.
3. Sampling profiles discover areas and provide inclusive opportunity ceilings;
   they never size a mechanism or predict benchmark movement. Sized impact must
   reflect the specific child call chains actually pruned by the proposed
   mechanism (`subtree_pruned`).
4. **Mandatory In-Situ Cycle Verification (Gate 3):** Advance to `sized` only with
   a passing artifact emitted by `mechanism_evidence.py`. Advance to review only
   with a passing paired candidate reduction artifact from the same tool. Never
   bypass Gate 3 or bundle unmeasured candidates into a macro A/B suite run.
5. **Single Authority & Strict Ban on Shadow Ledgers:** `campaign.py` and `ledger.json`
   are the sole authority for campaign progress, opportunity state transitions, and
   measured metrics. Creating untracked markdown ledgers (e.g. `OPTIMIZATION_LEDGER.md`)
   to bypass gate enforcement or schema validation is strictly prohibited.
6. **Clean Branch Candidate Isolation:** Every candidate MUST be implemented and
   measured on a clean branch created directly from baseline `origin/main` (or via
   `STAGED` on baseline HEAD) using the shared `Speedometer3Optimizations` flag.
   Measuring an unverified candidate on top of the main `speedometer` branch with
   the shared flag is strictly forbidden, as toggling the flag would activate all
   prior banked commits and falsely inflate the new candidate's numbers. Bank
   commits onto the main campaign branch only AFTER passing Gate 3 sizing and
   isolated A/B verification.
7. **One invariant per opportunity.** Implement one invariant per opportunity. Do not
   bundle unrelated fast paths, adjacent cleanup, or several speculative squeezes.
8. **Bind PASS reviews to the reviewed Git tree and exact evidence digests.**
   Generate review scaffolds; never hand-author an unbound verdict.
9. **Treat PGO, ThinLTO, symbols, frame pointers, host identity, and
   virtualization as recorded provenance rather than assumptions.**
10. **Require executable production semantics and a changed executable `.text`
    section.** Comments, tests, ledger files, and compiler-erased changes are not
    optimizations.
11. **Accept build/test receipts only from `command_evidence.py` and mechanism
    rows only from nonce-bound `mechanism_evidence.py capture` output.**
12. **Preserve specification, security, privacy, lifecycle, and behavior outside
    the campaign feature.**
13. **Use balanced randomized ABBA/BAAB blocks.** Treat each page-load repetition
    as one independent observation; nested benchmark iterations stay within it.
14. **Verify the v4 score manifest's raw-result digests, schedule positions,
    monotonic times, host, harness, workload inventory, and payload provenance;
    recompute all reported statistics.**
15. **Use the selected adapter's target-checkpoint and full-suite cadence.** A
    stale required profile or checkpoint blocks landing.
16. **Start only from a clean, committed skill repository. Audit the
    tamper-evident ledger history and artifact digests before trusting a resumed
    or completed campaign.**
17. **If a required field or artifact is unavailable, stop that opportunity.
    Never replace missing evidence with prose.**

## Files and roles

| Role | Playbook | Output |
| --- | --- | --- |
| Profiler | `playbooks/profiler.md` | independent capture summaries and a reconciled frontier |
| Investigator | `playbooks/investigator.md` | one mechanism and sizing/oracle evidence |
| Implementer | `playbooks/implementer.md` | one staged production diff and candidate evidence |
| Skeptic | `playbooks/skeptic.md` | bound effectiveness review JSON |
| Adversary | `playbooks/adversary.md` | bound correctness review JSON |
| Measurer | `playbooks/measurer.md` | A/A or A/B summary JSON |
| Gate challengers | `playbooks/gate-review.md` | independent challenge JSON |

Give each task its playbook, opportunity identity, input artifact paths, output
paths, and exact output contract. Reviewers are read-only. Only the task
holding the source-tree lease may modify or build from the campaign checkout.

Before accepting a preflight, profile, decomposition, sizing, candidate,
checkpoint, reprofile, or exhaustion gate, run independent skeptic and
adversary challenges. Give them raw artifacts, retain their real task and
transcript references, and resolve every challenge. Reviews may pause a valid
machine result; they can never waive a machine rejection.

## Initialize or resume

Work from Chromium `src`.

- If `.agents/campaigns/current/ledger.json` exists, run `campaign.py status
  --print`, then `campaign.py audit`, and resume the recorded gate.
- Otherwise select the benchmark, benchmark source, execution mode, campaign
  branch, feature, target, and adapter-calibrated share floor. Commit the skill
  repository first; initialization rejects dirty enforcement code.

```bash
python3 .agents/skills/optimize-campaign/scripts/campaign.py init \
  --name <campaign-name> \
  --benchmark <adapter-id> \
  --benchmark-source <source> \
  --execution <local-or-ssh> \
  --branch <branch> \
  --feature <campaign-feature> \
  --share-floor <adapter-floor>
```

For SSH execution, also provide the measurement host and remote Chromium
source. For local execution, use the current checkout and never ask the runner
to check out or rewrite a ref.

Before optimizing, run the adapter's A/A calibration and empty-feature null
check. Keep both runner-owned summaries. Do not proceed when the calibration
is unstable or the empty feature has measurable cost.

## Campaign loop

### 1. Capture and import a frontier

Proceed only when exact scored-window profiling is operational for the
selected adapter. Capture at least two independent profiles using the
adapter's default selector, calibrated repetitions, feature, interval model,
and quality floor:

```bash
python3 .agents/skills/optimize-campaign/scripts/remote_measure.py \
  --mode profile --benchmark <adapter-id> --ref <campaign-tip> \
  --stories <adapter-default-selector> \
  --repetitions <adapter-profile-repetitions> \
  --share-floor-pct <adapter-floor> \
  --enable-features <campaign-feature> \
  --summary-out <capture.json>
```

Every capture must bind the campaign benchmark and metric model, report
`interval_kind: exact-scored`, pass the adapter's workload-level sample gate,
and carry unique raw capture and artifact provenance.

Generate, review, and import the reconciliation:

```bash
python3 .agents/skills/optimize-campaign/scripts/campaign.py profile-scaffold \
  --capture-summaries <captures.json> --out <reconciliation.json>
python3 .agents/skills/optimize-campaign/scripts/campaign.py profile \
  --id <profile-id> --sha <campaign-tip> \
  --areas <reconciliation.json> --capture-summaries <captures.json> \
  --enable-features <campaign-feature> \
  --gate-skeptic <profile-skeptic.json> \
  --gate-adversary <profile-adversary.json>
```

Profile entries are broad discovery areas. Nested stack shares overlap; never
add them. Exclude idle/wait and payload-only shells. Keep already-landed work
visible until a follow-on profile proves its residual state.

### 2. Decompose and qualify an opportunity

Have the investigator analyze the workload-local profile and source:
1. **First-Principles Top-Down Discovery:** Decompose high-inclusive call trees
   to locate unharvested bottlenecks. Use `references/optimization-patterns.md`
   as an "also explore" inspiration reference without letting it narrow the
   investigation scope.
2. **Checkout Freshness & Durable Ledger Pre-Check:** Ensure the checkout is
   up-to-date with `origin/main`. Inspect the persistent campaign ledger
   (`OPTIMIZATION_LEDGER.md`) for prior attempts in the area.
3. **No Premature Path Closing:** If a prior attempt in an area failed or was
   discarded, do not close off the whole subsystem or function. Read the exact
   failure rationale (e.g., specific micro-check, branch overhead, or spec corner
   case); if a fundamentally different mechanism addresses the inclusive
   hotspot, continue exploring it.

Enumerate concrete paths using `decomposition.md`, and propose one testable
invariant per novel mechanism. Have the adversary challenge profile grounding,
semantics, lifecycle safety, and avoidable-work reasoning.

```bash
python3 .agents/skills/optimize-campaign/scripts/campaign.py advance \
  --opp <discovery> --to investigating
python3 .agents/skills/optimize-campaign/scripts/campaign.py decompose-scaffold \
  --opp <discovery> --out <paths.json>
python3 .agents/skills/optimize-campaign/scripts/campaign.py decompose \
  --opp <discovery> --children <paths.json> \
  --gate-skeptic <decomposition-skeptic.json> \
  --gate-adversary <decomposition-adversary.json>
```

Reuse stable `component/strategy` keys. Do not retry landed, rejected, or
reverted mechanisms without genuinely contradictory evidence.

### 3. Instrument and size one mechanism

Proceed only when mechanism capture is operational for the selected adapter.
Use `instrumented-twin.md` and `mechanism-evidence.md`. Bind the same
instrumentation-only patch across baseline, oracle, and candidate builds;
record release-like build provenance and an instrumented A/A overhead check.

Create metadata with an explicit adapter identity:

```bash
python3 .agents/skills/optimize-campaign/scripts/mechanism_evidence.py scaffold \
  --benchmark <adapter-id> --opp <id> \
  --mechanism-key <component/strategy> --profile-id <profile> \
  --target-story <workload> --min-avoidable-pct <adapter-floor> \
  --variant baseline --out <baseline.metadata-skeleton.json>
```

After attaching runner-owned build provenance, capture independent workload
blocks. The capture command also requires and cross-checks the adapter:

```bash
python3 .agents/skills/optimize-campaign/scripts/mechanism_evidence.py capture \
  --benchmark <adapter-id> --metadata <baseline.metadata.json> \
  --variant baseline --browser <instrumented-browser> \
  --block 1 --repetitions <adapter-mechanism-repetitions> \
  --enable-features <campaign-feature> \
  --out-dir <baseline-block-1> --out <baseline-capture-1.json>
```

`capture` automatically enables host tuning via `tune_benchmark_host.py` by default
(`--tune-host`), locking the base clock (3.5 GHz), disabling Turbo Boost, disabling
ASLR, and disabling SMT to minimize variance across `_rdpmc` cycle probe reads,
restoring the host upon block exit.


Ingest at least the adapter-required block count, summarize, and advance:

```bash
python3 .agents/skills/optimize-campaign/scripts/mechanism_evidence.py ingest \
  --metadata <baseline.metadata.json> \
  --capture-manifest <capture-1.json> \
  --capture-manifest <capture-2.json> \
  --capture-manifest <capture-3.json> --out <baseline.raw.json>
python3 .agents/skills/optimize-campaign/scripts/mechanism_evidence.py summarize \
  --raw <baseline.raw.json> --out <sizing.json>
python3 .agents/skills/optimize-campaign/scripts/campaign.py advance \
  --opp <id> --to sized --evidence-manifest <sizing.json> \
  --gate-skeptic <sizing-skeptic.json> \
  --gate-adversary <sizing-adversary.json>
```

The gate rejects a mechanism artifact whose benchmark or metric model differs
from the campaign ledger. An oracle is a ceiling, not permission to alter
semantics.

### 4. Implement and verify one invariant

Advance to `implementing`, preserve the temporary counters, and repeat the
same blocks with `variant: candidate`. Use `mechanism_evidence.py compare` for
the paired reduction and `command_evidence.py` for direct build and test
receipts. Advance to review only when lower confidence bounds establish both
exclusive-cycle reduction and net scored-cycle share saved.

### 5. Pre-Testing Local Code Review Gate

When an implementation is complete, compiles cleanly, and passes focused smoke checks, it is deemed **"ready to be tested"**. Before dispatching the change to the expensive remote 32-block macro measurement pipeline (128 iterations / ~1.5 hours), the candidate MUST pass a thorough offline code review via the `chromium-code-review` skill in **local mode** as a final pre-test quality gate.

#### Review Gate Protocol:
1. **Explicit Subagent Delegation:** The orchestrator agent MUST explicitly spawn a dedicated code review subagent via `invoke_subagent` (e.g. `Role: "Local Code Reviewer"`, `TypeName: "self"`) to execute the multi-phase review pipeline. Do NOT attempt to run all review phases directly in the orchestrator's main context.
2. **Local Pinning:** The review subagent runs `scripts/pin-local.sh` from `chromium-code-review`:
   ```bash
   bash .agents/skills/chromium-code-review/scripts/pin-local.sh <candidate_ref_or_sha> <baseline_ref> <review_dir>
   ```
   This creates a clean, detached read-only worktree and initializes review artifacts with `Mode: local branch`.
3. **Directives Configuration:** In `<review_dir>/directives.md`, the review MUST include:
   ```markdown
   - Mode: local branch
   - Skip test coverage: true
   - User directives: In-development optimization campaign candidate; skip reviewing for test coverage and do not flag missing unit/browser tests or test coverage gaps. Focus strictly on correctness, memory safety, lifecycle, threading, performance, and Blink invariants.
   ```
4. **Subagent Orchestration:** The review subagent executes the discovery, verification, and synthesis phases using worker subagents as specified by `chromium-code-review`. Test-related lenses (`TAS`, `FTS`) are routed to `not-applicable`.
5. **Gate Decision:**
   - **PASS:** Zero blocking findings or defects found; the candidate is certified ready for remote A/B benchmarking.
   - **FAIL / FINDINGS:** The candidate must be reworked and re-reviewed locally before any remote benchmark cycles are spent.

### 6. Isolated candidate evaluation and two-stage measurement gate

Every candidate commit is evaluated in pure isolation on a clean branch off the
scaffold baseline using a **two-stage verification funnel**:

#### Stage 1: Dedicated Bare-Metal Measurement (Exploration & Sizing)
Evaluate the candidate commit in pure isolation using the full suite (`--stories=all`)
under the aggregate feature flag on the dedicated bare-metal host (or local):

```bash
python3 .agents/skills/optimize-campaign/scripts/remote_measure.py \
  --execution ssh --mode ab --ref <candidate-sha> \
  --feature <campaign-feature> --blocks 32
```

Stage 1 confirms in-situ cycle reduction, PMU counter shifts, and initial absence of
macro regressions with rapid turnaround.

##### Automatic Benchmark Host Tuning:
`remote_measure.py` automatically enables benchmark host tuning via
`scripts/tune_benchmark_host.py` by default (`--tune-host`):
- **Timing:** Tuning is activated *after* `autoninja` compilation (ensuring builds use
  all threads and full turbo frequencies) and *before* Crossbench benchmark execution.
- **Tuning Controls:** Locks CPU clock scaling (disables Turbo Boost to prevent thermal
  stepping, locks CPU frequency to base clock, sets `performance` governor and EPP,
  disables ASLR, turns off SMT to isolate physical cores, and disables NMI watchdog).
- **Guaranteed Cleanup:** Pre-tuning host state is snapshotted to `/tmp/bench_host_tuning_state.json`.
  A shell trap (`trap ... EXIT INT TERM`) ensures host settings are always restored to their
  exact original state upon completion or failure, never leaving the machine locked.


#### Stage 2: Pinpoint Fleet Validation Gate (Fleet Checkpoint & PGO Verification)
Candidates demonstrating Stage 1 wins or strong signal advance to authoritative fleet
validation on production-configured bots (default: `mac-m1_mini_2020-perf-pgo`, 150 attempts)
using `scripts/pinpoint_measure.py`:

```bash
python3 .agents/skills/optimize-campaign/scripts/pinpoint_measure.py run \
  --benchmark speedometer3 \
  --bot mac-m1_mini_2020-perf-pgo \
  --attempts 150 \
  --out candidate_pinpoint_summary.json
```

##### Try CL Policy & Result Provenance:
- **Lightweight Try CL:** It is **completely acceptable if the Gerrit CL is NOT a full
  implementation** with feature-specific flags, enterprise toggles, or unit/browser tests at
  this stage. Its purpose is validating the isolated optimization on production PGO builds.
- **Durable Provenance:** The Gerrit CL URL (e.g. `https://chromium-review.googlesource.com/c/chromium/src/+/123456`)
  and the Pinpoint Job ID must be recorded directly in the candidate's measurement summary and
  campaign ledger, serving as the durable code foundation for the upstream landing CL if accepted.

##### Mandatory Abandonment of Failed CLs:
- If a candidate is rejected (statistically significant regression, negative score drag, or
  abandoned path), **the try CL MUST BE IMMEDIATELY ABANDONED** on Gerrit:
  ```bash
  python3 .agents/skills/optimize-campaign/scripts/pinpoint_measure.py abandon \
    --cl <gerrit_cl_url_or_number> \
    --reason "optimize-campaign: candidate failed fleet validation"
  ```
  Failed, discarded, or unviable experiment CLs must never be left open in Gerrit.

#### Acceptance Criteria (Dual Path):
1. **Targeted Improvement (Path A):**
   Demonstrates a statistically significant or clear in-situ improvement on the
   candidate's pre-registered target workload(s) without regressing other workloads.
2. **Unexpected Real Improvement (Path B):**
   Demonstrates a statistically significant improvement on untargeted workload(s),
   provided the mechanism's cross-cutting leverage is investigated and understood
   (e.g., cross-framework DOM/SVG listener overhead in WebComponent shadow roots).

#### Rejection Criteria (Strict Regression Guardrail):
- A candidate is **rejected** if it causes a statistically significant regression
  on any workload across the suite, or causes a net negative drag on the geometric mean.

#### Targeted Anomaly Confirmation Protocol:
- If a candidate flags a single-story borderline win or regression near the noise
  floor, run a fast targeted 32-block confirmation on that specific workload
  (`--stories=<flagged_story> --blocks=32`) to definitively distinguish a true effect
  from a multiple-comparison false positive before making the final accept/reject decision.

### 7. Run bound reviews

Generate skeptic and adversary review scaffolds after entering review. Each
reviewer inspects the staged diff and raw artifacts identified by the bound
digests. A PASS requires every check true and no unresolved finding. A FAIL
returns the opportunity to an allowed rework round or rejects it.

### 8. Land, checkpoint, and reprofile

Commit the exact reviewed tree to the campaign branch and record its SHA. At the adapter's cadence,
run a cumulative targeted A/B over the ledger-derived target selector and a
separate default-suite A/B for the aggregate claim and regression guardrail.

```bash
TARGETS=$(python3 .agents/skills/optimize-campaign/scripts/campaign.py checkpoint-targets)
python3 .agents/skills/optimize-campaign/scripts/remote_measure.py \
  --mode ab --benchmark <adapter-id> --ref <campaign-tip> \
  --feature <campaign-feature> --stories "$TARGETS" \
  --blocks <adapter-blocks> --summary-out <targeted-summary.json>
python3 .agents/skills/optimize-campaign/scripts/campaign.py checkpoint \
  --kind targeted --summary <targeted-summary.json> \
  --gate-skeptic <checkpoint-skeptic.json> \
  --gate-adversary <checkpoint-adversary.json>
```

Use the adapter's default workload selector for the separate full-suite
checkpoint. If a CI is too wide, use the measured MDE to preregister one larger
balanced run; never repeatedly sample fresh 95% tests until one passes.

Reprofile the enabled tip at the adapter's cadence and after repeated candidate
verification misses or a checkpoint that moves contrary to expectation.
Downstream sizing must use the residual profile, not a stale baseline.

### 7. End-of-campaign reporting, ledger tracking, and upstream CL preparation

When the campaign concludes (e.g., candidate quota reached, frontier exhausted,
or target benchmark gain achieved):

1. **Cumulative Full-Suite Sweep:**
   Run an authoritative 32-block randomized A/B measurement sweep across all
   benchmark workloads with all banked optimizations enabled vs. baseline HEAD.
   Record the overall geometric score delta, 95% CI, MDE, $t$-statistic, and the
   per-workload scorecard to verify zero stat-sig regressions.

2. **Campaign Ledger Authority & Export:**
   All opportunity state transitions, git hashes, and verified sizing/score metrics
   must be authoritatively recorded in `ledger.json` via `campaign.py`. At campaign
   close, generate `STATUS.md` and candidate summary tables directly from `ledger.json`
   linking:
   - **Opportunity ID & Optimization Index**
   - **Git Commit SHA** (on the campaign branch)
   - **Target Subsystem & Source Files** (exact file paths and functions)
   - **Target Workloads** (primary benchmark stories)
   - **Verified Isolated In-Situ Cycle Reduction & Score Delta**
   - **Upstream Landing Status** (e.g., Pending CL Series vs. Merged Upstream)
   - **Optimization Mechanism Summary**
   - **Discarded / Parked Candidates Log** with exact failure mechanics to prevent re-trying failed approaches.

3. **Multi-Tab Campaign Dossier Generation:**
   Store all reports **inside the campaign directory**
   (`.agents/campaigns/<campaign-name>/reports/`), never in the skill directory:
   - `00_OVERALL_CAMPAIGN_REPORT.md`: Executive overview, cumulative
     benchmark scorecard, per-story scorecard, candidate mapping table,
     discarded candidates log, and upstream CL landing strategy.
   - Individual candidate dossiers (`01_...md`, `02_...md`, ...): Formatted
     specifically for copy-pasting into separate tabs of a Google Document,
     containing:
     - Target subsystem, source files, and benchmark workloads
     - Problem analysis and selection rationale (from profiles)
     - Detailed C++ patch mechanics with code snippets
     - Safety, invariants, and web specification compliance
     - Measured isolated evidence, confidence intervals, and $t$-statistics

4. **Upstream CL Grouping & Landing Strategy:**
   Group the banked commits into cohesive, modular CL series by Blink
   subsystem (e.g., Canvas 2D, DOM Core, CSSOM/Selectors, HTML/Events,
   Layout Engine, Geometry/Navigation). Ensure each commit is cleanly rebased,
   preserves isolated production invariants, and includes required metadata
   tags (`TAG=agy` and `CONV=<conversation_id>`) at the bottom of the CL description.

## Stop rules

Stop and report when any condition holds:

- the selected adapter lacks a required exact evidence capability;
- exact scored capture or release-role provenance cannot be produced;
- A/A or empty-feature calibration fails;
- a persistent regression survives confirmation and bisection;
- repeated mechanisms fail the machine evidence gate;
- the fresh enabled frontier is exhausted under `campaign.py audit-exhaustion`;
- the human target is met with a sufficiently powered default-suite A/B.

Never claim aggregate improvement when the confidence interval crosses zero.
Report the point estimate, 95% CI, MDE, blocks, seed, SHAs, payload, workload
inventory, and build provenance. Run `campaign.py audit` before a final claim.

