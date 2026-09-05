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

## Per-state checklist (what the workhorse actually runs)

| State | Command | Must show before moving on |
| --- | --- | --- |
| init | `campaign.py init ... --display :1 --display-vt 9` | ledger `config.display.mode` matches the host policy |
| calibrate | two `remote_measure.py --mode aa` sessions hours apart, then `campaign.py calibrate --manifest A --manifest B` | `gate_pass`, per-story MDE table printed; floors now 2 × MDE |
| profile | two `remote_measure.py --mode profile --repetitions 32` | `stories_scope: main-thread`, `display.gpu_renderer` not SwiftShader, 100+ nominal samples per story |
| investigate | redundancy probe on the site, `redundancy_evidence.py` | packet `applicable_fraction` / `repeat_fraction` support the claimed avoidable fraction |
| decompose | `campaign.py decompose --children paths.json` | no floor or redundancy rejection; reviews cite artifacts and numbers |
| size | `mechanism_evidence.py capture` × 3+ blocks per arm, `summarize`, `advance --to sized` | avoidable-share lower bound above the story floor |
| implement | `command_evidence.py` build and test receipts, local code review | receipts bound to the staged tree, review PASS |
| measure | `remote_measure.py --mode ab --opp <id>` | family-adjusted story flags; fixed-plan verdict from `statistics_policy.py` |
| land | `advance --to landed --commit <sha> --performance-receipt <local manifest> --performance-receipt <pinpoint summary>` | local fixed-plan IMPROVEMENT on the target story, fleet IMPROVEMENT on the campaign bot |

Paste the real command output into the transcript at each step. If a step's
"must show" line is missing, stop and report it; do not reinterpret.

## Evidence layers

Keep these questions and artifacts separate:

| Question | Authoritative evidence | Never substitute |
| --- | --- | --- |
| Where is main-thread opportunity? | adapter-qualified exact scored-window, renderer main-thread story profiles (ranked by inclusive ceiling, with portability flags and score-time composition) | flat self-time, whole-page time, other threads/processes, or outer-suite samples |
| How often does the work run and repeat? | redundancy probe packet (`redundancy_evidence.py`) inside the scored window | a typed avoidable fraction |
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
   mechanism (`subtree_pruned`), and a Layer 1/2 claim binds a redundancy
   packet whose counts support the avoidable fraction.
3a. **Floors come from calibration.** A proposal's estimated target-story
   impact and a mechanism's sized lower bound must clear
   max(share floor, 2 × the story's calibrated MDE). Below that, the fixed-plan
   run cannot read the effect, so nothing downstream is worth running.
3b. **One rendering surface.** Every profile, capture and score run uses the
   display policy frozen at init; imports from another surface are rejected.
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
  --execution ssh \
  --branch <branch> \
  --feature <campaign-feature> \
  --share-floor <adapter-floor> \
  --baseline <full-sha> \
  --display :1 --display-vt 9 --viewport 1500x1000 --pause-service ollama
```

Init freezes the fixed statistical plan (32 blocks, 1% story and 0.2% suite
regression margins, alpha 0.05) and the fleet bot (`--fleet-bot`, Mac M1 PGO
by default). The minimum useful effect is raised to the calibrated MDE once
`calibrate` has run.

For SSH execution, also provide the measurement host and remote Chromium
source. For local execution, use the current checkout and never ask the runner
to check out or rewrite a ref. `--display headless` is allowed only for
diagnostic characterization; it renders through SwiftShader.

Before optimizing, run two separately timed A/A sessions and the empty-feature
null check on the campaign surface, then record the calibration:

```bash
python3 .agents/skills/optimize-campaign/scripts/remote_measure.py \
  --mode aa --ref <baseline> --blocks 32 --summary-out <aa-1.json>
# ... hours later, a second session ...
python3 .agents/skills/optimize-campaign/scripts/campaign.py calibrate \
  --manifest <aa-1 manifest> --manifest <aa-2 manifest> \
  --tolerance-pct 0.5 --max-mde-pct 3.0
```

The command prints every story's MDE and the resulting qualification floor.
Do not proceed when the calibration fails its gate or the empty feature has
measurable cost.

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
  --repetitions 32 \
  --share-floor-pct <adapter-floor> \
  --enable-features <campaign-feature> \
  --summary-out <capture.json>
```

The wrapper applies the campaign display policy, keeps ASLR on, samples at a
fixed period (about 4 kHz per CPU at the locked base clock) and scopes story
silos to the renderer main thread. Every capture must bind the campaign
benchmark and metric model, report `interval_kind: exact-scored` and
`stories_scope: main-thread`, record the campaign display identity, pass the
100-nominal-sample gate in every story, and carry unique raw capture and
artifact provenance.

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

Have the investigator analyze the story's main-thread profile, its score-time
composition and source (see `playbooks/investigator.md`):
1. **Shape first, then count.** Name which win shape the idea is (skip the
   subtree, reuse a result, change the representation, shorten a wait). For
   the first two, instrument the site with `redundancy_probe.h`, run the
   target story, and reduce the log with `redundancy_evidence.py`; the packet
   is bound at `decompose` and caps the avoidable fraction. Use
   `references/optimization-patterns.md` as an "also explore" reference
   without letting it narrow the scope; note which patterns are Mac-only.
1a. **Route the judgment call.** Send the frontier, composition and the top
   two hypotheses to the strongest available model for the architectural
   counterfactual and spec-risk pass before writing a proposal.
2. **Checkout Freshness & Durable Ledger Pre-Check:** Ensure the checkout is
   up-to-date with `origin/main`. Inspect the persistent campaign ledger
   (`ledger.json`) for prior attempts in the area.
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

Proceed only when mechanism capture is operational for the selected adapter
and the proposal's estimated impact clears the story floor; sizing must then
show an avoidable-share lower bound above the same floor.
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
scoped work reduction with total-work checks, or the separate trace-backed latency route. Scoped savings are not a net score estimate.

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

### 6. Isolated candidate evaluation and performance gates

Use [measurement-policy.md](measurement-policy.md) for the fixed-plan local
and fleet stages. Every launch is recorded in the ledger before it starts,
including failures and cancellations; the runner's manifest is the evidence
and is recomputed from raw results at import. A workload-specific primary
retains the entire default regression family.

Build and pass focused correctness checks and an independent local code review
before launching the expensive score stages. Prepare an immutable Gerrit
patchset only within the user's authorized publication scope. The Pinpoint
base and experiment must use the frozen baseline, exact Speedometer 3.1
20-workload payload, and explicit candidate feature activation on the
experiment. Record host/architecture/display differences rather than implying
identical environments. A missing metric, failed run or ambiguous result is
not a pass and is not an automatic permission to abandon a review remotely.

Advance to landed only with a local fixed-plan IMPROVEMENT manifest on the
candidate's target story and a Pinpoint IMPROVEMENT summary on the campaign
bot, plus a separately seeded confirmation for an unexpected hypothesis. Pass
repeated `--performance-receipt <file>` arguments and `--unexpected-win` when
applicable. This does not replace source review, build/test receipts,
mechanism/latency evidence or freshness requirements.

Cumulative checkpoints remain separate from isolated candidate validation.
Keep their raw manifests and fixed plans; do not use a cumulative win to rescue
an isolated candidate that failed its gates. Follow the calibrated sample
budget, full workload regression family and no-selective-retest policy.

### 7. End-of-campaign reporting, ledger tracking, and upstream CL preparation

When the campaign concludes (e.g., candidate quota reached, frontier exhausted,
or target benchmark gain achieved):

1. **Cumulative Full-Suite Sweep:**
   Run the preregistered, calibrated block-count A/B measurement sweep across all
   default benchmark workloads with all banked optimizations enabled vs. baseline HEAD.
   Record the overall geometric score delta, 95% CI, MDE, $t$-statistic, and the
   per-workload simultaneous non-inferiority bounds against preregistered margins.

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
