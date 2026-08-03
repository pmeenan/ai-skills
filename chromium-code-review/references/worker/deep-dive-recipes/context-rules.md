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

## Context Rules

Apply before reviewing any hunk. Diffs show what changed; bugs usually live in
the interaction between what changed and what did not.

- Read the full enclosing function of every hunk, never the hunk alone.
- For every touched class, read the class header and its destructor plus any
  reset/Close/Shutdown/Abort methods, even if the CL does not change them.
  Most lifetime bugs are interactions between changed code and unchanged
  teardown.
- For the most-changed files, fetch the parent revision
  (`git show <parent-sha>:<path>`) and read the old version of each heavily
  modified function. Do not reconstruct "before" from the diff's context
  lines. Then list every input or state for which observable behavior differs
  between old and new, and justify each difference against the CL description.
  A difference you cannot justify is a candidate regression.
