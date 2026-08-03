<!-- Generated from ../../chromium-specialist-checklists.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Chromium Specialist Checklists

Load only the sections activated by deterministic inventory triggers. Treat
these as discovery supplements: record every anomaly as a ledger candidate and
leave severity/disposition to verification. Close a row clean only with a
`path:line` citation to the relevant guard, owner, bound, metadata, or test.

## Platform And Language Semantics (PLS)

Trigger on build/platform guards, OS APIs, paths/handles, packed or serialized
data, CPU-specific code, architecture-sized types, or Java/Kotlin, Objective-C,
Rust, JavaScript/TypeScript, Python, GN, Mojo, or proto sources.

In the thread ledger, produce applicable OS/arch/bitness/endianness/
build configurations, compiled implementation/tests per non-equivalent row,
language boundary hazards/tools, and `PLS-*` rows with build/test citations.

- Expand nested `BUILDFLAG`, preprocessor, GN, runtime-feature, and architecture
  conditions; find missing implementations, dependencies, tests, and branches.
- Check 32-bit truncation/layout, pointer/integer conversions, native-sized wire
  fields, alignment/packing, unaligned access, and endianness.
- Verify path separators/roots/case/Unicode/reserved names/permissions/atomic
  replace, plus POSIX fd and Windows handle validity/inheritance/close behavior.
- Check OS API availability/behavior across supported SDK/deployment targets,
  libc/toolchain variants, and architectures. Scrutinize platform skips.
- Java/Kotlin/Android: check component lifecycle, configuration changes, UI vs
  binder threads, JNI local/global/weak refs, exceptions/nullability, API levels,
  and R8/Proguard behavior.
- Objective-C/C++: check ARC strong/weak/autorelease ownership, block captures,
  delegates, bridging, NSError/exception boundaries, main-thread UI calls, and
  ObjC++ destruction order.
- Rust/C++ FFI: prove `unsafe`, aliasing/pinning, ownership, encoding/length,
  repr/layout, panic/unwind, `Send`/`Sync`, callback lifetime, and error mapping.
- WebUI JS/TS: check promise cancellation/rejection, listener cleanup, stale
  results, message trust, HTML/Trusted Types sinks, DOM nullability, and bundles.
- Python: check runtime compatibility, subprocess quoting, paths/encoding,
  deterministic order, timeout/error cleanup, hermetic imports, and tests.
- GN/Mojo/proto: check target/toolchain context and generated-language defaults,
  unknown values, numbering/versioning, and regeneration inputs.
- Verify each cross-language contract in producer and consumer; bindings can
  erase nullability, ownership, signedness, errors, threads, and lifetimes.
