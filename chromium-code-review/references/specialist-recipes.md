# Specialist Deep-Dive Recipes

Run each recipe when its trigger matches the diff. Store the named work product
and create a ledger candidate for every `CANDIDATE` cell or unresolved semantic
choice. Close clean rows only with a `path:line` citation.

## Contents

- Field Propagation Matrix (FPM)
- Associative Container Semantics (ACS)

## Field Propagation Matrix (FPM)

Trigger when a struct/class adds, removes, renames, retypes, or changes the
meaning/default of a field, or when copy/move/clone/serialization/identity
semantics change.

In the thread ledger, put fields in rows and every applicable
operation in columns:

`construct/default | copy ctor | copy assign | move ctor | move assign | clone |
CopyFrom/UpdateFrom | Swap | equality | ordering | hash | serialize | deserialize |
IPC/proto conversion | debug/trace | reset/clear | Oilpan Trace`

1. Find every operation, including defaulted/compiler-generated special members
   whose behavior changed because of the field type.
2. Fill each cell with `path:line`, `N/A` plus a reason, or `CANDIDATE`; create
   one `FPM-*` ledger row per candidate.
3. Verify constructors/deserializers establish a valid default for old data,
   omitted input, failure, and partial initialization.
4. Verify copy/clone/update independence and avoid duplicating unique ownership,
   registrations, handles, or identifiers.
5. Verify moves transfer ownership once and leave a source valid for destructor,
   assignment, reset, and documented observers.
6. Keep equality, ordering, and hash consistent with identity. Decide explicitly
   whether each field participates.
7. Check wire/disk round trips, versions/defaults, unknown values, and every
   conversion layer rather than only one serializer.
8. Include state in debug output, tracing, memory dumps, reset, and Oilpan
   tracing where those define observability, cleanup, or reachability.
9. Test by changing only the field. Assert round trip, moved-from destruction,
   equality/hash behavior, and clone independence separately.

## Associative Container Semantics (ACS)

Trigger on map/set/unordered/flat containers, custom hash/equality/comparator,
key canonicalization, duplicate insertion/replacement, heterogeneous lookup, or
a key field that can mutate.

In the thread ledger, produce `logical key | stored
representation | canonicalization | hash | equality | ordering | duplicate
policy` plus insert/find/update/erase cases for equivalent and distinct keys.

1. Require `a == b` to imply identical hashes. For ordered containers, verify
   strict weak ordering: irreflexive, asymmetric, transitive, and equivalent-key
   transitivity across boundary values.
2. Align hash, equality, comparator, serialization, and canonicalization on case,
   Unicode, path/URL normalization, signedness, sentinels, and ignored fields.
3. Do not mutate a hash/order/equality field while stored. Erase/reinsert or use
   stable immutable identity.
4. Define duplicate policy: reject, preserve first, replace, merge, or accumulate.
   Trace ownership/cleanup of both old and new values, including failed insert.
5. Apply canonicalization once at a documented boundary. Keep lookup, insert,
   removal, persistence, and IPC representations consistent and locale neutral.
6. For heterogeneous lookup, prove temporary keys, views/spans, and adapter
   state outlive comparison and use the intended hash/equality overloads.
7. Do not expose unordered iteration to serialization, UI, goldens, signatures,
   or protocols that need determinism; sort or specify order.
8. Test alternate equivalent keys, collisions, sentinels, duplicate replacement,
   mutation attempts, temporary lookup, erase/reinsert, and deterministic output.
9. Create an `ACS-*` ledger row for every missing invariant, ambiguous policy,
   lifetime gap, or untested semantic distinction and cite the relevant functor,
   mutation site, owner, and test by `path:line`.
