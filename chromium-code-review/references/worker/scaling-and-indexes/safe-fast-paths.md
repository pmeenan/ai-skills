<!-- Generated from ../../scaling-and-indexes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Scaling And Compact Indexes

Use this contract to scale effort without weakening coverage or overfilling an
agent context. The deterministic helpers produce routing evidence; workers
still make semantic review decisions.

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
