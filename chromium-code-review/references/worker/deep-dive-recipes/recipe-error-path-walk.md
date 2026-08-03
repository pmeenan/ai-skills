<!-- Generated from ../../deep-dive-recipes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Deep-Dive Recipes

Read this alongside the discovery checklists in Pass 3. The checklists say
*what to suspect*; these recipes say *how to dig*. Each is a fixed procedure
with named work products — run every recipe whose trigger matches the diff and
record the outputs in the ledger.

The recipes are designed so that an incomplete step is itself a candidate
finding: if you cannot name the guard, the owner, or the test, write that down
as the hypothesis instead of moving on. Reviews that only record what they
proved tend to silently skip exactly the places where proof was hard.

The same closure rules bind every recipe row: clean requires a `path:line`
citation of what makes it clean, and any anomaly your notes record becomes a
candidate row regardless of how benign it looks — adjudication belongs to
verification, not to the thread that found it.

## Recipe: Error-Path Walk

Trigger: any changed function with early returns or error branches. Review the
failure paths as carefully as the success path — they get a fraction of the
testing and most of the bugs.

For every early return and error branch in changed code, answer four
questions and list each return point with its answers:

1. What cleanup is skipped relative to the success path (and relative to the
   other error paths)?
2. Is there a completion/result callback the caller is waiting on that this
   path never invokes? A dropped completion callback hangs the caller
   forever and is a top Chromium bug class.
3. What members or outputs are left half-initialized, and who can observe
   them afterwards?
4. What resources (locks, slots, fds, cache entries, quota) are still held?
5. Trace the exact return value one step into its consumer: what does the
   enclosing loop, state machine, or caller do next with this value and the
   state this branch just mutated? Walk one full iteration past the error —
   error branches that read correctly in isolation fail at the hand-off.

For `DoLoop`-style state machines (the net/ `next_state_` pattern): on every
branch, check that the pair (return value, `next_state_`) leaves the machine
in a defined configuration. An error return with a stale `next_state_`
re-enters a state whose preconditions the cleanup just destroyed; a
success-shaped return (a positive length, `OK`) emitted after failure cleanup
makes the loop treat the failure as success. Both read locally like correct
error handling — which is why a success-shaped return after failure cleanup
is a **mandatory candidate row, never adjudicated in-thread**: measured runs
twice recorded exactly this anomaly in their notes, dismissed it as benign,
and it was a P1 crash both times. Also prefer setting the terminal state
before invoking completion/notification helpers, so reentrant observers see
a consistent machine and the helper can assert it.
