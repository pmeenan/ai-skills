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

## Recipe: Container And View Invalidation

Trigger: any pointer, reference, iterator, `base::span`, or
`std::string_view` into a container, buffer, or temporary.

1. Name the acquisition point and the last use.
2. List every operation between them that can reallocate, mutate, or destroy
   the backing store: `push_back`/`insert`/`erase`, map rehash, `reset`,
   `std::move` of the owner, the owner being a temporary or going out of
   scope, or a callback that can reenter and mutate.
3. If any such operation is reachable between acquisition and use, that is a
   candidate with the operation as evidence.

Special case: a `string_view`/`span` constructed from a function's return
value binds to a temporary unless the function returns a reference — check
the callee's signature, not the call site's appearance.
