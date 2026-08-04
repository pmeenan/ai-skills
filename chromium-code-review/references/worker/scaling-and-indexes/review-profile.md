<!-- Generated from ../../scaling-and-indexes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Scaling And Compact Indexes

Use this contract to scale effort without weakening coverage or overfilling an
agent context. The deterministic helpers produce routing evidence; workers
still make semantic review decisions.

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

Profile class is a budget and sharding prior, not the topology selector.
Schema-3 profiles use `evidence-graph-v1`: inventory records typed edges and
two bounded generalist passes independently inspect them. Shard both passes
over the same connected-component/budget partition when a whole-graph pass
would exceed budget; unresolved evidence then
selects catalog lenses and shards mechanically. Per-file/hunk coverage,
reconciliation, independent challenge of every surviving candidate, and
delivery freshness remain mandatory. Legacy schema-2 reviews retain the full
roster. A micro profile may use the fast paths below only after Inventory
confirms the profile's proof.
