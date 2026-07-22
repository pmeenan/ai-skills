# Scaling And Compact Indexes

Use this contract to scale effort without weakening coverage or overfilling an
agent context. The deterministic helpers produce routing evidence; workers
still make semantic review decisions.

## Contents

- [Agent Input Budget](#agent-input-budget)
- [Model Tiers](#model-tiers)
- [Review Profile](#review-profile)
- [Compact Indexes](#compact-indexes)
- [Safe Fast Paths](#safe-fast-paths)
- [Sharded Aggregation](#sharded-aggregation)

## Agent Input Budget

Before generating a brief, estimate the bytes or tokens of every assigned
artifact and required reference section. When the harness exposes context
capacity, assigned input may consume at most 35% of it. Use a tokenizer when
available and a conservative four-bytes-per-token estimate otherwise. When
capacity is unknown, use 128 KiB as the assigned-artifact ceiling. The limit
excludes neither repeated headers nor reference text: count everything the
worker must load. Leave the remaining context for code, tool output, reasoning,
and the deliverable.

If a unit exceeds the budget, shard it by a named natural unit before spawn.
If an already-running worker discovers deeper-than-profiled work, it writes a
full-quality partial artifact plus exact remaining scope and yields to a fresh
continuation. Never compress evidence or reduce the checklist to fit.

## Model Tiers

Every phase brief in `phase-briefs.md` carries a `Tier:` annotation, and every
`spawn` row in `plan.md` carries a `tier` column. The tier names the least
capable model class the task tolerates. Tiers are capability descriptions,
never model names — the orchestrator resolves them inside whatever family the
harness offers:

| tier | capability semantics | resolve to (illustrative, non-normative) | thinking/reasoning setting |
| --- | --- | --- | --- |
| `mechanical` | exact rule-following over small structured inputs: union/uniqueness checks, ordered concatenation, single-line mutations, schema-shaped extraction. No open-ended code reasoning. | the smallest/fastest model offered alongside the session model (Haiku-class, Flash-Lite/Flash-class, mini-class) | minimal or none |
| `standard` | structured enumeration and classification, summarization/distillation, prose rendered from an already-verified evidence record, audits against deterministic checklists | the session's default model or a mid-tier family member (Sonnet-class, Flash-class) | harness default |
| `frontier` | adversarial code tracing, interleaving/lifetime/ownership reasoning, invariant-owner and layering judgment, refutation, contradiction hunting, roster/scoping judgment | the strongest model the harness offers (Opus/Fable-class, Pro-class, high-reasoning-class), with the highest available thinking or reasoning setting | maximum available |

Rules:

- **A tier is a floor, not a target.** Running a task above its tier wastes
  money but never correctness; running a `frontier` task below its tier is a
  measured quality failure — the eval corpus records weak-model runs whose
  collapsed rosters and citation-free matrices missed exactly the P0s the
  deep-trace threads own.
- Generated analytical workers have contract tiers the orchestrator applies
  without reading their briefs: discovery threads take the tier from their
  `plan.md` row; verification skeptics, root-cause challengers, and synthesis
  challengers are always `frontier`; continuations and repairs inherit the
  tier of the work they continue.
- The orchestrator itself is `standard` or higher — never delegate
  orchestration to a `mechanical`-class model.
- **If the harness cannot select per-subagent models or thinking levels,
  every worker inherits the session model and the annotations are a no-op.**
  Never block or degrade a review because tier selection is unavailable.
- The user may set a cost preference in `directives.md` (e.g. "run this at
  flash-level", "pro-level only for verification"). Honor it, but record the
  deviation, and Verification Notes must disclose every phase that ran below
  its recommended tier. Deep-dive recipe threads, specialist trace threads,
  and verification skeptics are the last to downgrade.

## Review Profile

Run `scripts/profile-review.py` immediately after pinning. It writes
`profile.json` and `profile.md` from the exact pinned diff and normalized
metadata. Treat its class as a conservative lower bound that Inventory may
escalate but never downgrade without cited proof.

- `micro`: eligible only when the helper proves all changed paths are
  non-executable documentation/metadata and finds no API, BUILD, feature,
  async, state, persistence, security, performance, prior-feedback, or
  unresolved-comment signal. Low line count alone never qualifies.
- `standard`: the default when no high-risk or large trigger is proved.
- `high-risk`: any contract/API, behavior-changing feature gate,
  async/lifecycle, ownership/GC, state-machine/state-holder,
  cache/persistence, security/privacy, threading, performance, or flaky-test
  signal. Build/generated/language/telemetry file types route specialists but
  require an independent behavior-sensitive signal to escalate.
- `large`: the diff or predicted natural trace units require sharding—roughly
  more than 40 files, 4,000 changed lines, 15 files/1,500 lines in a file-shaped
  lens, 8–10 path walks, 40 matrix cells, or any estimated input above the
  agent budget. Record high-risk signals independently when both apply.

Profile class changes topology, not review truth. The full roster decision,
per-file floor, reconciliation, independent challenge, and delivery freshness
remain mandatory. A micro profile may use the fast paths below only after
Inventory confirms the profile's proof.

## Compact Indexes

Run `scripts/build-review-indexes.py` after each producer phase. Index files are
derived views, atomically regenerated from canonical artifacts; they never
replace or amend those artifacts. They live under `indexes/` with a
source-fingerprint manifest.

- `indexes/inventory.tsv`: kind, stable scope/surface ID, subject, scope,
  tags (including `root-cause-required=yes|no`), citations, and canonical source.
- `indexes/candidates.tsv`: candidate ID, claim/location, origin, severity,
  effective status/amendment evidence, citations, and canonical source.
- `indexes/verdicts.tsv`: verdict ID, candidate ID, verdict, severity/origin,
  citations/evidence excerpt, and canonical source.
- `indexes/reconciliation.tsv`: every canonical row ID, kind, source path,
  effective amendment, candidate/verdict/root-cause links, and disposition
  state.

Planners read an index first, select bounded IDs, and open only the canonical
row bodies needed for judgment. Validators recompute indexes or compare their
source fingerprints before accepting them; stale or incomplete indexes block
the fast path.

## Safe Fast Paths

Fast paths remove mechanical control-plane agents, never analytical coverage:

- Run `extract-unresolved-comments.py` directly; do not spawn an agent merely
  to execute it.
- Only when `profile.json` sets `context_fast_path_eligible: true`, create the
  empty-source `context.md` skeleton mechanically. Inventory and the always-run
  holistic lens still audit description alignment and scope. Otherwise use the
  Context worker, sharding external sources when their extracts exceed budget.
- When a fresh `indexes/candidates.tsv` has zero rows and Collection passed, write the
  canonical empty verification plan and skip Verification Planner/skeptics.
- When `indexes/verdicts.tsv` has zero data rows and
  `indexes/inventory.tsv` has no
  root-cause-required scope, write canonical empty Trigger Accounting and skip
  Root-Cause Planner/challengers.
- When a challenge fits one bounded shard, render its brief/index
  mechanically, run one independent challenger, and finalize the index
  deterministically. Never skip the challenger.
- Refresh Gerrit delivery scalars and update only the Freshness gate with the
  delivery helper. A newer material patchset still restarts the review; a
  helper cannot declare a semantic delta trivial.

## Sharded Aggregation

Collection, verification planning, root-cause planning, reconciliation, and
challenge planning use map/collect topology whenever their indexed assigned
input exceeds the agent budget.

1. Partition exact row/surface IDs into non-overlapping shards under budget.
2. Give each worker the index slice and only its selected canonical bodies.
3. Write immutable shard artifacts; never have two workers write one canonical
   file.
4. Use a deterministic collector to verify union equality, zero duplicates,
   source fingerprints, and required fields before assembling the canonical
   manifest/table.
5. Route semantic conflicts to a bounded reconciliation worker; do not let the
   collector adjudicate them.

Dense single-file diffs may shard by stable hunk/surface range rather than
path. Each hunk and changed surface belongs to exactly one inventory shard;
file-level risks and per-file floor are checked across their union.

Do not pipeline final verification from an incomplete discovery corpus merely
to save latency. High-risk discovery may run first, but Collection remains the
barrier before the final candidate index, deduplication, and verdict plan.
