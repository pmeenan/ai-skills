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

## Contents

- Context Rules
- Desk-Check Simulation
- Arithmetic Drills
- Data Lineage
- Recipe: Callback And Task Lifetime
- Recipe: Container And View Invalidation
- Recipe: Error-Path Walk
- Recipe: State × Method Matrix
- Recipe: Mode × Host-Capability Matrix
- Recipe: Teardown Order

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

## Arithmetic Drills

Mechanical sweeps over the diff; each takes minutes and catches a
disproportionate share of real P1s.

- **Unsigned subtraction:** find every `-` where either operand is unsigned
  (`size_t`, `uint*_t`, `.size()` results). Evaluate each at
  minuend < subtrahend and trace where the wrapped value flows. The
  `n - 1` with `n == 0` class lives here.
- **Conversions:** for every cast (explicit or implicit) on a size, length,
  offset, or id: name the source type, destination type, and the first value
  at which the conversion truncates or changes sign — and whether untrusted
  or production-realistic input can reach that value. Untrusted arithmetic
  should use `base::checked_cast`, `base::CheckedNumeric`, or
  `base::ClampedNumeric`; a raw `static_cast` on an untrusted size is a
  candidate by default.
- **Multiplication and shifts on sizes:** for `a * b` or `a << b` feeding an
  allocation or offset, compute the smallest inputs that overflow and ask
  what bounds them.
- **Rate, token-bucket, and throughput types:** probe four named values
  through every conversion and refill path — `0`, the smallest sub-unit
  positive value (e.g. 0.4 kbps before a ×1024 cast), each "unlimited"
  sentinel, and "accumulating while consumers are queued / while time
  advances". The last probe is the one runs keep skipping: token caps that
  only apply when the queue is empty quietly break the rate limit while
  work is waiting.

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

## Recipe: State × Method Matrix

Trigger: a class with a state enum, or implicit states formed by member
combinations (bools, optionals, null-vs-set pointers, pending callbacks).

1. Enumerate the states, including implicit ones.
2. Build a matrix of states × public entry points (methods, callbacks, the
   destructor).
3. For each cell: is the call legal in that state, what enforces that, and
   what actually happens if it occurs?
4. **Trace Telemetry & Cancellation:** If the class records UMA
   metrics/telemetry:
   - Identify cells in the matrix where an operation is cancelled or aborted
     while a background task, I/O, or asynchronous operation is pending
     (e.g., in-flight network, disk, IPC, or task runner wait).
   - If the async completion callback/method still runs later (even to perform
     no-op or cleanup), verify that success-only metrics (e.g., duration,
     success count, size/ratio metrics) are *not* logged. Ensure logging is
     gated so aborted attempts do not pollute success statistics.


Spend extra attention on the cells inspiration never visits: a method called
after Close/Abort/error, the same method called twice, and any entry point
arriving while an async operation is in flight. Edge cases are cells of this
matrix; enumerating them mechanically beats hoping to notice them. Return
the rendered table with every cell marked (legal/enforced/what-happens or
not-checked); unvisited cells are candidates, not omissions.


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
