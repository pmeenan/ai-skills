<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## Exact Output Fragments, draft-parts/, And draft-assembly/

When the card index has at most 12 cards and the measured total required input
(cards plus compact control artifacts) is at most
`worker_input_budget_bytes` from `profile.json`, one Draft Writer may
consume them. Above either threshold, use one Finding Writer per card and a
separate Frame Writer. Both topologies produce the same exact per-item
fragments: `draft-parts/<item>.md` is the byte-for-byte review block for every
finding/question, and `gerrit-parts/<item>.md` is the byte-for-byte Gerrit
comment for every finding. Questions have no Gerrit fragment.

````markdown
#### Failed flush reported as success — silent byte loss (P1)

- **Synthesis item:** F001
- **Claim:** failed cleanup still returns a success-shaped byte count.
- **Location:** net/streams/delay_buffer.cc:203
- **Evidence:** ...
- **Severity:** P1 — success-shaped return after failure cleanup.
- **Origin:** CL-introduced.
- **Fix status:** validated fix — ...
- **Suggested edit:** applicable — replaces net/streams/delay_buffer.cc:203

  ```suggestion
  return result;
  ```
- **Regression test:** ...
- **Rows:** EPW-2 / V001-1 / RC001-1
````

When an inline replacement is not eligible, use exactly
`- **Suggested edit:** omitted — <specific reason>` and emit no
`suggestion` fence. An applicable edit uses one contiguous changed-side range
of at most 10 selected lines and at most 20 replacement lines. Its
`suggestion` block is byte-for-byte identical in the draft and Gerrit
fragments and contains only complete replacement text. Empty replacement text
is allowed for a validated deletion.

`gerrit-parts/F001.md` contains only the exact target/comment block intended
for Gerrit, including its repo-relative `path:line`; it contains no internal
item marker. `output-coverage.tsv` binds both fragments to the card:

```tsv
item	kind	draft_path	draft_bytes	draft_sha256	gerrit_path	gerrit_bytes	gerrit_sha256
F001	finding	draft-parts/F001.md	⟨bytes⟩	⟨sha256⟩	gerrit-parts/F001.md	⟨bytes⟩	⟨sha256⟩
Q002	question	draft-parts/Q002.md	⟨bytes⟩	⟨sha256⟩	-	-	-
```

The item set equals `synthesis/index.md` exactly. A finding fragment has the
complete Finding Format fields; a question fragment has non-empty
`Synthesis item`, `Question`, `Why it matters`, and `Rows` fields. Final
validation checks every measured fragment occurs byte-for-byte exactly once
in its destination output. An ID in a frame/list does not count, and a
finding without a Gerrit fragment cannot pass.

`FRAME.md` contains only High-Level Summary, Prior Review Follow-Up, Positives,
Verification Notes, Next Steps, verdict sentence, and the ordered part list; it
does not repeat per-finding evidence.

Assembly is hierarchical. Every assembly node consumes at most 12 input cards
or fragments and no more than `worker_input_budget_bytes` total, writes one
`draft-assembly/L<level>-N<node>.md`,
and records exact child paths plus byte counts. Nodes only order, join,
validate required headings, but never edit, summarize, deduplicate, or omit
bytes inside a per-item draft/Gerrit fragment. They never reopen
ledgers/verdicts, alter claims/severity/fixes, or invent evidence.
The root assembly writes `draft-review.md` and `gerrit-comments.md`. If a node
would exceed either bound, add another level. The assembly manifest shape is:

```markdown
# Draft assembly — revision 1

| node | inputs | input bytes | output | status |
| --- | --- | --- | --- | --- |
| L01-N001 | draft-parts/F001.md ... F008.md | 118204 | draft-assembly/L01-N001.md | complete |
| L02-N001 | FRAME.md, L01-N001.md, L01-N002.md | 172911 | draft-review.md + gerrit-comments.md | complete |
```

The root output starts with `- Draft revision: ⟨n⟩`; `FRAME.md` is a required
root input, not optional framing that may be dropped during assembly. The root
also collects the measured per-worker coverage rows into canonical
`output-coverage.tsv`; duplicate, missing, foreign, stale-hash, or
non-included fragments block delivery.

When a root draft exceeds `worker_input_budget_bytes`, assembly also emits
immutable section fragments and an exact-concatenation index:

```tsv
revision	order	section	type	draft_path	draft_bytes	draft_sha256	gerrit_path	gerrit_bytes	gerrit_sha256	cards	rows	global_frame
1	1	FRAME	frame	draft-sections/FRAME.md	8421	⟨sha256⟩	gerrit-sections/FRAME.md	211	⟨sha256⟩	-	-	yes
1	2	ISSUES-P1	findings	draft-sections/ISSUES-P1.md	26310	⟨sha256⟩	gerrit-sections/ISSUES-P1.md	1944	⟨sha256⟩	F001,F002	EPW-2,AL-1	no
```

`draft-review.md` and `gerrit-comments.md` must be raw byte concatenations of
their respective indexed fragments in numeric `order`, with no collector-
inserted separator, newline, or normalization. Each fragment therefore owns
any required trailing newline. A destination with no content uses
`-`, `0`, and the SHA-256 of the empty byte string; it is never silently
omitted. Challengers verify fragment hashes
and consume only assigned sections plus the bounded frame; one global shard
receives headings/digests and target indexes, not every section body.
