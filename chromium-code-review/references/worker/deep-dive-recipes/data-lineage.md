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

## Data Lineage

For each new or changed value that crosses a boundary (IPC/Mojo, disk,
network, process, sequence, or component): write its lineage —

- **Origin:** who produces it, and is that producer trusted?
- **Hops:** units and encoding at each step (wire bytes vs decoded bytes vs
  item counts vs blocks; encrypted vs plaintext; compressed vs decompressed).
- **Validation:** which hop validates range/format, and is every use
  downstream of that validation?
- **Sinks:** every place it is stored, compared, or used for arithmetic.

Flag any hop where units could be misread (a byte count consumed as an item
count), where validation happens after first use, or where two sinks assume
different encodings. Unit mismatches are invisible hunk-by-hunk and obvious in
a lineage table.
