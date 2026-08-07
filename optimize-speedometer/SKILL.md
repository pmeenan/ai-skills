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
edits, not even temporary instrumentation). Implementation is additionally
strictly sequential at the lifecycle level: one uncommitted diff at a time,
because the working diff is what reviewers review.

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
2. Optimize as high in the call tree as one invariant permits; prefer a
   parent that controls several expensive children.
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
   (so the frontier reflects work already landed) and rebuild the punch list:
   `campaign.py add` recurrent frontier entries above the floor; `park` stale
   ledger candidates whose subtrees shrank.
2. **Investigate ahead.** Keep 2–3 investigations in flight so a sized
   dossier is always ready — their source-analysis phases overlap freely,
   but their instrumentation/oracle steps take turns holding the tree lease
   (and wait while an implementer holds it). Record results:
   `advance --to sized --ceiling X --evidence "..."` or `reject --reason`.
3. **Implement one opportunity** (`advance --to implementing`). The
   implementer squeezes the anchor fully — refinements until two consecutive
   rounds add no mechanistic benefit — then leaves the diff uncommitted
   (staged with `git add -A`) and reports. Record each refinement round with
   `campaign.py squeeze --opp N --note "..."`.
4. **Review in parallel** (`advance --to review --tests "..."` — this
   records the current HEAD and a digest of the staged diff, freezing what
   is under review): skeptic + adversary on that diff; optionally a
   story-targeted A/B from the measurer when samples concentrate (it can run
   concurrently with reviews) — measure the *candidate itself* with
   `remote_measure.py --mode ab2 --ref-a HEAD --ref-b STAGED
   --enable-features <Flag>`, which builds a provisional commit from the
   staged tree; a plain flag A/B would measure the whole cumulative campaign
   instead. Record verdicts: `campaign.py review --role ... --verdict ...`.
   - Both PASS → commit yourself: `git add -A && git commit` (message format
     below), then `advance --to landed --commit <sha>`. Landing verifies the
     commit sits directly on the reviewed base and its content matches the
     reviewed digest — if it refuses, something changed after review;
     re-review rather than reaching for `--skip-review-verification`.
   - Any FAIL → `advance --to implementing` (rework, findings attached).
     The ledger blocks a third rework round; at that point `reject` and move
     on — the findings stay recorded.
5. **Checkpoint every 3–5 landings** (measurer, `--mode ab` on branch head).
   Record with `campaign.py checkpoint`. On any stat-sig regression:
   confirm (targeted rerun), then bisect (`--mode ab2`) across the batch and
   fix or revert the guilty commit before continuing.
6. Reassess stopping rules; update the human via `STATUS.md` (regenerated
   automatically by every ledger mutation).

### Commit protocol

You (not the implementer) commit, one commit per opportunity, on the
campaign branch:

```text
[sp3] Opp #011: Skip redundant sibling-affecting style invalidation

Anchor: StyleEngine::RecalcStyle subtree (0.6% marginal share)
Evidence: 12k avoidable recalcs/run counter-verified; subtree -71% in re-profile
Reviews: skeptic PASS, adversary PASS
Tests: blink_unittests StyleEngine*, wpt css/selectors (both flag states)
```

The ledger is gitignored, so commit messages must carry these essentials —
`git log` alone reconstructs the landed list.

### Re-profiling triggers (event-driven, not scheduled)

- every ~5 landings; or
- two consecutive opportunities whose measured/instrumented reality fell far
  short of the frontier's prediction (the profile has shifted); or
- the candidate pool above the floor is exhausted.

### Stopping rules (any one)

- Target landed count reached (`target_landed`, default 20) → run the final
  measurement (measurer, 10–15 blocks + Pinpoint routing), then decide with
  the human: raise the target or conclude.
- Three consecutive opportunities rejected or evidenced-null.
- **Profile exhaustion:** a fresh re-profile's frontier has no recurrent
  candidates above the share floor — the discoverable CPU opportunity is
  consumed.
- **Statistical plateau:** two consecutive checkpoints show no gain over
  their predecessor. Respond by re-profiling first (the profile may have
  shifted); stop only if the fresh frontier is also exhausted.

Keep these two criteria separate: profile share is a *cycle-opportunity
upper bound*, not a predicted score delta — small on-CPU savings can unblock
disproportionate wall-clock score (see chrome-cycle-profiling §3.1), so
never convert remaining share into an expected score number or compare it
against the MDE. Diminishing returns are read from the checkpoint table in
`STATUS.md` (cumulative curve) alongside — not arithmetically combined
with — the remaining-frontier-share line.

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
| Profile capture (campaign state) | `--mode profile --ref <sha> --repetitions 2 --enable-features <Flag>` |
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
Skill scripts are **not** transferred: they are pre-synced to both machines,
and the job verifies a content digest before running. Exit codes: 75 = lock
busy (retry later), 4 = remote tree dirty (human intervention), 5 = skill
scripts out of sync (re-sync the skills repo on the remote host).

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
