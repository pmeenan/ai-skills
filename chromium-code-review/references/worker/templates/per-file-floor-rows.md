<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## Per-File Floor Rows

Every changed file must have at least one ledger row — attention collapses
onto the first and largest files, and the per-file floor keeps coverage even
across the tail of the diff. When no thread emitted a row for a file, the
collection-audit agent reads that file's diff and adds an explicit
clean-or-candidate `ORC` row to `collection.md` (never a silent omission):

```markdown
| id | claim | location | evidence / hypothesis | origin | severity | status |
| --- | --- | --- | --- | --- | --- | --- |
| ORC-1 | clean: file only re-exports the new header; no logic | net/streams/delay_buffer_export.h:1-14 | whole file read; two `#include`s and a comment | CL-introduced | | clean (cited) |
```
