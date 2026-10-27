<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## ledger/PR.md — Prior-Feedback Reconciliation

The exact `## Prior-feedback rows` and `## Candidate rows` headings are
required. The first table accounts for every supplied finding, every normalized
unresolved Gerrit thread, and every resolved Gerrit thread in `comments.json`
where `Reviewer email` agreed to defer work to a follow-up CL, using one of the
canonical `resolution` values: `fixed`, `partially fixed`, `still open`,
`obsolete`, `superseded`, `reviewer decision pending`, `deferred (accepted)`
(for resolved threads where `Reviewer email` agreed the deferred work may land
in a follow-up CL), or `not-posted` (for local draft items in
`prior-feedback-input.md` that `Reviewer email` did not post to Gerrit according
to `comments.json`). Only `partially fixed` and `still open` items are copied
into `## Candidate rows` for verification; `fixed`, `obsolete`, `superseded`,
`reviewer decision pending`, `deferred (accepted)`, and `not-posted` PR rows
remain reconciliation obligations in `reconciliation.md` (for example `clean
(fixed in PS...)`, `clean (deferred to follow-up CL per thread ...)`, or `clean
(not-posted in prior Gerrit review)`) and must never be copied into `##
Candidate rows` as active `candidate` rows.

```markdown
# Prior feedback — CL 9999999 PS3

## Baseline derivation

- Prior review source: prior-feedback-input.md, review timestamp 2026-06-30T14:02:00Z
- Derived reviewed patchset: PS2, SHA 93ab... (detail.json revision `_number` 2;
  newest revision created no later than the supplied review timestamp)
- Confidence: explicit / derived / unknown
- Comparison: `git diff 93ab... 4f2a...`; or `unavailable` with reason

## Gerrit thread normalization

- Normalized input: gerrit/unresolved-threads.json
- Unresolved thread roots accounted: 2

## Prior-feedback rows

| id | source | prior claim / thread | prior location | baseline | current evidence | resolution | origin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PR-1 | supplied finding 1 | pending_ survives abort | net/streams/delay_buffer.cc:141 | PS2 93ab... | reset added at delay_buffer.cc:143 | fixed | introduced-in-PS2 |
| PR-2 | Gerrit thread root abc123 | Flush can double-complete | net/streams/delay_buffer.cc:167 | PS2 93ab... | second path remains at :172 | still open | introduced-in-PS2 |
| PR-3 | supplied finding 2 | optional helper rename | net/streams/delay_buffer.h:44 | PS2 93ab... | absent from comments.json by Reviewer email | not-posted | CL-introduced |
| PR-4 | resolved Gerrit thread root def456 | follow-up unit tests for retry policy | net/streams/delay_buffer_unittest.cc:1 | PS1 51c0... | reviewer agreed in thread def456 to land unit tests in stacked CL | deferred (accepted) | CL-introduced |

## Candidate rows

| id | claim | location | evidence / hypothesis | origin | severity | status |
| --- | --- | --- | --- | --- | --- | --- |
| PR-2 | prior unresolved double-completion concern remains | net/streams/delay_buffer.cc:172 | trace: ... | introduced-in-PS2 | | candidate |

## Candidate descriptors

| candidate | classes | obligations | base / interface | invariant owner | violated invariant | state / transition | proposed fix layer | related symbols |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PR-2 | async-lifetime | callee/backend-implementation, async-operation-owner, destruction/cancellation, platform-branches | Flush completion contract | DelayBuffer pending completion state | one operation completes exactly once | pending → abort/flush → completion | unknown — verification must compare completion owners | Flush, pending_, callback_ |
```

Never assume "previous patchset" means `PS-1`. Prefer an explicit patchset/SHA
from the prior feedback. Otherwise map revision `_number`, `created`, and
Gerrit message timestamps from `detail.json`: choose the newest revision whose
creation is no later than the prior review timestamp. If the source has no
usable patchset or timestamp, record baseline `unknown`, do not fabricate a
comparative origin, and reconcile against the pinned code without a delta.
