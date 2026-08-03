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
- **Chunk/window charging vs delivery:** when metering charges in chunk- or
  window-sized units, desk-check one read/`Pull`/`Write` that spans a chunk
  boundary and compare bytes charged with bytes delivered. Charging the
  front chunk while delivery crosses into later chunks over-delivers past
  the configured rate; this class recurs in throttling code.
