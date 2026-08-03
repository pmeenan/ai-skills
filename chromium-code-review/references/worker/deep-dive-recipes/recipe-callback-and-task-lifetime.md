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

## Recipe: Callback And Task Lifetime

Trigger: any `PostTask`, `BindOnce`, `BindRepeating`, timer, or Mojo callback
in the diff.

1. Name the object the callback is bound to and the binding mode
   (`base::Unretained`, `WeakPtr`, `scoped_refptr`, raw `this` capture,
   owned-by-callback; in Blink, `WrapPersistent` / `WrapWeakPersistent`
   over Oilpan-managed objects).
2. Name every code path that can destroy or reset that object (destructor,
   reset, disconnect handler, error path, tab close, shutdown).
3. Name the sequence each of (1) and (2) runs on.
4. Name the line that prevents the callback from running after destruction
   (weak invalidation, timer stop, cancelable callback, sequence guarantees).

If you cannot complete step 4, that is a candidate finding, not an unknown.
`base::Unretained` requires a lifetime argument; if no comment or obvious
structural guarantee justifies it, file at least a P3 documentation candidate
and trace it as a potential P1.
