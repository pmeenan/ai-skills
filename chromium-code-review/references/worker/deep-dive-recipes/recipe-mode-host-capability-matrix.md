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

## Recipe: Mode × Host-Capability Matrix

Trigger: the CL adds a mode, flag, or transform to an existing class — a new
bool, enum, or member that changes how existing operations behave — OR a new
state container/collection (a session map, registry, queue) to an existing
class. For a new container, the capability axis is every existing
administrative method of the host: clear, reset, shutdown, close-all,
flush, stats. Each such method must account for the new state or the cell
is a candidate. (A measured run missed that a NetworkContext gained an
isolated-sessions map while its ClearHttpCache/CloseAllConnections kept
operating only on the primary session.)

The diff shows the new mode; the bugs live in the host's pre-existing
capabilities, which the diff barely touches. A diff-anchored read structurally
cannot see these cells, so enumerate them:

1. Read the entire class header, not just the changed declarations. List
   every public entry point, changed or not.
2. List the host's pre-existing capabilities and special modes. Grep the
   class for markers such as `parallel`, `Stop`, `cancel`, `abort`,
   `truncat`, `resume`, `restart`, `retry`, `range`, `doom`, `join`, plus
   any mode/pattern enums declared in the header.
3. Build the matrix: new mode × each entry point and capability. Mark every
   cell compatible, incompatible-but-guarded (name the guard line),
   incompatible-unguarded, or not-checked.
4. Every incompatible-unguarded, not-checked, or unexplained cell is a
   ledger candidate. The old entry points were written before the new mode
   existed; assume they mishandle it until the guard is named.
5. The deliverable is the rendered table itself — return it with the
   candidate rows, every cell marked. Returning only the interesting
   findings is the measured failure mode: a run skipped two of the four
   cells named in this recipe's own example because nothing forced the
   table. When an example below happens to match the CL under review, its
   cells still require their own rows — examples illustrate the procedure,
   they never pre-fill it.

Example pattern: a CL adds on-disk compression to a cache writer. The matrix
row "compressing" × {parallel writers catching up from disk, StopCaching
mid-stream, truncation detection comparing disk size to Content-Length, a
late transaction joining} contains four P1 bugs — none of which appear in
the changed hunks.
