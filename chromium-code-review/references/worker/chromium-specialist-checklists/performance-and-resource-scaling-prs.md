<!-- Generated from ../../chromium-specialist-checklists.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Chromium Specialist Checklists

Load only the sections activated by deterministic inventory triggers or the
soft-likelihood routing contract. Treat
these as discovery supplements: record every anomaly as a ledger candidate and
leave severity/disposition to verification. Close a row clean only with a
`path:line` citation to the relevant guard, owner, bound, metadata, or test.

## Performance And Resource Scaling (PRS)

Within a routed scope, inspect hot/startup code, per-frame/tab/process state, unbounded loops or
inputs, caches/queues, allocations/copies, task hops, timers/wakeups, GPU
resources, Skia/Graphite/Ganesh graphics pipelines, image codecs, `.sksl` shaders,
benchmarks, or claimed performance/memory effects.

In the thread ledger, produce `operation | cost/item | bound | fanout |
worst cost`, `resource | owner | cap | eviction/release | pressure behavior`,
before/after evidence, and `PRS-*` rows citing bounds and measurements.

- Derive time/space complexity, including hidden scans, repeated sorting,
  nested callbacks, string building, and retries on adversarial input.
- Multiply by tabs, frames, documents, origins, processes, profiles, observers,
  devices, retries, and queued events as applicable.
- Require limits and eviction for queues, maps, caches, histories, pending
  requests, and buffers. Check churn, duplicates, memory pressure, and teardown.
- Count allocations, copies, serialization passes, conversions, and temporaries;
  verify the actual overload and backing-store ownership permit moves.
- Trace thread/process hops, blocking, priority inversion, and work that wakes an
  idle process/device. Quantify polling/timer wakeups in background/no-work.
- Account for startup and binary size: static initialization, eager services,
  templates, generated tables, and per-locale/config resources.
- For GPU, Skia (`skia/`, `cc/`, `gpu/`, `viz/`), and Shader (`.sksl`, WGSL/GLSL) work:
  - **Graphite & Ganesh GPU Pipelines:** Calculate resource bytes, copies,
    synchronization, and readback; verify command buffer recording, backend
    texture binding lifetime, pipeline layout caching, draw-pass ordering
    invariants, and device loss/reset cleanup.
  - **Image Codecs & Safe Stride Math:** Enforce overflow-checked arithmetic
    (`SkSafeMath`, `base::CheckedNumeric`) on image dimensions, stride /
    row-bytes (`width * bytesPerPixel`), and buffer allocation sizes during
    stream parsing and decompression.
  - **Geometry & Coordinate Sanitization:** Verify robust geometric clipping and
    explicit `SkScalarIsFinite` / `isFinite()` sanitization on bounds, paths,
    and transform matrices before rasterization or GPU buffer upload.
  - **Color Spaces & Alpha Blending:** Check `sRGB` vs wide-gamut (`Display-P3`,
    Rec.2020) transfer function application, and enforce premultiplied
    (`kPremul_SkAlphaType`) vs unpremultiplied (`kUnpremul_SkAlphaType`) alpha
    invariants across blitters, shaders, and paint pipelines.
  - **SkSL / Shader Correctness:** Check precision qualification (`half` vs
    `float` range/underflow), vector swizzle validity, uninitialized varyings,
    and branch convergence across GPU targets (no derivative ops in non-uniform
    branches).
- Require representative benchmarks/profiles with units, variance, stable
  comparison, and a metric/trace isolating the changed work.
