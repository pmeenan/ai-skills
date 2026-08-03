<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## Scope-Packet Spec And Code Packets

A planner that generates a brief also writes a machine-readable scope spec
next to it, `packets/⟨WORK⟩.spec.tsv`, naming exactly the code the worker's
scope covers. The orchestrator runs
`scripts/build-scope-packets.py ⟨review-dir⟩ ⟨WORK⟩ --worktree … --parent …
--revision …` before sealing; the resulting `packets/⟨WORK⟩-code.md` holds
the scoped diff and line-numbered changed-side slices, and the brief lists it
as an `assigned` input. Workers read the packet first instead of each
re-running `git diff` and re-opening whole files for the same scope. **The
packet is a starting point, never a boundary:** a worker opens any worktree
file whenever its procedure needs more context, and a packet too narrow for
honest tracing is a spec bug to fix, not a reason to thin the analysis.

```tsv
kind	path	old_range	new_range	note
diff	net/streams/delay_buffer.cc	-	-	whole-file diff
diff	net/streams/big_state_machine.cc	1180-1420	1200-1460	shard hunks H0007-H0012
slice	net/streams/delay_buffer.h	-	40-95	DelayBuffer declaration
```

- `diff`: unified diff of `path` between the pinned parent and revision.
  Ranges `-` take every hunk; otherwise a hunk is kept when it intersects any
  old-side (`old_range`) or new-side (`new_range`) inclusive interval —
  dense-file shards copy their exact owned intervals here.
- `slice`: revision-side lines of `path` from the pinned worktree, emitted
  with line numbers for citation; use it for declarations, contracts, and
  fixture context worth pre-cutting.
- Paths are repo-relative; a row that matches nothing fails the build — fix
  the spec rather than letting a worker guess its scope.
- A worker whose entire scope is one file's full diff may have no spec; it
  derives that single diff itself. Specs are for dense-hunk shards,
  multi-file scopes, and files several workers share.
