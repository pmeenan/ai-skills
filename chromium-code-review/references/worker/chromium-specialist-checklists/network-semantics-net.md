<!-- Generated from ../../chromium-specialist-checklists.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Chromium Specialist Checklists

Load only the sections activated by deterministic inventory triggers or the
soft-likelihood routing contract. Treat
these as discovery supplements: record every anomaly as a ledger candidate and
leave severity/disposition to verification. Close a row clean only with a
`path:line` citation to the relevant guard, owner, bound, metadata, or test.

## Network Semantics (NET)

Within a routed scope, inspect URLs, requests/responses, redirects, auth/proxy, cookies/credentials,
caching/retries, fetch/navigation policy, headers, DNS, TLS/certificates,
NetworkIsolationKey/partition keys, or profile-bound network contexts.

In the thread ledger, produce `stage | URL/origin | credentials | partition key |
policy | body`, redirect/auth/retry state machine, cache-key table, network-
context ownership, and `NET-*` rows citing canonicalization/policy/isolation.

- Enforce redirect limits and re-run applicable scheme/origin/credential/
  referrer/policy checks at every security transition and final URL.
- Separate server/proxy auth, prevent credential forwarding, and avoid loops or
  inappropriate prompts.
- Retry only idempotent/permitted operations; prove body replayability and handle
  partial upload/response without duplicated effects.
- Set cookie/credentials mode deliberately; preserve SameSite, secure,
  partitioned, third-party-cookie, and storage-access policy.
- Carry correct NetworkIsolationKey/NetworkAnonymizationKey, top-frame site,
  nonce, and storage partition through redirects, caches, sockets, DNS, proxy.
- Include all response-varying security/content dimensions in cache keys; honor
  `Vary`, method, credentials, range/encoding, validation, and no-store/private.
- Apply CORS, CSP, CORP, COEP/COOP, mixed-content, Private Network Access, and
  download/navigation policy to internal, cached, and preloaded paths too.
- Verify TLS/cert hostname/error/pinning/CT/downgrade/client-cert behavior and
  profile-bound exception storage.
- Use standard URL/header canonicalization. Reject CR/LF injection, conflicting
  lengths, forbidden headers, ambiguous IPs, and userinfo confusion.
- Test redirects, auth/proxy, non-replayable body, credential/partition isolation,
  `Vary`, blocked policy, malformed URL/header, cert errors, and profile teardown.
