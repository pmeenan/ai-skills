# Process-Contract Validation

These checks exercise workflow invariants without inventing a Chromium CL or
revision. Run them against a completed review directory, or build a synthetic
fixture containing the named control/artifact files. A process fixture is not
a correctness eval and must never be promoted to `cl-<number>.md`.

## Mechanical validation

Run the repository's review-directory validator when available:

```sh
python3 scripts/validate-review-dir.py /absolute/path/to/cl-<CL>-ps<PS>
```

The command must fail (nonzero) for each independently injected,
snapshot-observable defect:

1. The pin schema, selected SHA, parent, worktree, or normalized Gerrit JSON is
   missing or inconsistent.
2. A generated brief omits directives, revision pinning, authority boundary,
   append/amendment, or partial-return contracts.
3. `orchestration.tsv` duplicates a work-ID/attempt, has concurrent writers for
   one canonical artifact, completes a missing artifact, violates a dependency,
   or leaves nonterminal work at delivery.
4. A compliance-matrix PASS lacks a `path:line` citation, two rows reuse an ID,
   or a changed file lacks a ledger/ORC floor row.
5. A candidate has no skeptic verdict or merge survivor, a root-cause brief
   names a noncanonical reopened ID, or an inventory scope marked root-cause
   required is absent from Root-Cause Trigger Accounting.
6. A canonical ledger, verdict, or root-cause row lacks exactly one
   reconciliation disposition.
7. `profile.json` or an `indexes/` view is missing/stale, a synthesis card or
   assembly node violates its profile-derived size/child bound, names an
   unknown source row, or is missing from disk. Assembly input-byte claims
   must equal the sum of the exact listed child files; globs, ranges, missing
   children, and understated declarations fail.
8. Final delivery lacks an accepted freshness result, full pin, affirmative
   gate line, complete successful challenge round, or required trivial-delta
   proof.
9. A large root draft lacks the exact-concatenation section index, a section
   byte count/hash is stale, a section coverage token is missing/duplicated,
   or any large-draft challenger brief reads the complete root outputs.
10. `input-manifest.tsv` omits a generated analytical brief or a file named in
    its Inputs/Procedure, contains a stale byte count/SHA, exceeds the profile
    worker budget, or lets candidate-packet/card inputs exceed their narrower
    profile budgets. For sectioned challenges, exact assigned section/frame/
    card paths must be manifested and fit the worker budget.
11. `plan.md` omits or renames any fixed or trigger-only roster entry. The
    exact specialist additions are FPM, ACS, TER, TSY, OBL, MIS, PRS, PLS,
    BAG, PAT, AXI, NET, and FTS with the canonical names in the skill roster;
    each
    must be `spawn`, explicitly `unreviewed — <reason>`, or `not applicable —
    trigger absence proved by <T IDs>`.
12. A not-applicable row cites an unrelated/positive trigger row, omits an
    `<PREFIX> absent` row from another inventory shard, or coexists with any
    positive trigger for that prefix. Accept both `T<n>` and collision-free
    `I<shard>-T<n>` IDs.

The scaling fixture set must also prove these positive/negative cases:

- A small documentation/metadata-only diff with no risk or prior-feedback
  escalation signal may classify `micro`; a test-only diff, unresolved thread,
  executable contract change, or any escalation signal must not. A
  trigger-only specialist signal is routing evidence, not an escalation signal.
- Deterministic profile fixtures route representative synchronization, Blink
  ownership/lifecycle, Mojo/sandbox, performance/resource, language/platform,
  build/generated, privacy/telemetry, accessibility/i18n, network, fuzzing/test,
  field-propagation, and associative-container edits to the exact roster
  entry/prefix. A benign `.grd`, Java/Rust, AX, or metrics metadata edit does
  not become `high-risk` from file type alone; independent lifecycle, IPC,
  threading, security, persistence, API, or similar behavior signals still
  escalate it.
- A path under `third_party/blink/` or `net/` does not alone activate OBL or
  NET; a lifecycle/ownership or network-semantic signal must match.
- Removing any one specialist roster row from an otherwise valid synthetic
  plan fails exact-roster validation and names the omitted entry.
- A dense single-file diff crosses the `large` threshold and exposes stable
  hunk/surface routing IDs even when its file count is one.
- Zero-candidate and zero-root-trigger fast paths pass only with fresh
  fingerprinted zero-row indexes and their canonical empty artifacts.
- Sharded inventory, Collection, and reconciliation collectors accept an exact
  union and reject a missing, duplicated, foreign, or stale shard.
- Lowering the recorded worker budget forces sharding; it never truncates a
  brief, card, draft part, or challenge assignment to manufacture a pass.
- Duplicate input roles for one path count that path once toward a worker's
  total; omitted named inputs, stale hashes, and actual assembly-child totals
  above budget still fail deterministically.

Some temporal or semantic contracts cannot be reconstructed from one final
directory snapshot. The process evaluator—not the validator—must fail a trace
where a continuation repeats completed scope, an amendment overwrites prior
evidence, freshness was claimed before the passing challenge, or a material
patchset delta reused the old review directory. Record those checks from the
manifest/progress history and sibling-directory evidence; do not imply the
validator proved them.

It must pass a fixture with sharded inventories, multiple retry attempts,
append-only amendments, two reopened verification rounds, and a proven-trivial
patchset delta. Keep that fixture synthetic unless every Gerrit pin and
expected code finding is independently recorded.

## Script smoke checks

```sh
bash -n scripts/fetch-cl.sh
bash -n scripts/mechanical-leads.sh
python3 -m py_compile scripts/extract-unresolved-comments.py scripts/worktree-lease.py
python3 -m py_compile scripts/profile-review.py scripts/build-review-indexes.py
python3 -m py_compile scripts/refresh-delivery-gate.py
python3 -m py_compile scripts/validate-review-dir.py
python3 -m unittest discover -s scripts/tests -v
```

For `mechanical-leads.sh`, create a temporary two-file Git fixture where both
files contain deterministic hits. Invoke the script once for each individual
pathspec and once for both. Assert that each shard contains only its requested
path and that the combined artifact contains every hit even when the count is
larger than any display-summary limit. The authoritative artifact must never
be piped through `head` or otherwise capped.

For `fetch-cl.sh`, use a recorded XSSI-prefixed Gerrit response fixture and
assert that `detail.json` and `comments.json` are valid plain JSON under
`jq -e .`; malformed/missing comment data and a missing parent must fail
instead of producing `{}` or an unusable pin. Also assert that the worktree is
created in the checkout-peer `codereview/worktrees/cl-<CL>-ps<PS>` cache, a
second review of a fresh CL/patchset lease fails immediately, a one-hour-stale
lease is replaced, explicit forced takeover invalidates the old owner token,
corrupt/empty leases are archived without blocking same-pin acquisition or
unrelated cache cleanup, takeover worktrees receive a two-hour removal grace,
a released matching worktree is reused, other released clean cache entries are
removed, dirty inactive entries are preserved, environment timeout overrides
stay synchronized, archived lease logs older than 30 days are pruned, live
validation fails after release, and ordinary audit validation still passes.

## Resume drill

Stop a fixture run after at least one complete, one partial, one retryable,
and one queued work item. In a fresh orchestrator context, provide only the
review-directory path. It must reconstruct the dependency-ready queue from
`orchestration.tsv`, `progress.md`, `pin.md`, `directives.md`, and `plan.md`;
it must not reread ledgers, redo completed work, or blindly retry the full
scope of the partial/failed item.
