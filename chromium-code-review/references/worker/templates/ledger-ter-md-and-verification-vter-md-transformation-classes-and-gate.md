<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## ledger/TER.md And verification/VTER.md — Transformation Classes And Gate

The TER ledger adds a `## Transformation classes` table (classes are gate
targets, not candidate rows) and satisfies the per-file floor with one clean
membership row per class × file in its ordinary `## Candidate rows` table:

```markdown
## Transformation classes

| class id | old → new | members | files | proof |
| --- | --- | --- | --- | --- |
| TC1 | base::LegacyFmt(x) → std::format(x) | 214 | net/foo/a.cc; net/foo/b.cc | diff table rows 1-11; scratch/TER/rederive-TC1.log |

The `files` cell is an explicit `;`-separated repo-relative list — never a
count or a pointer; the validator reconciles it one-to-one against
membership rows. A file whose class sites all conform gets a
`clean (class TC⟨n⟩ conforming)` membership row; a file that also carries
residue gets a `mixed (class TC⟨n⟩ + residue)` membership row plus its
residue candidate rows. A TER thread that finds no stable class writes the
explicit sentinel row `| — | no stable transformation class found | 0 | — |
⟨scan evidence⟩ |`; a spawned TER ledger with neither a class nor the
sentinel — or missing the `## Transformation classes` or `## Residue`
headings — fails validation.

## Candidate rows

| id | claim | location | evidence / hypothesis | origin | severity | status |
| --- | --- | --- | --- | --- | --- | --- |
| TER-1 | clean: class TC1 conforming; re-derivation empty | net/foo/a.cc:1 | rederive diff empty | CL-introduced | | clean (class TC1 conforming) |
| TER-2 | class TC1 conforming sites plus residue below | net/foo/b.cc:1 | rederive diff empty except hunk H0412 | CL-introduced | | mixed (class TC1 + residue) |
| TER-3 | residue: hand-edited callsite deviates from TC1 | net/foo/b.cc:88 | rederive diff nonempty (3 lines) | CL-introduced | | candidate |

## Candidate descriptors

| candidate | classes | obligations | base / interface | invariant owner | violated invariant | state / transition | proposed fix layer | related symbols |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TER-3 | contract | base-contract, caller-reachability, callee/backend-implementation | transformed call contract | shared transformation class TC1 | every class member preserves old behavior | old call → transformed call | unknown — verification must locate the divergence owner | TC1, transformed helper |
```

The gate skeptic writes `verification/VTER.md` with the dedicated schema —
`PROVEN / REJECTED / UNPROVEN`, never the defect verdicts; the file is
excluded from ordinary verdict pipelines and indexes:

```markdown
# TER gate verdicts — CL 9999999 PS3

| id | class | verdict | evidence |
| --- | --- | --- | --- |
| VTER-1 | TC1 | PROVEN | independently re-derived difference table; sampled 6/214 sites (a.cc:12, c.cc:40, ...); no unlisted observing site found |
```

The gate table has exactly these four columns and `VTER-⟨n⟩` IDs. PROVEN
and REJECTED verdicts require a real `path:line` citation — the gate
accepts no `evidence-exception`, because it authorizes bulk residue
scoping. The file counts only with execution provenance: a `VTER`
orchestration work unit, complete, frontier tier, artifact
`verification/VTER.md`, a registered brief, and a dependency on the
gate-brief builder (`VTERB`), which itself must depend on **every** spawned
TER shard.
