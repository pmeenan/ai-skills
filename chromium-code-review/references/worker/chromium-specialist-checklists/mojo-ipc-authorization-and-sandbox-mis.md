<!-- Generated from ../../chromium-specialist-checklists.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Chromium Specialist Checklists

Load only the sections activated by deterministic inventory triggers or the
soft-likelihood routing contract. Treat
these as discovery supplements: record every anomaly as a ledger candidate and
leave severity/disposition to verification. Close a row clean only with a
`path:line` citation to the relevant guard, owner, bound, metadata, or test.

## Mojo IPC Authorization And Sandbox (MIS)

Within a routed scope, inspect `.mojom`, generated bindings, remotes/receivers, `ReceiverSet`,
associated interfaces, binder registration, messages crossing a process,
process/frame/document identity, handle transfer, broker calls, sandbox policy,
allowlists, handle inheritance, syscalls, or entitlements.

In the thread ledger, produce before/after wire contracts, an old/new peer matrix,
`sender/principal | validation | authorization | sink/capability | lifetime`,
binder-to-implementation flow, sandbox capability delta, and `MIS-*` rows.

- Preserve ordinals and existing field order. Append compatible members
  deliberately and use `MinVersion`/version queries when old peers can appear.
- Check old-to-new, new-to-old, and reconnect/update cases. Verify nullability,
  absent defaults, unknown/extensible enums, unions, and generated defaults.
- Validate sizes, values, URLs/origins, tokens, and handles before allocation,
  indexing, arithmetic, authority lookup, or resource acquisition.
- Authenticate and authorize at the privileged receiver. Treat object existence
  separately from permission to operate on it.
- Ensure `ReceiverSet` context is authentic and fresh across navigation,
  process swap, profile/storage partition, permission changes, and object reuse.
- For browser-process storage, origin, or capability binders (`content/browser/`
  frame and worker binders), verify all three orthogonal isolation and lifetime
  checks separately:
  1. **Profile & `StoragePartitionConfig` isolation:** check both
     `BrowserContext::IsOffTheRecord()` and `StoragePartitionConfig::in_memory()`
     / non-default `StoragePartition`s (such as non-persistent `<webview>`
     guests inside a regular `BrowserContext`) so in-memory or isolated guest
     partitions never share a regular profile's persistent on-disk store.
  2. **`StorageKey` nonce & partitioning:** check
     `storage_key.ForbidsUnpartitionedStorageAccess()` (`storage_key.nonce()`)
     and third-party `StorageKey` partitioning (`storage_key.top_level_site()`);
     never extract `storage_key.origin()` alone while dropping `nonce()`, which
     lets `<iframe credentialless>` and fenced frames read or write persistent
     unpartitioned storage.
  3. **Process authorization & host-scoped lifetime:** check
     `ChildProcessSecurityPolicy::CanAccessDataForOrigin(process_id, origin)`
     at bind/request time (even when `origin` comes from browser-side
     `GetStorageKey()`, because `CanAccessDataForOrigin` blocks restricted
     processes such as PDF renderer processes), null-check
     `ServiceWorkerHost::GetProcessHost()` during worker shutdown races, and
     scope per-frame receivers with `content::DocumentService` (and worker
     bindings with host-owned `ReceiverSet`s) rather than `MakeSelfOwnedReceiver`.
- Trace binder exposure through every factory. Do not expose an interface to a
  broader process/origin/frame state or feature configuration than intended.
- Verify associated-interface ordering only within its guarantee; handle
  disconnect/rebind and traffic on unrelated pipes/task runners.
- Minimize transferred handle type/rights; verify duplication, inheritance,
  transfer, peer closure, revocation, and release ownership.
- Bound message/array size, queued calls, outstanding replies, receiver count,
  and per-client work; disconnection alone is not resource control.
- Treat every broker operation, sandbox allowlist, syscall, entitlement,
  namespace, device, file, registry, or IPC exception as capability expansion.
  Require the narrowest platform scope and a cited caller.
- Test malformed/old-version messages, unauthorized or stale principals,
  cross-profile/document reuse, disconnect races, queue pressure, revocation,
  and bad-message isolation.
