<!-- Generated from ../../specialist-recipes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Specialist Deep-Dive Recipes

Run each recipe when its trigger matches the diff. Store the named work product
and create a ledger candidate for every `CANDIDATE` cell or unresolved semantic
choice. Close clean rows only with a `path:line` citation.

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
