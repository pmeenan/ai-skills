<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## challenge/ And challenge.md

Challenge work is sharded whenever its required input would exceed
`worker_input_budget_bytes`; six findings/questions or 200 reconciliation rows
are conservative starting heuristics, not permission to exceed the byte
budget. Each `CH...` shard owns a measured bounded set of cards/draft sections
or structural rows and writes an immutable file:

```markdown
# Synthesis challenge — round 1 / CH001 — draft revision 1

| id | scope | draft says | record says | evidence | required correction | status |
| --- | --- | --- | --- | --- | --- | --- |
| CH001-1 | F001 | fix is validated | RC001-1 validates only immediate path | RC001-1; delay_buffer.cc:199-203 | downgrade fix status to option needing verification | open |
```

The Challenge Collector writes `challenge.md` as a small index, never by
discarding shard rows:

```markdown
# Challenge index — round 1 / draft revision 1

- Draft revision: 1

| shard | scope | brief | artifact | expected coverage | issues |
| --- | --- | --- | --- | --- | --- |
| CH001 | F001-F002 / ISSUES-P1 | briefs/CH001.md | challenge/round-1/CH001.md | card:F001, card:F002, section:ISSUES-P1 | CH001-1 |
| CH002 | structural rows | briefs/CH002.md | challenge/round-1/CH002.md | row:EPW-2, row:V001-1, row:RC001-1 | none |
| CH003 | global-consistency / frame and indexes | briefs/CH003.md | challenge/round-1/CH003.md | global:consistency | none |

- Result: revision required
- Total open issues: 1
```

The immutable index lives at `challenge/round-1/index.md`; `challenge.md`
contains only the current round, index path, issue count, and pass/fail result.
After any draft revision, increment the round and run a new complete challenge
generation under `challenge/round-<N>/`; never overwrite an earlier round. A
revision is never accepted based only on the old challenge's issues being
addressed; the revised draft is challenged afresh.
