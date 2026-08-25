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
5. Implement one invariant per opportunity. Do not bundle unrelated fast
   paths, adjacent cleanup, or several speculative squeezes.
6. Bind PASS reviews to the reviewed Git tree and exact evidence digests.
   Generate review scaffolds; never hand-author an unbound verdict.
7. Treat PGO, ThinLTO, symbols, frame pointers, host identity, and
   virtualization as recorded provenance rather than assumptions.
8. Require executable production semantics and a changed executable `.text`
   section. Comments, tests, ledger files, and compiler-erased changes are not
   optimizations.
9. Accept build/test receipts only from `command_evidence.py` and mechanism
   rows only from nonce-bound `mechanism_evidence.py capture` output.
10. Preserve specification, security, privacy, lifecycle, and behavior outside
    the campaign feature.
11. Use balanced randomized ABBA/BAAB blocks. Treat each page-load repetition
    as one independent observation; nested benchmark iterations stay within it.
12. Verify the v4 score manifest's raw-result digests, schedule positions,
    monotonic times, host, harness, workload inventory, and payload provenance;
    recompute all reported statistics.
13. Use the selected adapter's target-checkpoint and full-suite cadence. A
    stale required profile or checkpoint blocks landing.
14. Start only from a clean, committed skill repository. Audit the
    tamper-evident ledger history and artifact digests before trusting a resumed
    or completed campaign.
15. If a required field or artifact is unavailable, stop that opportunity.
    Never replace missing evidence with prose.

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

Have the investigator analyze the workload-local profile and source, enumerate
concrete paths using `decomposition.md`, and propose one testable invariant per
novel mechanism. Have the adversary challenge profile grounding, semantics,
lifecycle safety, and avoidable-work reasoning.

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

### 5. Run bound reviews

Generate skeptic and adversary review scaffolds after entering review. Each
reviewer inspects the staged diff and raw artifacts identified by the bound
digests. A PASS requires every check true and no unresolved finding. A FAIL
returns the opportunity to an allowed rework round or rejects it.

### 6. Land, checkpoint, and reprofile

Commit the exact reviewed tree and record its SHA. At the adapter's cadence,
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
