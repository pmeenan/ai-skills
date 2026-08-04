<!-- Generated from ../../chromium-specialist-checklists.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Chromium Specialist Checklists

Load only the sections activated by deterministic inventory triggers or the
soft-likelihood routing contract. Treat
these as discovery supplements: record every anomaly as a ledger candidate and
leave severity/disposition to verification. Close a row clean only with a
`path:line` citation to the relevant guard, owner, bound, metadata, or test.

## Privacy And Telemetry (PAT)

Within a routed scope, inspect identity, permissions, secrets/credentials/tokens, user/profile data,
paths, incognito/storage partitions, consent/retention/deletion, crypto/random,
logging, histogram macros/XML, UKM, source IDs, metric emission changes, or
enterprise policy surfaces (`components/policy`, `policy_templates.json`,
policy-gated behavior).

In the thread ledger, produce `datum | principal/purpose | storage/transit |
readers | retention/deletion | profile/partition`, an async authorization
timeline, `metric | site | population/frequency | value/unit | metadata`, and
`PAT-*` rows citing enforcement and emission sites.

- Authenticate/authorize at the enforcement boundary and revalidate after async
  gaps, redirects, navigation, profile changes, or object replacement.
- Defend paths against traversal, alternate/encoded separators, symlink/reparse
  races, Unicode/case aliases, and unsafe archive extraction.
- Keep secrets, credentials, tokens, private URLs, user text, and stable IDs out
  of logs, crash keys, traces, errors, lower-trust IPC, and debug persistence.
- Bound attacker-controlled allocation, parsing, decompression, recursion,
  concurrency, retries, and queueing before incurring the cost.
- Use reviewed crypto/secure randomness; verify nonce uniqueness, key lifetime,
  authentication-before-use, downgrade behavior, and errors.
- Isolate regular/incognito/guest/managed/system profiles and storage partitions.
  Require purpose, minimization, consent/policy, retention, deletion, and cleanup
  across backup/sync/cache copies.
- For enterprise policies: verify schema and `policy_templates.json`
  documentation match the implementation, dynamic-refresh behavior is
  deliberate, precedence against user settings is defined, and a
  policy-disabled path is tested.
- Match histogram type, unit, range, buckets, name, summary, expiry, and XML.
  Preserve enum numbers, never reuse retired values, and cover emitted maxima.
- Count UMA emissions per logical event across retries, duplicate observers,
  restore, success, and error paths.
- For UKM, verify source/document identity freshness, consent/policy/incognito
  gates, profile isolation, cardinality, identifiability, and absence of PII.
- Test non-emission when gated plus duplicate-callback, incognito, stale
  principal, oversized input, deletion, and teardown paths.
