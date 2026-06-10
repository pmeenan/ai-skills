# Ground Truth: CL 7703417 @ Patchset 29 — Blind-Review Eval Fixture

⚠️ EVAL GROUND TRUTH — do not read this file during a blind review phase.
Comparison/grading phase only.

Pinned target: CL 7703417 ("Add socket-layer network delay primitives"),
**patchset 29** (ref `refs/changes/17/7703417/29`, revision
`cc2025abca04229e3ffe6fba2ea18e7a54519abe`). Source: a consolidated report of
four independent reviews of PS29, each finding verified against PS29 source;
key claims re-verified against the Gerrit revision on 2026-06-10. Line
numbers are PS29 lines. Severity labels are the review's (P0/P1/P2 ≈ the
skill's P1/P2/P3); note severity disagreements, do not count them as misses.

This CL is large and target-rich, and it was abandoned mid-review — the
ground truth below is *known-found*, not exhaustive. A blind-review finding
that is not on this list is NOT automatically a false positive: list such
findings separately as "novel candidates" for human adjudication.

Grading per item: **Identified** (same root cause and consequence, any
wording) / **Partially identified** (right code flagged, wrong or incomplete
root cause/consequence, or only some sub-parts of a bundled item) /
**Missed**. Report three numbers: P0 recall (x/9), P1 recall (x/3), P2
recall (x/9). Grade strictly: a test-gap mention of the same area ("upload
throttling is untested") is at most Partial for a correctness item, and an
adjacent style nit does not satisfy a design-shape item — measured runs have
stretched both.

## P0 — correctness/safety, must fix

- **GT-1 `ReadIfReady` violates the Socket contract** —
  `net/socket/delayed_stream_socket.cc:198-247, 317-339`;
  `delayed_stream_socket.h:191`. Two sub-violations (either = Partial, both
  = Identified): (a) the caller's `IOBuffer` is retained across
  `ERR_IO_PENDING` — and in a bare `raw_ptr`, so a caller that drops its ref
  leaves a dangling pointer the wrapper later writes through; (b) the async
  callback fires with a positive byte count, where the contract
  (`net/socket/socket.h:42-53`) requires `OK` and a caller retry.
  Consequence: `SocketBIOAdapter` (TLS) frees its buffer on pending and
  `CHECK`s on positive results → UAF or CHECK-crash on first delayed TLS
  read.
- **GT-2 `~NetworkContext` leaks isolated sessions (UAF risk)** —
  `services/network/network_context.cc:956-969` (PS29 line 964). The
  destructor calls `session->factory_handle->Reset()` but never sets
  `factory_handle = nullptr`, leaving the
  session→handle→session ref cycle intact (the
  `SetSocketLayerNetworkConditions` path at :1925-1928 does both). Leaked
  `HttpNetworkSession` holds raw pointers into the dying
  `URLRequestContext`; any background task touching the leaked pools after
  destruction is a UAF.
- **GT-3 Download bytes silently dropped on partial `Push`** —
  `delayed_stream_socket.cc:270, 294`; `bottleneck_buffer.cc:54-77`. Inner
  reads always pull up to 32KB; `BottleneckBuffer::Push` accepts only up to
  free capacity and returns the accepted count — which is discarded. Near a
  full buffer (the entire point of backpressure), excess bytes vanish:
  silent stream corruption.
- **GT-4 Upload bytes silently dropped on partial inner `Write`** —
  `delayed_stream_socket.cc:438-471`. `DrainUploadBuffer` /
  `OnInnerWriteComplete` treat any `rv >= 0` as "all pulled bytes written";
  short writes (legal per `socket.h:60-71`) truncate TLS records / request
  bodies.
- **GT-5 Buffer capacity overflow on "unlimited" sentinel mismatch** —
  `delayed_stream_socket.cc:62-72`; `bottleneck_buffer.cc:24-35`, `.h:67`.
  `BottleneckBuffer::kUnlimitedThroughput == 0` but the config sentinel is
  `UINT64_MAX`; `BdpCapacity` only short-circuits on 0, so the
  latency-only/shared-throttle configs compute a ~1.8e18 BDP — `full()`
  never trips and backpressure is disabled entirely.
- **GT-6 Datagram throughput collapse (breaks QUIC)** —
  `delayed_datagram_socket.cc:114-140, 300-313`. No read-ahead: every
  `Read()` is delayed half-RTT individually, so N kernel-buffered packets
  deliver serially at `k * half_RTT` — receive throughput collapses to
  ~1/half_RTT packets/sec regardless of configured bandwidth, wrecking QUIC
  handshake/congestion behavior.
- **GT-7 Throttle callbacks outlive the socket (UAF) + reentrancy** —
  `delayed_stream_socket.cc:169-174, 355-361, 528-533`;
  `bandwidth_throttle.cc:33-54, 78-100`. Bundle (any one = Partial, ≥2 = 
  Identified): (a) app callbacks are moved into bare lambdas queued on the
  throttle, surviving `Disconnect()`/destruction → UAF; (b)
  `RequestBytes` completes synchronously on the fast path, firing the
  callback before `Read` returns `ERR_IO_PENDING` (reentrancy contract
  violation); (c) the `!front.callback` staleness check is dead code — a
  bound `OnceClosure` doesn't null itself when its object dies.
- **GT-8 Upload bandwidth bypass for fitting writes** —
  `delayed_stream_socket.cc:67-72, 397-471, 528-533`. With a shared
  `upload_throttle_`, the per-socket buffer is set "unlimited" and the
  throttle is consulted ONLY on the partial-accept retry path — every write
  that fits the buffer (the common case) is never throttled.
- **GT-9 DNS delay never wired into production** —
  `services/network/network_context.cc:1903-1959`;
  `net/dns/delayed_host_resolver_wrapper.cc:54-66, 99-121`. Two sub-parts
  (one = Partial, both = Identified): (a) `SetSocketLayerNetworkConditions`
  never installs `DelayedHostResolverWrapper` — the isolated session
  resolves DNS undelayed; (b) even if installed, the wrapper passes
  `CreateServiceEndpointRequest` through undelayed, which is what modern
  connect paths (`tcp_connect_job.cc:164`,
  `http_stream_pool_attempt_manager.cc:1131`) use.

## P1 — fix before LGTM

- **GT-10 Unbounded token accumulation while data queued** —
  `bottleneck_buffer.cc:259-269`. `RefillTokens` caps at `burst_size_` only
  when `chunks_.empty()`; a slow consumer lets tokens grow unbounded, and
  the next `Pull` drains far past the configured rate. Fix shape: cap at
  `burst_size_ + buffered_bytes_`.
- **GT-11 Division-by-zero for sub-1KB/s configs** —
  `bandwidth_throttle.cc:118`; `delayed_datagram_socket.cc:266-274`;
  `network_context.cc` kbps conversion. `kbps > 0` with
  `static_cast<uint64_t>(0.4 * 1024.0) == 0` builds a throttle with
  `throughput_bytes_per_sec_ == 0` → divide-by-zero in the drain timer /
  `ComputeThroughputDelay`.
- **GT-12 Isolated sessions skipped by context-wide cleanup APIs** —
  `network_context.cc:1450-1500, 1548-1600, 1854-1876`. `ClearHttpCache`,
  `ClearHttpAuthCache`, `CloseAllConnections`, `CloseIdleConnections`
  operate only on the primary session; isolated caches/auth/sockets/TLS
  keys survive "clear everything".

## P2 — structural/polish tier

- **GT-13 Unbounded recursion on synchronous inner completion** —
  `delayed_stream_socket.cc:275-277, 462-463`. `StartInnerRead` /
  `DrainUploadBuffer` self-recurse on sync completion; mock sockets (and
  the GT-5 overflow) can blow the stack.
- **GT-14 Dead state-juggling in the `Read` throttle branch** —
  `delayed_stream_socket.cc:161-174`. Sets then immediately clears pending
  state; bypasses the `DCHECK(!pending_read_callback_)` invariant.
- **GT-15 Initial-token inconsistency** — `bandwidth_throttle.cc:24-29`
  (full burst) vs `bottleneck_buffer.cc:37-50` (zero); both can apply to
  one socket — harmonize or document.
- **GT-16 `prevent_destruction_guard_` as a never-run `OnceClosure`** —
  `url_request_http_transaction_factory_override.h:34-50`; a typed
  `scoped_refptr` member is clearer.
- **GT-17 `Connect()` vs `ConnectAsync()` latency asymmetry** —
  `delayed_datagram_socket.cc:28-93`; same underlying op, only one path
  adds half-RTT.
- **GT-18 `SetIsSharedDictionaryReadAllowedCallback` silently no-ops** —
  `http_network_transaction.cc:831-836`; shared-dictionary reads silently
  broken inside isolated sessions; needs at least a log/doc.
- **GT-19 Partial isolation is undocumented** — cookies/HSTS/ALPN/server
  properties remain shared with the primary session ("Slow 3G but instantly
  negotiates HTTP/2"); document the model.
- **GT-21 Stale `bandwidth_throttle.h` callback comment** — claims the
  callback "receives the delay as a TimeDelta"; the type is
  `base::OnceClosure`.
- **GT-22 Test-gap bundle** (≥3 named gaps = Identified, 1-2 = Partial):
  no tests for ReadIfReady-with-TLS-style consumer, partial `Push`, partial
  inner `Write`, `BdpCapacity` with the unlimited sentinel, UDP burst
  arrival, `Disconnect()` with queued throttle request / sync throttle
  completion, shared-upload-throttle correctness, slow-consumer token
  accumulation, sub-1KB/s config, `~NetworkContext` with an active
  isolated session.

## Adjudicated additions (found by eval runs, verified post-hoc)

Score these separately as "A recall (x/5)" so the historical P0/P1/P2
denominators stay comparable across runs.

- **A-1 Write hang on synchronous drain (P0-class)** —
  `delayed_stream_socket.cc:~401-411`. `DrainUploadBuffer()` runs *before*
  `pending_write_callback_` is assigned; if the inner write completes
  synchronously and empties the buffer, the completion fires into a null
  callback and `Write()` returns `ERR_IO_PENDING` with no completion ever
  delivered — permanent hang. Adjudicated 2026-06-10 by direct PS29 source
  verification (ordering confirmed); a sibling of the PS51 review's B1.
  Independently rediscovered by all three baseline eval models.
- **A-2 `BottleneckBuffer` synchronous-callback reentrancy/UAF (P0-class)** —
  `bottleneck_buffer.cc:136-137, 184-185, 313-314`. `Pull`/`PullFront`/the
  drain path invoke `space_available_cb_`/`data_ready_cb_` synchronously;
  a consumer that reads/destroys the owning socket reenters or frees the
  buffer mid-method. Adjudicated via the PS44 review's finding A3, which
  independently describes this bug on the reworked code; the same pattern
  exists at PS29. Missed by all four PS29 reviews.
- **A-3 Mid-flight fallback to the unthrottled default factory (P2-class)** —
  `net/url_request/url_request_http_job.cc:~736-741` +
  `url_request_http_transaction_factory_override`. Once the handle is
  `Reset()` (profile cleared/updated), the override `Get()` returns null and
  in-flight/not-yet-started requests silently fall back to the primary,
  unthrottled factory instead of failing or staying isolated. Adjudicated
  via the PS51 review's S13, which independently describes the same
  fallback behavior on later code; found blind at PS29 by a second eval
  model.
- **A-4 `BandwidthThrottle::ProcessQueue` runs the callback before popping
  (P2-class)** — `net/socket/bandwidth_throttle.cc:81-99`. The front
  request's callback runs while the request is still in
  `pending_requests_`; a reentrant `RequestBytes` (or a callback that drops
  the last throttle reference) recurses into `ProcessQueue` and double-pops
  or frees the queue under the outer frame. Adjudicated via the PS51
  review's S4, which independently describes the same pop-after-run hazard
  on later code; found blind at PS29 by two eval models.
- **A-5 `Disconnect()` permanently poisons the buffer callbacks (P2-class)** —
  `delayed_stream_socket.cc` (`Disconnect` calls
  `weak_factory_.InvalidateWeakPtrs()`; the `BottleneckBuffer`
  ready/space-available callbacks are bound once in the constructor and never
  re-armed). A reconnect — valid per `stream_socket.h` — yields a socket
  whose buffers can never notify it: reads hang. Adjudicated via the PS51
  review's B3, which independently describes the same poisoning on later
  code; found blind at PS29 by a fourth eval model.

## Not graded

- **Doc/code mismatch** (design doc / review guide describe
  `IsPartOfSequence()` / `kSequenceThreshold` that the code doesn't have):
  requires external documents outside the blind phase's allowed inputs.
- All findings from the PS43/PS44/PS51 review rounds: they target reworked
  code (`HandleInnerWriteResult`, `receive_queue_`, the
  `features::kSocketLayerNetworkConditions` flag, etc.) that does not exist
  at PS29. Do not import them into grading.
