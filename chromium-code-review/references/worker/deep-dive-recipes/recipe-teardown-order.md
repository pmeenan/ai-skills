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

## Recipe: Teardown Order

Trigger: any touched stateful class.

1. Read the destructor and reset/Shutdown paths even if unchanged.
2. Members are destroyed in reverse declaration order: record the order for
   the members involved in the CL.
3. Check: does any timer, callback subscription, observer registration, or
   background task outlive a member it uses? Is anything unregistered after
   the thing it observes is gone?
4. If the CL adds a member, check its declaration position relative to the
   members and callbacks that reference it — a new member declared after the
   timer that uses it is destroyed first.
5. For operation-scoped heavy resources (codec contexts, large buffers,
   scratch arenas) owned by a long-lived object: name the line that releases
   the resource at the end of the operation — on success, failure, and
   cancellation — not just in the owner's destructor. A request-scoped
   resource held until a connection-scoped owner dies is a memory finding.
