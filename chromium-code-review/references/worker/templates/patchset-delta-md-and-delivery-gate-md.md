<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## patchset-delta.md And delivery-gate.md

`patchset-delta.md` is immutable evidence about one newer patchset:

```markdown
# Patchset delta inspection

- Reviewed pin: PS3 4f2a09c1d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4c9
- Inspected Gerrit current: PS4 5a3b...
- Inspected at: 2026-07-01T19:02:00Z
- Classification: trivial
- Files / changes: commit-message-only; executable diff empty
- Cited-line revalidation: every F/Q card location remains byte-identical
- Conclusion revalidation: all findings, questions, and verdict remain valid
```

Material classifications additionally name affected findings and roster
scopes, but never amend old rows. `delivery-gate.md` is written only after the
latest complete challenge by direct
`scripts/refresh-delivery-gate.py <review-dir>` execution (add
`--accept-proven-trivial-delta` only for the already revalidated case). Do not
spawn a finalizer agent unless the harness cannot invoke the helper; the phase
brief is a degraded wrapper only.

```markdown
# Delivery freshness
- Checked after challenge revision: 2
- Checked at: 2026-07-01T19:08:00Z
- Pinned: PS3 4f2a09c1d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4c9
- Gerrit current: PS4 5a3b...
- Result: trivial delta verified
- Gate line: yes — patchset-delta.md matches current PS4/SHA and draft revision 2 passed challenge/round-2/index.md
```

Accepted results are `current`, `historical pin verified`, and `trivial delta
verified`. `newer patchset` and `fetch failed` are blocking. The finalizer
copies the accepted result into only the Freshness line of reconciliation.md.
