<!-- Generated from ../../chromium-specialist-checklists.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Chromium Specialist Checklists

Load only the sections activated by deterministic inventory triggers or the
soft-likelihood routing contract. Treat
these as discovery supplements: record every anomaly as a ledger candidate and
leave severity/disposition to verification. Close a row clean only with a
`path:line` citation to the relevant guard, owner, bound, metadata, or test.

## Platform And Language Semantics (PLS)

Within a routed scope, inspect build/platform guards, OS APIs, paths/handles, packed or serialized
data, CPU-specific/MacroAssembler code, V8 compiler/Torque (`.tq`) pipelines,
architecture-sized types, or Java/Kotlin, Objective-C, Rust,
JavaScript/TypeScript, Python, Shell (`.sh`), GN, Mojo, or proto sources.

In the thread ledger, produce applicable OS/arch/bitness/endianness/
build configurations, compiled implementation/tests per non-equivalent row,
language boundary hazards/tools, and `PLS-*` rows with build/test citations.

- Expand nested `BUILDFLAG`, preprocessor, GN, runtime-feature, and architecture
  conditions; find missing implementations, dependencies, tests, and branches.
- Check 32-bit truncation/layout, pointer/integer conversions, native-sized wire
  fields, alignment/packing, unaligned access, and endianness.
- For V8 Compiler, Codegen, & Torque (`.tq`):
  - **Turbofan & Maglev:** Verify graph reduction, node replacement, type/range
    mutation, and deoptimization `FrameState` invariants across optimization
    passes.
  - **MacroAssembler & Arch Backends (`x64`, `arm64`, `ia32`, `riscv`, `ppc64`, `s390x`, `loong64`):**
    Require non-aliasing register assertions (`DCHECK(!scratch.is(dst))`,
    `UseScratchRegisterScope`), verify helper macros do not clobber live
    condition flags or scratch registers, and guard `checked_cast` / immediate
    offset encoding against truncation.
  - **Torque (`.tq`) & Builtins:** Verify Torque type-hierarchy invariants,
    `cast<>` vs `UnsafeCast<>` preconditions, and builtin call descriptor
    transitioning/GC expectations.
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
- Python & Shell (`.py`, `.sh`): check Python 3 hermetic imports, subprocess
  quoting, paths/encoding, deterministic order, and timeout/error cleanup. In
  `.sh` scripts, enforce macOS BSD vs GNU Linux portability (avoid GNU-only
  `sed -i` without backup suffix, `grep -P`, `readlink -f`, `stat -c`, or
  bashisms under `#!/bin/sh`).
- GN/Mojo/proto: check target/toolchain context and generated-language defaults,
  unknown values, numbering/versioning, and regeneration inputs.
- Verify each cross-language contract in producer and consumer; bindings can
  erase nullability, ownership, signedness, errors, threads, and lifetimes.
