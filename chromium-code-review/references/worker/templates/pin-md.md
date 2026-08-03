<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## pin.md

```markdown
# CL 9999999 — patchset 3 pin

- Subject: [net] Add DelayBuffer for socket-level write pacing
- Status: NEW
- Owner: Jane Doe <jdoe@chromium.org>
- Updated: 2026-07-01 18:22:04
- Pinned patchset: 3
- Revision SHA: 4f2a09c1d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4c9
- Parent SHA: 8b1d77e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b177
- Gerrit-current patchset at fetch: 3
- Gerrit-current revision SHA at fetch: 4f2a09c1d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4c9
- Is current at fetch: yes
- Metadata fetched at: 2026-07-01T18:24:11Z
- Ref: refs/changes/99/9999999/3
- Worktree: /checkout/chromium/codereview/worktrees/cl-9999999-ps3 (rev-parse verified; clean; active lease required)
- Worktree lease: /checkout/chromium/codereview/locks/cl-9999999-ps3.log
- Worktree lease token: 4bf91f071cc24bd3960362c5ef57251a
- Messages: 12; comment threads: 9 (2 unresolved)
- Files changed (3):
  - net/streams/delay_buffer.cc
  - net/streams/delay_buffer.h
  - net/streams/delay_buffer_unittest.cc
```
