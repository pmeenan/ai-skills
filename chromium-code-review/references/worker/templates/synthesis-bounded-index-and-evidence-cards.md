<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## synthesis/ — Bounded Index And Evidence Cards

The Reconciliation Builder writes one immutable card per promoted finding and
question. Each card is at most `evidence_card_budget_bytes` from
`profile.json` and contains only the
evidence needed to draft and challenge that item. If evidence exceeds the
bound, split supporting material into numbered parts and keep the root card
within the bound. The draft writer consumes these cards instead of
all verdict and root-cause files.

The disposition owns the synthesis-item identity: use exactly
`promoted → F<number> (...)` or `question → Q<number> (...)`. Every such item
appears exactly once in `synthesis/index.md`, and that index row's `source
rows` includes the disposition's defining row. Non-promoted/non-question
dispositions own no card. A severity downgrade stays inside a
`promoted → F<number>` disposition; never use bare `downgraded`, which would
omit the finding. The validator compares these sets exactly; a missing card is
an error, not an empty-review warning.

````markdown
# EPW-2 evidence card — CL 9999999 PS3

- Disposition: promoted → F001 (P1, V001-1, RC001-1)
- Claim / location: failed flush reported as success — net/streams/delay_buffer.cc:203
- Candidate: EPW-2 (effective row, including amendment if any)
- Verdict: V001-1 CONFIRMED — completing trace ...
- Root cause: RC001-1 — invariant owner and fix verdict ...
- Root family: RF001
- Merge support: AL-1 (equivalence validated)
- Severity / origin: P1, anchor ..., CL-introduced
- Existing Gerrit thread: root abc123, or `none`
- Verbatim changed line: `return write_len_;`
- Suggested edit decision: applicable — replaces net/streams/delay_buffer.cc:203
- Suggested edit selected lines:
  ```cpp
  return write_len_;
  ```
- Suggested edit replacement:
  ```suggestion
  return result;
  ```
- Required test / verification caveat: ...
````

`synthesis/index.md` is the compact card manifest:

```markdown
| item | card | bytes | source rows |
| --- | --- | --- | --- |
| F001 | synthesis/EPW-2.md | 2840 | EPW-2, AL-1, V001-1, RC001-1 |
| Q002 | synthesis/AL-3.md | 1902 | AL-3, V002-3 |
```
