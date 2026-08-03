<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## gerrit-comments.md

````markdown
# Gerrit-ready comments — CL 9999999 PS3 / 4f2a09c1

## Main comment

Not LGTM until the failed-flush result bug is fixed. ...

## Replies to existing unresolved threads

### Thread abc123 — net/streams/delay_buffer.cc:167

- Latest comment id: def456
- Status: remains open / resolved by PS3 / owner question
- Reply: Can we ...?

## New inline comments

### net/streams/delay_buffer.cc:203

- Line: `return write_len_;`
- Comment: Can this return the captured write error after cleanup? Returning a
  positive length advances the caller past bytes that were not accepted.

  ```suggestion
  return result;
  ```

## Optional polish

- `nit:` ...
````

An absent section says `None`; never emit placeholder comments. Thread replies
use the normalized thread root/latest IDs from
`gerrit/unresolved-threads.json`, not positional assumptions about
`comments.json`.
