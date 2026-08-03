<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## ledger/⟨THREAD⟩.md — Compliance Matrix And Candidate Rows

The exact section headings `## Compliance matrix` and `## Candidate rows`
are load-bearing: late-phase agents extract the row sections mechanically
(`sed`/`grep`) instead of reading whole ledgers, so a renamed heading makes
a thread's rows invisible to verification and reconciliation.

```markdown
# EPW — Error-Path Walk — CL 9999999 PS3

Scope: DelayBuffer::Push, ::Flush, ::OnTimer (net/streams/delay_buffer.cc)

## Compliance matrix

| # | step / question | answer | evidence | candidate |
| --- | --- | --- | --- | --- |
| 1 | Push: cleanup skipped on early return? | ERR_ABORTED path leaves `pending_` set | net/streams/delay_buffer.cc:141 | EPW-1 |
| 2 | Push: completion callback invoked on every path? | yes — all three returns run `std::move(callback_)` | net/streams/delay_buffer.cc:120,133,144 | — |
| 3 | Flush: members left half-initialized? | N/A — Flush has no early returns | net/streams/delay_buffer.cc:150-171 | — |
| 4 | OnTimer: return value traced one step into consumer? | returns `write_len_` after `OnWriteFailure()` ran | net/streams/delay_buffer.cc:203 | EPW-2 |

## Candidate rows

| id | claim | location | evidence / hypothesis | origin | severity | status |
| --- | --- | --- | --- | --- | --- | --- |
| EPW-1 | ERR_ABORTED path leaves `pending_` set; next Push hits `CHECK(!pending_)` | net/streams/delay_buffer.cc:141 | IF Push returns ERR_ABORTED THEN `pending_` stays true and the next Push CHECK-crashes UNLESS a reset path clears it (none found in this class) | CL-introduced | | candidate |
| EPW-2 | Success-shaped return after failure cleanup | net/streams/delay_buffer.cc:203 | trace: OnTimer → OnWriteFailure() at :199 clears `buffer_` → returns `write_len_ > 0` → caller's DoLoop treats the failed write as progress | CL-introduced | | candidate |

## Candidate descriptors

| candidate | classes | obligations | base / interface | invariant owner | violated invariant | state / transition | proposed fix layer | related symbols |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EPW-1 | state-protocol | base-contract, caller-reachability, callee/backend-implementation | DelayBuffer public call-state contract | DelayBuffer pending-state transition | an aborted operation must leave the object callable or explicitly terminal | Push active → aborted → next Push | unknown — verification must identify whether Abort or Push owns reset | DelayBuffer::Push, DelayBuffer::Abort, pending_ |
| EPW-2 | contract | base-contract, caller-reachability, callee/backend-implementation | OnTimer completion result consumed by DelayStream::DoWriteComplete | unknown — verification must trace the shared completion contract | a completion result must report bytes accepted XOR an error | write pending → timer fires after backend failure | unknown — verification must compare cleanup helper, completion wrapper, and caller | DelayBuffer::OnTimer, OnWriteFailure, DoWriteComplete |
```

The matrix row 1 shows the anomaly rule in action: the answer records the
anomaly AND emits the candidate. Row 4 is the mandatory-candidate class
(success-shaped return after failure cleanup) — recorded, never adjudicated
in-thread. Every status `candidate`/`reopened` row has exactly one descriptor
row. `classes` is one or more of `general`, `contract`, `async-lifetime`,
`style-convention`, `state-protocol`, or `platform`. `obligations` uses only
`local-proof`, `base-contract`, `caller-reachability`, `callee/backend-implementation`,
`async-operation-owner`, `destruction/cancellation`, `platform-branches`, and
`style-authority`. Class-required obligations are mandatory:

- `contract` and `state-protocol`: base contract, caller reachability, and
  callee/backend implementation;
- `async-lifetime`: callee/backend implementation, async operation owner,
  destruction/cancellation, and platform branches;
- `style-convention`: applicable style authority;
- `platform`: platform branches.

Use `local-proof` only for a genuinely local claim such as punctuation or an
unused include. It never substitutes for a class-required cross-layer
obligation.

Use `unknown — reason` for unresolved semantic descriptors; a bare
`unknown`, `N/A`, or `-` is invalid. The descriptors preserve semantic
affinity across sharded verification and tell the skeptic exactly which
cross-layer contracts must be closed.
