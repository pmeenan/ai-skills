---
name: optimize-speedometer
description: >-
  Run a long-horizon Speedometer 3 optimization campaign in Desktop Chromium
  as a tech lead orchestrating subagents: remote profile capture,
  overlap-aware candidate discovery, a gated per-opportunity lifecycle
  (investigate, implement, skeptic + adversary review, land), a single
  campaign feature flag, batch checkpoints on a remote bare-metal machine,
  and explicit re-profiling and stopping rules. Also covers one-off use of
  the profiling/analysis pipeline.
---

# Speedometer 3 Optimization Campaign

You are the **tech lead** of a long-running optimization campaign. You
coordinate subagents that do all reading, implementation, and review; you own
the punch list, the gates, and the decisions. The campaign lands many small
optimizations — each individually **below the score noise floor** — behind
one feature flag, and measures them in aggregate.

## Roles

| Role | Playbook | Does |
| --- | --- | --- |
| Tech lead (you) | this file | punch list, gates, ledger, commits, decisions |
| Profiler | `playbooks/profiler.md` | remote captures → candidate frontier |
| Investigator | `playbooks/investigator.md` | one candidate → dossier + sizing evidence |
| Implementer | `playbooks/implementer.md` | dossier → uncommitted production diff |
| Skeptic | `playbooks/skeptic.md` | effectiveness review of the diff |
| Adversary | `playbooks/adversary.md` | spec/correctness/security/privacy review |
| Measurer | `playbooks/measurer.md` | remote A/A, A/B, checkpoints, bisects |

Spawn each subagent with: its playbook path, the specific inputs listed
there, and the instruction to honor its output contract.

**The working tree is a single exclusive resource.** Chromium's DEPS-managed
checkout makes fresh worktrees expensive (each needs a `gclient sync`), so
all agents share one tree, and only one agent at a time may dirty it — the
implementer, or an investigator running its instrumentation/oracle step. You
grant that "tree lease" explicitly and expect the tree back clean (verified
by `git status`) before granting it again. Read-only work parallelizes
freely, with one rule about *what* is read: while the tree is dirty,
non-reviewer agents must read source from the last commit (`git show
HEAD:path`, `git grep <pattern> HEAD`) so dossiers are never built against
another agent's provisional diff; only the reviewers read the dirty tree —
that diff is their review subject — and reviewers are strictly read-only (no
edits, not even temporary instrumentation). The lease also covers the
**build directories**: `out/Default` is one build environment and the build
system rejects (or races with) concurrent invocations, so only the lease
holder runs `autoninja`; a reviewer who needs a build requests it through
you and builds sequentially. Implementation is additionally strictly
sequential at the lifecycle level: one uncommitted diff at a time, because
the working diff is what reviewers review.

## One-off profiling (no campaign)

To just profile and inspect candidates without campaign machinery: run
`remote_measure.py --mode profile --ref <sha>` (or `run_cycle_benchmark.py`
directly on the measurement box), then read the returned
`candidate_frontier.md` / `opportunity_trees.txt` with
`resources/analyzer_reference.md` as the interpretation guide. No ledger, no
flag, no gates. Everything below this point assumes a full campaign.

## Context discipline (non-negotiable)

Your context must last the whole campaign.

- You read ONLY: `STATUS.md`/ledger output, `candidate_frontier.md`
  summaries, dossier summaries, review verdict JSON, and measurement summary
  JSON. You never open source files, raw diffs, opportunity trees, or perf
  data — that is subagent work.
- Subagent replies are bounded by their output contracts; if one returns a
  wall of text, extract the contract fields and drop the rest.
- All campaign state lives in the ledger (`scripts/campaign.py`), never only
  in your context. Any fresh session must be able to resume from
  `campaign.py show` + `git log` alone.

## Principles

1. A sample is a complete call stack; never turn a flat self-time list into a
   work queue. Rank by marginal, previously-uncovered samples — nested frames
   are competing explanations, not additive wins.
2. A profiled **area** and an optimization **mechanism** are different ledger
   objects. Explore areas hierarchically, fan each investigation out into
   stably-keyed mechanisms, and reject only the mechanism actually tried. A
   landing never exhausts its area; only a fresh flag-enabled follow-on profile
   can show that the residual area is below the floor.
3. Individual optimizations are expected to be sub-noise on the suite score.
   Their evidence is **mechanistic**: counters, oracle interventions, and
   sampled-cycle reduction — plus story-targeted A/B when samples
   concentrate. Suite-score movement is a *batch* property. A stat-sig
   regression anywhere, however small, is always actionable.
4. Every optimization is production quality, spec-preserving, gated behind
   the single campaign flag, and individually committed after passing both
   independent reviews and its tests.
5. Restrict changes to Chromium-owned code (no V8/ANGLE/Skia forks).
6. `out/Default` (local) for all development and tests; `out/perf` exists
   only on the remote machine and only via `remote_measure.py`. Local
   headless numbers are screening evidence; the remote bare-metal box is
   authoritative (Pinpoint for final confirmation).
7. Fidelity over latency in analysis: keep inline frames, full stacks, exact
   sample membership, complete inventories.
8. All artifacts under `scratch/` or the campaign directory — never the repo
   root.

## Session kickoff

Work from the Chromium `src` root (repo/ledger discovery is cwd-based).

- **If a campaign exists** (`.agents/campaigns/current/ledger.json`): resume
  it. Read `campaign.py status --print`, then `git log` on the campaign
  branch; do not re-ask for configuration the ledger already has, and do not
  re-run setup steps the ledger shows as done.
- **If no campaign exists**: before `init`, confirm with the human anything
  their request didn't specify — campaign name, branch, target count, remote
  host, and whether the skills are already synced on the remote host. The
  defaults below are right for the usual environment; a one-line
  confirmation beats a mis-targeted unattended run.
- **Autonomy level**: if the human didn't say how far to run, default to:
  proceed autonomously, report at every checkpoint (STATUS.md summary), and
  stop at any stopping rule or anything requiring human intervention (dirty
  remote tree, skills out of sync, regression that survives bisect).
- **Authoritative state, and only it**: this skill plus the campaign
  directory (`.agents/campaigns/<name>/` — ledger, STATUS.md, dossiers,
  reviews) are the whole truth. Speedometer-optimization guidance found
  anywhere else — planning docs in `.agents/scratch/` or `.agents/docs/`,
  old dossier pools, stale project files on either machine — is leftover
  from earlier, abandoned phases; do not follow it. Known stale markers:
  per-candidate git worktrees, a `speedometer-5pct-integration` branch,
  apply/revert probe patches, the `Speedometer3OptimizationSet` flag name,
  and `sudo` system-wide `cpu-clock` profiling.

## Campaign setup (once)

1. **Init the ledger:**

   ```bash
   python3 .agents/skills/optimize-speedometer/scripts/campaign.py init \
     --name sp3-2026-08 --branch speedometer --target 20 --share-floor 0.1 \
     --feature Speedometer3Optimizations --remote-host linux
   ```

   Config lives in `.agents/campaigns/<name>/` with `dossiers/`, `reviews/`,
   `ledger.json`, and the generated `STATUS.md`.
2. **Scaffolding commits** (implementer, on the campaign branch):
   commit 1 = the feature flag per `resources/flag_scaffolding.md`;
   commit 2 = the `[SP3_MONO_TIME]` probe so remote profiling never patches
   the remote tree.
3. **Calibrate** (measurer): remote A/A (`--mode aa`) for the session noise
   floor and MDE, then the **flag-overhead null check** (`--mode ab` on the
   scaffolding-only sha) — must be null before anything lands.

## The campaign loop

Repeat until a stopping rule fires:

1. **Frontier fresh?** If a re-profiling trigger fired (below), send the
   profiler for ≥2 independent full-suite captures **with the flag enabled**
   (so the frontier reflects work already landed) and record one reconciled
   profile group before rebuilding the punch list. The campaign tree must be
   clean and on the campaign-branch tip; profiling never overlaps an
   uncommitted implementation:

   ```bash
   campaign.py profile --id <profile-id> --sha <sha> \
     --areas <profile-reconciliation.json> \
     --capture-summaries <capture-summaries.json> \
     --enable-features <campaign-feature> \
     --artifacts "..."
   ```

   **Never hand-author the manifest from scratch.** Generate it with
   `campaign.py profile-scaffold --capture-summaries <capture-summaries.json>
   --out <profile-reconciliation.json>`: recurrence matching, source refs,
   shares, and the parked-mechanism reconciliation are mechanical joins of the
   machine inventories, so the scaffold prefills them; the profiler then only
   reviews dispositions (`discover` vs `exclude` under the admission rule) and
   supplies exclusion evidence. The manifest is a JSON object containing
   **every** recurrent coverage-frontier entry above the floor and accounting
   for every raw source entry from both captures:

   ```json
   {"areas":[
      {"area_key":"style-recalc", "anchor":"...",
       "marginal_share_pct":0.63, "disposition":"discover",
       "source_refs":[
         {"capture_id":"capture-1","entry_key":"symbol:blink::Hot"},
         {"capture_id":"capture-2","entry_key":"symbol:blink::Hot"}]},
      {"area_key":"script-dispatch", "anchor":"...",
       "marginal_share_pct":0.40, "disposition":"exclude",
       "exclusion_category":"payload-dominated",
       "exclusion_reason":"application script owns the work",
       "exclusion_evidence":"owner-exclusive share is negligible",
       "source_refs":[...]}
    ],
    "source_exclusions":[
      {"capture_id":"capture-1","entry_key":"symbol:one-off",
       "category":"not-recurrent","evidence":"absent from capture 2"}],
    "parked_mechanisms":[
      {"mechanism_key":"style/cache-rule-match",
       "disposition":"recurrent","area_key":"style-recalc"}]}
   ```

   The capture-summaries file is a JSON array of the complete JSON objects from
   at least two independent `remote_measure.py --mode profile` runs. The
   command verifies unique capture ids, distinct local/remote capture
   provenance and analyzer artifact paths, accepted quality, matching resolved
   SHA, the campaign feature, a compatible analyzer floor, and exhaustive
   machine inventories. It opens/digests each referenced analyzer JSON instead
   of trusting copied summary fields. Every raw frontier entry must appear
   exactly once as its own area's source refs from every capture, or as a
   genuinely nonrecurrent source exclusion; distinct entries cannot be
   coalesced into a coarse parent. Recurrence is judged on the digest-free
   semantic work identity: a caller-specific context whose path digest differs
   between captures—or moves between context and function representation—still
   recurs, must be reconciled as one area (its per-capture `source_refs` may
   carry different exact keys), and can never be dropped as `not-recurrent`;
   a surplus same-symbol context may be excluded as `context-variant` only
   while a sibling area covers that symbol. The manifest also explicitly reconciles
   every globally parked mechanism as recurrent (mapped to a discoverable
   area) or nonrecurrent with evidence. Stable source-entry-to-area mappings
   cannot silently change across profiles. It validates scope exclusions and
   the clean campaign-branch tip before atomically creating profile/discovery
   rows. Never hand-add only displayed top rows.

   - Do not add nested children as independent marginal frontier rows. Pass
     their parent-linked inclusive/overlap shares to the discovery investigator
     as decomposition evidence. Only `disposition: discover`
     coverage-frontier marginal shares are summed into eligible frontier share.
     Every material overlapping alternative is assigned exactly once to one
     frontier area by greatest exact overlap, even when some of it also appears
     as a related hotspot or no single parent contains 50% of it. Caller-
     specific contexts have stable path-derived keys and remain distinct.
     Exclude only leaf roots; composite payload/idle/out-of-scope shells remain
     discoveries so their material child refs receive independent dispositions.
   - A fresh profile may add another discovery for an area seen before. It
     must not retry or duplicate terminal mechanisms: decomposition matches
     globally stable `mechanism_key` values and skips paths that landed,
     rejected, or reverted, while creating only novel paths.
     A merely parked (untried) mechanism is different: rediscovery
     automatically returns that existing record to the candidate pool and
     links it to the new discovery.
   - Park stale open discoveries whose areas fell below the floor. Never infer
     area exhaustion from a landing or rejection recorded against an older
     profile.

   **Admission rule — payload-dominated shells don't enter the ledger.**
   For each frontier entry, compare owner-exclusive share to inclusive
   share (the profiler reports both per line). When owner-exclusive is a
   small fraction of inclusive and the descendants are application script,
   V8, or out-of-scope owners (Skia/ANGLE), the entry is a dispatch shell
   around mandatory payload — the benchmark's own work, which no
   parent-level invariant can avoid. Skip it; admit such an entry only when
   you can name the invariant that would let the parent avoid its payload.
   Idle-wait anchors (futex/`WaitableEvent`/worker-pool sleeps) are never
   candidates — cycles spent waiting are not eliminable work.
2. **Investigate and decompose ahead.** Keep 2–3 investigations in flight.
   Select work with `campaign.py next`, which ranks the entire materialized
   candidate pool independent of tree depth. An undecomposed discovery inherits
   the largest profiler-measured root/nested/alternative share in its work
   inventory, so a hot deep child pulls its parent decomposition ahead of a
   colder shallow area. After decomposition, each mechanism is ranked by its
   primary profiler work refs, not investigator-supplied `share_pct`. Re-run
   `next` after every decomposition and follow-on profile. A source-inspection
   mechanism `expected_value` may override measured priority only when
   accompanied by `expected_value_unit: "profile-share-equivalent-pct"`;
   express it in percentage points using the formula in
   `resources/analyzer_reference.md`.
   Mark each discovery or mechanism
   `campaign.py advance --opp N --to investigating` when you dispatch its
   investigator so STATUS.md shows it in flight. Source-analysis phases
   overlap freely, but instrumentation/oracle steps take turns holding the
   tree lease (and wait while an implementer holds it).
   - A **discovery** returns one exhaustive JSON object with matching
     `area_key`, `profile_id`, `accounting_evidence`, and a nonempty `paths`
     array. Start the investigator from `campaign.py decompose-scaffold
     --opp N --out <path>` — it emits one path row per profiler hotspot with
     the exactly-one-primary `work_refs` accounting prefilled and blank
     dispositions, so the investigator supplies only judgments. Every
     supplied hotspot/path has disposition `novel`, `known`, `covered-by`,
     `mandatory`, `below-floor`, or `out-of-scope`, plus anchor, overlap
     share, and evidence. Each path has `work_refs` to profiler
     roots/hotspots with `accounting: primary|overlap`; every expected work
     ref requires exactly one primary owner, and a primary path may cover
     only one hotspot key across captures. Thus a coarse one-row disposition
     cannot swallow distinct children — while a recursive wrapper frame whose
     samples are the same work as another path is dispositioned `covered-by`
     with `covered_by: <owner mechanism_key>`, never falsely `mandatory` and
     never a spurious sibling mechanism. Novel/known rows also have a
     globally namespaced, source-and-strategy-specific `mechanism_key`.
     Store the whole object and atomically persist it with `campaign.py
     decompose --opp N --children <path>`. The command creates novel paths,
     links known paths, records fresh observations, and reopens rediscovered
     parked paths. If a prior parked path is now below-floor/out-of-scope,
     keep its existing key on that row; the audit rejects a latest-area
     decomposition that silently omits it. A parked path whose prior
     profiler work fingerprint recurs cannot be declared nonrecurrent, and
     an existing mechanism cannot be hidden under a `mandatory` disposition:
     use `known` (which reopens it) or evidenced
     `below-floor`/`out-of-scope`.
   - After decomposition, dispatch a **skeptic exhaustion review** of the
     decomposition's `mandatory`/`out-of-scope`/`covered-by` claims — these
     close work with no other gate. Record it with `campaign.py review
     --opp N --role skeptic --verdict PASS|FAIL`. A FAIL cannot be overwritten:
     revise the decomposition by rerunning `campaign.py decompose` (existing
     child mechanisms become `known` rows), then dispatch a fresh review;
     every verdict is bound to that exact decomposition revision. Reopening
     any child also stales the verdict. Then record `campaign.py exhaust --opp N --reason "..."
     --evidence "..."` only when every child is landed/reverted/rejected.
     Evidence must be overlap-aware and tied to the current profile. The ledger
     refuses direct investigation-to-exhaustion, stale post-landing evidence,
     exhaustion without a skeptic PASS, or exhaustion while any child is
     open/parked; reopening a child automatically invalidates linked
     exhausted discoveries.
   - A **mechanism** returns sizing evidence. Record
     `campaign.py advance --opp N --to sized --ceiling X --evidence "..."` or
     `campaign.py reject --opp N --reason "..." --evidence "..."`. Reject
     requires an investigated mechanism and cannot operate on a discovery, so
     one failed hypothesis can never close an area.
   - Rejected and reverted mechanism keys remain ruled out across profiles.
     `reopen` requires both `--contradicts-prior-evidence` and a reason; use it
     only when new evidence invalidates the old conclusion, never merely
     because the containing area is hot again. A genuinely different path gets
     a new mechanism key.
3. **Implement one mechanism**
   (`campaign.py advance --opp N --to implementing`). The implementer
   squeezes that mechanism fully — refinements of the same invariant until two
   consecutive rounds add no mechanistic benefit — then leaves the diff
   uncommitted (staged with `git add -A`) and reports. A distinct invariant,
   cache, fast path, or child callee is a sibling mechanism, not a squeeze
   round. Record each same-mechanism refinement with `campaign.py squeeze
   --opp N --note "..."`.
4. **Review in parallel**
   (`campaign.py advance --opp N --to review --tests "..."` — this records
   the current HEAD and a digest of the staged diff, freezing what is under
   review): skeptic + adversary on that diff; optionally a story-targeted
   A/B from the measurer when samples concentrate (it can run concurrently
   with reviews) — measure the *candidate itself* with
   `remote_measure.py --mode ab2 --ref-a HEAD --ref-b STAGED
   --enable-features <Flag>`, which builds a provisional commit from the
   staged tree; a plain flag A/B would measure the whole cumulative campaign
   instead. Record verdicts:
   `campaign.py review --opp N --role skeptic|adversary --verdict PASS|FAIL
   [--report <path>]`.
   - Both PASS → commit yourself: `git add -A && git commit` (message format
     below), then `campaign.py advance --opp N --to landed --commit <sha>`.
     Landing verifies the commit sits directly on the reviewed base and its
     content matches the reviewed digest — if it refuses, something changed
     after review; re-review rather than reaching for
     `--skip-review-verification`.
   - Any FAIL → `campaign.py advance --opp N --to implementing` (rework,
     findings attached). The ledger blocks a third rework round; at that
     point `campaign.py reject --opp N --reason "..." --evidence "..."` and
     move to its sibling mechanisms — the findings stay recorded and the
     parent area stays open.
5. **Checkpoint every 3–5 landings** (measurer, `--mode ab` on branch head).
   Record with `campaign.py checkpoint`. On any stat-sig regression:
   confirm (targeted rerun), then bisect (`--mode ab2`) across the batch,
   then either fix forward (a new opportunity through the normal gates) or
   `git revert` the guilty commit and record it with
   `campaign.py revert --opp N --revert-commit <sha> --reason "..."` —
   which removes it from the landed count — before continuing.
6. Reassess stopping rules; update the human via `STATUS.md` (regenerated
   automatically by every ledger mutation).

### Commit protocol

You (not the implementer) commit, one commit per opportunity, on the
campaign branch:

```text
[sp3] Opp #011: Skip redundant sibling-affecting style invalidation

Anchor: StyleEngine::RecalcStyle subtree (0.6% marginal share)
Area: style-recalc
Mechanism: style-invalidation/skip-redundant-sibling-affecting
Evidence: 12k avoidable recalcs/run counter-verified; subtree -71% in re-profile
Reviews: skeptic PASS, adversary PASS
Tests: blink_unittests StyleEngine*, wpt css/selectors (both flag states)
```

The ledger is gitignored, so commit messages must carry these essentials,
including stable area/mechanism identities — `git log` alone reconstructs the
landed list.

### Re-profiling triggers (event-driven, not scheduled)

- every ~5 landings; or
- a discovery's last unresolved child finishes and at least one child landed
  (the pre-landing profile cannot establish residual exhaustion); or
- three consecutive mechanisms are rejected/evidenced-null (treat this as a
  signal that the profile or hypothesis inventory shifted, never as a reason
  to abandon their areas); or
- two consecutive opportunities whose measured/instrumented reality fell far
  short of the frontier's prediction (the profile has shifted); or
- the candidate pool above the floor is exhausted.

### Milestones and stopping rules

- Target landed count reached (`target_landed`, default 20) is a **measurement
  and reporting milestone**, not area exhaustion. Run the 10–15 block final
  measurement + Pinpoint routing and report it, but continue unless the human
  changes scope or the exhaustion rule below is also satisfied.
- Two consecutive flat checkpoints trigger re-profiling; they do not justify
  stopping while a recurrent area or untried mechanism remains.
- **Profile exhaustion is the autonomous completion rule:** every recurrent
  coverage-frontier area from the latest flag-enabled ≥2-capture profile has a
  discovery record and is evidence-exhausted, no mechanism remains active, and
  no landing/revert made that profile stale. `campaign.py audit-exhaustion`
  enforces this reconciliation and must PASS while still at the profiled clean
  branch tip. Only then is discoverable in-scope CPU opportunity consumed.
- Explicit human cancellation or a blocking external/correctness constraint
  may stop earlier; record the reason. Rejections, reversions, target count,
  and statistical plateau alone never imply opportunity exhaustion.

Keep these two criteria separate: profile share is a *cycle-opportunity
upper bound*, not a predicted score delta — small on-CPU savings can unblock
disproportionate wall-clock score (see chrome-cycle-profiling §3.1), so
never convert remaining share into an expected score number or compare it
against the MDE. Diminishing returns are read from the checkpoint table in
`STATUS.md` (cumulative curve) alongside — not arithmetically combined
with — the latest overlap-safe profile-frontier line.

## Measurement quick reference

Everything remote goes through
`python3 .agents/skills/optimize-speedometer/scripts/remote_measure.py`
(details: `playbooks/measurer.md`; statistics: the `chrome-cycle-profiling`
skill). Arguments differ by purpose — use the matching row exactly:

| Purpose | Command arguments |
| --- | --- |
| A/A noise calibration | `--mode aa --ref <sha>` |
| Flag-overhead null check | `--mode ab --feature <Flag> --ref <scaffolding-sha>` |
| Cumulative checkpoint | `--mode ab --feature <Flag> --ref <branch-head>` |
| Candidate screen (in review, staged) | `--mode ab2 --ref-a HEAD --ref-b STAGED --enable-features <Flag> --stories <stories>` |
| Landed-commit isolation | `--mode ab2 --ref-a <commit>^ --ref-b <commit> --enable-features <Flag>` |
| Regression bisect | `--mode ab2 --ref-a <good> --ref-b <suspect> --enable-features <Flag>` |
| Profile capture (campaign state) | `--mode profile --ref <sha> --repetitions 2 --enable-features <Flag> --share-floor-pct <pct> --summary-out <path>` |
| Profile capture (true baseline) | `--mode profile --ref <sha> --repetitions 2 --enable-features=""` |

Notes: `ab2` takes `--ref-a`/`--ref-b` (never `--ref`) and **always needs
`--enable-features <Flag>`** — without it both arms run baseline behavior
and flag-gated commits cannot differ. `--feature` is exclusively for `ab`
mode, which toggles it between arms. Remote host/path default from the
campaign ledger (overridable via `--host`/`--remote-src` or
`SP3_REMOTE_HOST`/`SP3_REMOTE_SRC`).

The wrapper pushes shas to the remote checkout over ssh (`refs/campaign/*`,
never upstream), builds `out/perf` there, runs under a lock, and returns
summary JSON. The remote tree must stay clean — anything that needs code
present must be committed on the branch (or staged, for `STAGED`) first.
Skill scripts are **not** transferred: the human keeps them synced on both
machines, and the job verifies a content digest before running. Exit codes:
75 = lock busy (retry later), 4 = remote tree dirty (human intervention),
5 = skill scripts out of sync — **stop and ask the human to sync; never
rsync/scp/git-push the skills repo yourself**, in either direction.

## Resuming a campaign

`campaign.py status --print` then `campaign.py show` for detail; `git log`
on the campaign branch for landed work; the last checkpoint tells you where
measurement stands. Pick up at the loop step the in-flight gates imply.

## Reference material (for subagents, not you)

- `resources/analyzer_reference.md` — frontier semantics, capture quality
  gates, visualization tools.
- `resources/flag_scaffolding.md` — flag + probe scaffolding patterns.
- `../chrome-cycle-profiling/SKILL.md` — perf capture mechanics, statistical
  protocol, correctness guardrails.
