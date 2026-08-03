<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## Final-Review Finding

````markdown
#### 1. Failed flush reported as success — silent byte loss (P1)

- **Synthesis item:** F001
- **Claim:** When the flush timer fires after a write failure,
  `DelayBuffer::OnTimer` runs failure cleanup but still returns
  `write_len_`, so the caller's DoLoop advances past bytes the socket never
  accepted.
- **Location:** net/streams/delay_buffer.cc:203
- **Evidence:** OnWriteFailure() at delay_buffer.cc:199 clears `buffer_`;
  the subsequent `return write_len_;` reports 1024 accepted bytes;
  delay_stream.cc:88 advances the read offset by the returned count.
- **Severity:** P1 (anchor: success-shaped return after failure cleanup).
- **Origin:** CL-introduced.
- **Fix status:** validated fix — return the error code captured by
  OnWriteFailure() after cleanup completes (traced through immediate,
  delayed, and abort paths).
- **Suggested edit:** applicable — replaces net/streams/delay_buffer.cc:203

  ```suggestion
  return result;
  ```
- **Regression test:** in delay_buffer_unittest.cc, fail the underlying
  write with ERR_CONNECTION_RESET while a flush is pending and assert the
  flush completion reports the error and the consumer offset does not
  advance.
- **Rows:** EPW-2 / V001-1 / RC001-1 (internal trail — omit from Gerrit-ready
  text).
````
