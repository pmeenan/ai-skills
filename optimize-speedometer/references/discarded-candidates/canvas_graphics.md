# Discarded Candidates: 2D Canvas & Graphics Pipeline

Subsystem: `third_party/blink/renderer/modules/canvas/`, `platform/graphics/`, `cc/paint/`

---

## CANV-01: `Canvas2DRecorderContext::DrawPathInternal` Full-Circle Arc to `drawOval`
- **Concept:** When `arc(x, y, r, 0, 2*PI)` is called, emit a `drawOval` paint op instead of constructing a full SkPath circular contour.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `f962a0a15a3d3`).
- **Empirical Result:** Directly regressed target story `Charts-chartjs` **`-2.50% [-3.28%, -1.71%]`**.
- **Causal Failure Mechanism:** In Skia's GPU playback pipeline, `drawOval` and `drawArc`/`drawPath` are serialized as different `PaintOp` types. Chart.js draws hundreds of circular markers in batch; converting full circles to ovals broke Skia's internal paint op batching, causing more draw calls and GPU state flushes.
- **Durable Invariant:** Do not convert SkPath arcs to Skia ovals/rectangles without verifying Skia GPU op-merging and batching behavior; op-type diversity prevents batch draw call collapsing.

---

## CANV-02: `Canvas2DRecorderContext::setTransform` CTM Redundancy Check
- **Concept:** Check if the new 6-element affine transform matrix equals the current transform in `Canvas2DRecorderContext::setTransform` and return early.
- **Rejection Stage:** Clean-Branch Isolation A/B (Commit `2aff51c8caf23`).
- **Empirical Result:** Stat-sig regression on `TodoMVC-WebComponents-Complex` (`-2.14%`).
- **Causal Failure Mechanism:** Redundant `setTransform` calls were exceedingly rare in the benchmark. The 6-float comparison (`AffineTransform` equality) executed on every valid transform change, adding pure CPU overhead without pruning work.
- **Durable Invariant:** Do not add matrix redundancy checks to Canvas 2D transform setters unless redundant calls exceed 60% of total invocations in profile traces.
