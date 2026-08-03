<!-- Generated from ../../chromium-specialist-checklists.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Chromium Specialist Checklists

Load only the sections activated by deterministic inventory triggers. Treat
these as discovery supplements: record every anomaly as a ledger candidate and
leave severity/disposition to verification. Close a row clean only with a
`path:line` citation to the relevant guard, owner, bound, metadata, or test.

## Mojo IPC Authorization And Sandbox (MIS)

Trigger on `.mojom`, generated bindings, remotes/receivers, `ReceiverSet`,
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
