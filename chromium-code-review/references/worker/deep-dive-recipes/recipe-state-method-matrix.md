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

## Recipe: State × Method Matrix

Trigger: a class with a state enum, or implicit states formed by member
combinations (bools, optionals, null-vs-set pointers, pending callbacks).

1. Enumerate the states, including implicit ones.
2. Build a matrix of states × public entry points (methods, callbacks, the
   destructor).
3. For each cell: is the call legal in that state, what enforces that, and
   what actually happens if it occurs?
4. If the class records UMA metrics or telemetry, add the cancellation cells
   explicitly: for every cell where an operation is cancelled or aborted
   while async work (network, disk, IPC, posted task) is pending and the
   completion callback still runs later — even as a no-op or cleanup —
   check that success-only metrics (durations, success counts, size/ratio
   metrics) are gated off, so aborted attempts do not pollute success
   statistics.

Spend extra attention on the cells inspiration never visits: a method called
after Close/Abort/error, the same method called twice, and any entry point
arriving while an async operation is in flight. Edge cases are cells of this
matrix; enumerating them mechanically beats hoping to notice them. Return
the rendered table with every cell marked (legal/enforced/what-happens or
not-checked); unvisited cells are candidates, not omissions.
