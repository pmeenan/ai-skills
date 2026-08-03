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

## Desk-Check Simulation

Execute the code on paper rather than just reading it: names and comments
describe intent — only simulation reveals behavior. This is a hand
simulation with a written value table, not an instruction to build or run
anything (for when actually executing code is warranted, see
Execution-Based Verification in `references/verification-and-fixes.md`).
For each changed function that touches sizes, offsets, indices, buffers,
loops, or arithmetic:

1. Pick two or three concrete inputs from the table below, biased toward the
   boundary the code is least obviously prepared for.
2. Trace the function line by line, keeping a written table of
   `line | variable | value` as you go. Update every assignment; do not skip
   "obvious" lines — off-by-ones live in obvious lines.
3. At each loop boundary and each index/pointer use, check the value against
   the container's actual size at that moment.
4. Any state where a variable goes negative, wraps, exceeds capacity, or a
   loop fails to terminate is a candidate finding with the trace as evidence.

Adversarial value table:

| Input kind | Values to push through |
| --- | --- |
| size/length/count | 0, 1, exact capacity, capacity ± 1, `SIZE_MAX`, largest plausible production value |
| signed integer | -1, 0, `INT_MAX`, `INT_MIN` |
| index/offset | 0, last, last + 1 |
| buffer/string | empty, 1 byte, exactly one chunk, one chunk + 1 byte |
| collection | empty, one item, duplicate items, front item removed mid-iteration |
| delay/timestamp | zero delay, identical timestamps, delay shorter than timer resolution |

For functions that delay or schedule completion, also write a timeline table:
`API entry time | wrapped operation completion time | timer start time |
callback fire time`. Run at least three cases: wrapped operation completes
synchronously, wrapped operation completes before the configured delay budget
expires, and wrapped operation completes after that budget has already expired.
Any case where "total latency" silently becomes "wrapped latency plus extra
latency" is a candidate unless the API contract explicitly says the delay is
additive.
