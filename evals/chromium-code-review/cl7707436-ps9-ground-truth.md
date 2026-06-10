# Ground Truth: CL 7707436 @ Patchset 9 — Blind-Review Eval Fixture

⚠️ EVAL GROUND TRUTH — do not read this file during a blind review phase.
Comparison/grading phase only.

Pinned target: CL 7707436, **patchset 9** (ref `refs/changes/36/7707436/9`).
Source: the union of inline review comments on PS9 and PS10 (human + agent
review rounds), with each item verified present in PS9 code on 2026-06-09.
Items flagged on PS10 that do not exist in PS9 are listed under Excluded.
Line numbers are PS9 lines. Severity labels are advisory (taken from the
review comments); grade identification, and note severity disagreement
separately rather than counting it as a miss.

Grading per item: **Identified** (same root cause and consequence, any
wording) / **Partially identified** (right code flagged, but wrong or
incomplete root cause or consequence) / **Missed**. Report P1+P2 recall and
P3 recall as separate numbers.

## P1 — must-fix correctness

- **GT-1 Lagging parallel-writer corruption** —
  `net/http/http_cache_transaction.cc:405` + `http_cache_writers.cc` (PS9 has
  no join/single-writer guard). When compressing, parallel writers cannot
  catch up from the cache (disk bytes are compressed; `read_offset_` tracks
  uncompressed bytes), so the `compressing_for_cache()` gate forces them to
  network reads; a lagging writer receives stream-front bytes at the wrong
  offset → silent body corruption. Fix direction: enforce a single-writer /
  no-late-join invariant while compressing. Two distinct mechanisms both
  count as this item: (a) an already-joined writer lagging behind the stream
  front, and (b) a late transaction joining after compression has started.
  A correct trace of either = Identified; note whether both were covered.
- **GT-2 Truncated response cached as complete** —
  `http_cache_writers.cc:613-616`. The Content-Length truncation check is
  skipped when `compressing_for_cache_` ("avoid a false-positive truncation
  signal"), so a mid-stream network drop finalizes and caches a truncated
  frame as complete. The check must compare received wire bytes against
  Content-Length instead of disk size.
- **GT-3 Content-Encoding gate is production dead-code** —
  `http_cache_writers.cc:729` (also 350). The gate rejects any response with
  a Content-Encoding header, but real CDT responses carry
  `Content-Encoding: dcb` or `dcz` → the feature is unreachable in
  production. Must permit dcb/dcz (align with shared-dictionary encoding
  parsing).
- **GT-4 `Compress()` failure treated as success** —
  `http_cache_writers.cc:~527`. On `Compress() < 0` the code calls
  `OnCacheWriteFailure()` (which nulls `active_transaction_` and resets the
  compressor) and then returns `write_len_` (positive) → the state machine
  proceeds as success and downstream code dereferences the nulled state.
- **GT-5 Finalize failure leaves stale `next_state_`** —
  `http_cache_writers.cc:~753-793` (`DoCacheWriteCompressedFinalize*`). On
  `Finalize()` failure or `kMaxFinalizeRounds` exceeded,
  `OnCacheWriteFailure()` resets `compressor_` but the error return does not
  force a terminal state → `DoLoop` can re-enter a compression state and
  crash on `DCHECK(compressor_)`.

## P2 — fix before LGTM

- **GT-6 `StopCaching` mid-compression is unhandled** —
  `http_cache_writers.cc:105-120`. `StopCaching(keep_entry=true)` after
  compressed bytes were written is not accounted for in the compression
  state. Either observable consequence counts as this item: (a) a kept
  unfinalized/partially compressed entry, or (b) a spurious doom via the
  `expected_result = compressed_write_len_` mismatch once writes stop while
  `compressing_for_cache_` remains true. Fix direction: on StopCaching with
  compressed bytes written, force `keep_entry` to false and reset
  compression state.
- **GT-7 `InitCompression` retried per chunk → mixed-format entry** —
  `http_cache_writers.cc:515-517`. If Init fails on chunk 1 ("fall through
  to uncompressed write"), chunk 2 re-evaluates
  `!compressor_ && ShouldCompressForCache()` and can succeed → uncompressed
  chunk 1 + compressed chunks 2..N in one entry. Init failure must latch
  (never retry within an entry).
- **GT-8 Cache-write failure aborts the consumer transaction** — finalize
  error paths (~770-793). Returning `ERR_CACHE_WRITE_FAILURE` at EOF fails
  the consumer's fetch even though the network transfer succeeded. The cache
  is an optimization layer: doom the entry, let the transaction complete.
- **GT-9 Load-bearing metadata write is fire-and-forget** —
  `http_cache_writers.cc:816` (`UpdateResponseInfoForCompression`).
  `zstd_uncompressed_body_size` is written with `base::DoNothing()`; if the
  write fails, the entry has a compressed body but metadata without the size
  flag → future reads serve raw zstd bytes to consumers. Await/handle the
  failure or doom the entry.

## P3 — polish, tests, perf

- **GT-10 Double index-metadata writes at EOF** —
  `http_cache_writers.cc:797-798`. `UpdateResponseInfoForCompression()` and
  `UpdateEncodedBodySizeInCacheEntry()` each write index metadata
  back-to-back; consolidate into a single write.
- **GT-11 Compressor retained after successful finalize** — success path
  (~796-802) never resets `compressor_` (only `OnCacheWriteFailure()` does),
  keeping the zstd context and buffers alive until Writers is destroyed.
- **GT-12 No chunked-delivery test coverage** — `http_cache_unittest.cc`.
  All new Zstd tests deliver the body in one mock read; multi-chunk
  `CompressAndWriteBlock` appends and the `compressed == 0` internal
  buffering path are untested. Add a chunked-delivery test.
- **GT-13 `next_state_` ordering / missing DCHECK in finalize-complete** —
  ~800-801. Set `next_state_ = State::NONE` before
  `CompleteWritingAndNotifyTransactions()` (PS9 sets it after) and restore
  `DCHECK_EQ(next_state_, State::NONE)` inside the helper.
- **GT-14 `kMaxFinalizeRounds` placement** — `http_cache_writers.h:282`.
  Only used in the .cc; move to an anonymous namespace in the
  implementation file.
- **GT-15 Platform gating for `ShouldCompressForCache`** — ~722.
  `base::Feature` lookups are not free; gate the body with a
  `NET_DISABLE_ZSTD`-style `#if` so unused platforms return false without
  the lookups.
- **GT-16 Style-nit bundle** (grade as one item; note sub-hits): prefer
  `CHECK()` over `DCHECK` for cheap checks in new code; `constexpr` for
  compile-time test constants (unittest ~16359); non-ASCII em dashes in new
  comments (`writers.cc:517`, several unittest comments); contradictory
  `ZstdCompressEmptyBody` comment (~16613); enable the decompression feature
  too in write-path tests so the feature is fully exercised.

## Excluded — not present in PS9; do not grade

- `CompressAndWriteBlock` contract/doc nit (`writers.h:221`) — the method
  was introduced in PS10.
- `set_max_uncompressed_size_for_testing` naming
  (`cache_body_compressor.h:120`) — setter introduced in PS10.
- Inverted `#if` in the suggested `NET_DISABLE_ZSTD` snippet — feedback on a
  PS10-round fix suggestion, not PS9 code.
- PS10 commit-message wording suggestions.
