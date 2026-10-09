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
For an issue whose immutable shard row explicitly classifies it `clerical`, a
collector may close it without changing the shard by writing
`challenge/round-<N>/clerical-resolutions.json` before recollection:

```json
{
  "draft_revision": "2",
  "resolutions": [{
    "issue": "CH007-1",
    "shard": "CH007",
    "classification": "clerical",
    "evidence": "internal card path only",
    "corrections": [{
      "kind": "exact-text-projection",
      "path": "draft-sections/FRAME.md",
      "before_path": "draft-parts/FRAME.before-clerical.md",
      "audited_sha256": "<hash present in CH007.md>",
      "current_sha256": "<current file hash>",
      "replacements": [{"old": "<exact old text>", "new": "<exact new text>", "count": 1}]
    }]
  }]
}
```

An `exact-text-projection` authenticates the preserved before-file hash against
the immutable shard and must reproduce the complete current file by the listed
ordered exact replacements. A reconciliation-only correction instead uses
`{"kind":"structured-amendment","path":"reconciliation.md","amendment":"<ID>"}`;
the named `replace-fields` amendment must be present and remains subject to all
normal reconciliation gates. Every receipt entry names one exact shard/issue,
has nonempty evidence, and resolves only a row explicitly classified
`clerical`, either in a `classification` column or with the word `clerical` in
the normative `scope` or `required correction` cell. Unclassified or
substantive issues remain open. The collector
records the receipt path in the index, and final validation rechecks it.

After any draft revision, increment the round and run a new complete challenge
generation under `challenge/round-<N>/`; never overwrite an earlier round. A
revision is never accepted based only on the old challenge's issues being
addressed; the revised draft is challenged afresh. The authenticated clerical
projection above is the sole exception because it proves the exact byte delta
from the challenged input while preserving every immutable shard.
