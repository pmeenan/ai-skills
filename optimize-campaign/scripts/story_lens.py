#!/usr/bin/env python3
"""Decompose per-story collapsed stacks into reviewer-facing "lenses".

The campaign's profile frontier ranks outermost Blink entry points and hides
what sits underneath them.  This script re-reads the per-story
``profile.collapsed`` files a capture already produced and emits, per story, a
fixed set of decompositions:

* ownership of self time (who owns the leaf frame),
* what triggered the work (main-frame update, forced layout, timers, ...),
* which rendering/DOM phase the work belongs to (whole story, per trigger, and
  a self-time view keyed by the leaf-most phase frame),
* which bindings entry forced synchronous style/layout,
* a V8 lens (IC feedback state, compilation, GC, API callbacks),
* binding plumbing self time in both directions,
* profiling overhead (perf logging, allocation sampling, unknown frames),
* an "underneath" view for every frontier candidate, and
* coverage arithmetic (how much addressable time the frontier explains).

Only the standard library is used; results are deterministic.  Every share is
a percent of the story's total collapsed weight, rounded to three decimals.

Usage::

    python3 story_lens.py --capture-dir <dir> [--capture-dir <dir> ...] \
        --out lens.json [--markdown lens.md] [--top 12] [--floor-pct 1.0]

``--capture-dir`` accepts either the capture root (the directory that contains
``analysis/``) or the ``analysis/stories`` directory itself.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import multiprocessing
import os
import pathlib
import re
import sys
import time

SCHEMA_VERSION = 1

# --------------------------------------------------------------------------
# Classifier tables.  Every table is an ordered list of (name, compiled regex);
# order matters wherever "first match" semantics are documented.  Extend by
# adding rows.
# --------------------------------------------------------------------------

# 1. Ownership of the leaf frame (first match wins).
OWNERSHIP = [
    ("jit-js", re.compile(r"^(?:JS:|LazyCompile|Function:|Script:|RegExp:|RegExp\.|Eval:|\*|~)|perf-\d+\.map")),
    ("v8-builtin", re.compile(r"Builtins_")),
    ("v8-cpp", re.compile(r"v8::|^_ZN2v8|^cppgc::")),
    ("blink", re.compile(r"blink::|WTF::|^_ZN5blink|^_ZN3WTF")),
    ("cc-skia-gpu", re.compile(r"^cc::|^gpu::|(?<![A-Za-z])Sk[A-Z]|skia|^viz::|GrOp")),
    ("harfbuzz-icu", re.compile(
        r"^hb_|_hb_|^OT::|^AAT::|^icu|^u_|^ubrk|^u[a-z]+_[A-Za-z_]*\d+\(|^apply_(?:forward|backward)\b|"
        r"^getGeneralCategory|^skrifa::|^<skrifa::|^read_fonts::")),
    ("allocator", re.compile(r"partition_alloc|allocator_shim|malloc|\bfree\b|operator new|operator delete|base::allocator::dispatcher")),
    ("libc", re.compile(
        r"memcpy|memmove|memset|__mem|__str|__GI_|_IO_|__printf|__vfprintf|^pthread_|^pkey_|^clock_gettime|"
        r"@@GLIBC")),
    ("kernel-unknown", re.compile(r"\[unknown\]|\[kernel|entry_SYSCALL|syscall")),
    ("chromium-other", re.compile(r"base::|content::|mojo::|absl::|std::|^CRYPTO_|^md5_block|^sha\d*_block|^bssl::")),
]
OWNER_NAMES = [name for name, _ in OWNERSHIP] + ["other"]
OWNER_INDEX = {name: index for index, name in enumerate(OWNER_NAMES)}
ADDRESSABLE_OWNERS = ("blink", "chromium-other", "cc-skia-gpu", "harfbuzz-icu", "allocator", "libc")
HANDOFF_OWNERS = ("jit-js", "v8-builtin", "v8-cpp", "kernel-unknown")

# 2. Triggers.  frame-update and hit-test-lifecycle win wherever they appear in
# the stack; the remaining rows are assigned by the first matching frame walking
# root -> leaf; script-other catches everything else under BeginMainFrame.
TRIGGER_FRAME_UPDATE = "frame-update"
TRIGGER_HIT_TEST = "hit-test-lifecycle"
TRIGGER_FORCED = "forced-style-layout"
TRIGGER_SCRIPT_OTHER = "script-other"
TRIGGER_OTHER = "other"
TRIGGERS = [
    (TRIGGER_FRAME_UPDATE, re.compile(r"^cc::LayerTreeHost::RequestMainFrameUpdate")),
    (TRIGGER_HIT_TEST, re.compile(r"^blink::LayoutView::HitTest\(|^blink::HitTestInDocumentImpl")),
    (TRIGGER_FORCED, re.compile(
        r"^blink::Document::UpdateStyleAndLayout\(|"
        r"^blink::Document::UpdateStyleAndLayoutForNode|"
        r"^blink::LocalFrameView::UpdateStyleAndLayout\(\)|"
        r"^blink::Document::UpdateStyleAndLayoutTree\(|"
        r"^blink::Document::UpdateStyleAndLayoutTreeForThisDocument")),
    ("commit", re.compile(
        r"^cc::LayerTreeHost::UpdateLayers|^cc::LayerTreeHost::WillCommit|"
        r"^cc::ProxyMain::\w*Commit|^cc::CommitState|"
        r"^(?:non-virtual thunk to )?blink::WebFrameWidgetImpl::\w*Commit|"
        r"^blink::LayerTreeView::\w*Commit")),
    ("did-begin-main-frame", re.compile(r"^blink::WidgetBase::DidBeginMainFrame")),
    ("timer-task", re.compile(r"^blink::TimerBase::RunInternal|^blink::DOMTimer::Fired")),
]
TRIGGER_NAMES = [name for name, _ in TRIGGERS] + [TRIGGER_SCRIPT_OTHER, TRIGGER_OTHER]
TRIGGER_INDEX = {name: index for index, name in enumerate(TRIGGER_NAMES)}
BEGIN_MAIN_FRAME_RE = re.compile(r"^cc::ProxyMain::BeginMainFrame|^blink::WidgetBase::BeginMainFrame")

# 3. Phases, listed from highest to lowest priority.  A stack's phase is the
# highest-priority phase matched by any of its frames, with one refinement for
# the dispatch-like phases (event-dispatch, custom-element-reactions,
# script-execution): when the leaf-most frame matching any of the three is a
# script-execution frame, the stack belongs to the script it ran rather than to
# the dispatch machinery that invoked it, unless a Blink phase also matches (in
# which case that Blink phase wins exactly as before).  Dispatch machinery keeps
# its phase only when it is the leaf-most dispatch-like frame.
PHASES = [
    ("ink-overflow", re.compile(r"RecalcInkOverflow|SetTextInkOverflow|ComputeInkBounds")),
    ("text-shaping", re.compile(r"HarfBuzzShaper|hb_shape|ShapingLineBreaker::ShapeLine|InlineNode::ShapeText")),
    ("line-breaking", re.compile(r"LineBreaker::NextLine|LazyLineBreakIterator|InlineLayoutAlgorithm::Layout")),
    ("min-max-sizing", re.compile(r"ComputeMinMaxSizes|CalculateMinMaxSizesIgnoringChildren")),
    ("layerization", re.compile(r"PaintArtifactCompositor::Update|Layerizer|PendingLayer::")),
    ("prepaint", re.compile(r"PrePaintTreeWalk|RunPrePaintLifecyclePhase")),
    ("paint", re.compile(r"RunPaintLifecyclePhase|LocalFrameView::PaintTree|PaintLayerPainter|BoxFragmentPainter|FramePainter")),
    ("hit-test", re.compile(r"HitTestNoLifecycleUpdate|PaintLayer::HitTest")),
    ("active-style-update", re.compile(r"StyleEngine::UpdateActiveStyle|CollectFeaturesTo|ApplyRuleSetChanges")),
    ("style-recalc", re.compile(
        r"StyleEngine::RecalcStyle|StyleEngine::UpdateStyleAndLayoutTree|"
        r"Document::UpdateStyleAndLayoutTreeForThisDocument|StyleResolver::|"
        r"StyleInvalidator|Element::RecalcStyle|StyleEngine::RebuildLayoutTree")),
    ("layout", re.compile(
        r"LocalFrameView::UpdateLayout|LocalFrameView::RunLayout|LayoutView::LayoutRoot|"
        r"LayoutView::UpdateLayout|blink::BlockNode::Layout|blink::BlockNode::SimplifiedLayout")),
    ("text-input-state", re.compile(r"UpdateTextInputStateInternal|CachedTextInputInfo")),
    ("custom-element-reactions", re.compile(r"CustomElementReactionStack|CustomElementReaction")),
    ("html-parsing", re.compile(
        r"ParseHTMLFragment|TryParsingHTMLFragment|HTMLFastPathParser|HTMLDocumentParser|"
        r"DOMParser::|SetContentFromDOMParser")),
    ("dom-mutation", re.compile(
        r"ContainerNode::(?:AppendChild|InsertBefore|RemoveChild|RemoveChildren|ReplaceChildren|AppendChildren)|"
        r"NotifyNodeInserted|NotifyNodeRemoved|DetachLayoutTree")),
    ("selector-query", re.compile(r"SelectorQuery|querySelector")),
    ("attribute-change", re.compile(r"SetAttributeHinted|SetAttributeWithoutValidation|AttributeChanged")),
    ("canvas-2d", re.compile(r"Canvas2DRecorderContext|BaseRenderingContext2D|Canvas2DResourceProvider|FlushCanvasInternal")),
    ("event-dispatch", re.compile(
        r"EventDispatcher::Dispatch|EventPath|DefaultEventHandler|FireEventListeners|DispatchEventInternal|"
        r"dispatchEventForBindings")),
    ("script-execution", re.compile(
        r"Builtins_JSEntryTrampoline|Builtins_InterpreterEntryTrampoline|Builtins_JSConstructStubGeneric|^JS:|"
        r"LazyCompile|\[application script execution\]|Builtins_PromiseFulfillReactionJob|"
        r"Builtins_RunMicrotasks|v8::internal::MicrotaskQueue::PerformCheckpointInternal")),
]
PHASE_OTHER = "other"
# priority: index 0 has the highest priority.
PHASE_PRIORITY = {name: len(PHASES) - index for index, (name, _) in enumerate(PHASES)}
PHASE_BY_PRIORITY = {priority: name for name, priority in PHASE_PRIORITY.items()}
PHASE_BY_PRIORITY[-1] = PHASE_OTHER
PHASE_NAMES = [name for name, _ in PHASES] + [PHASE_OTHER]
LAYOUT_PHASE_RE = dict(PHASES)["layout"]
PHASE_SCRIPT = PHASE_PRIORITY["script-execution"]
# Dispatch machinery phases that yield to script-execution under the leaf-most rule.
DISPATCH_PHASES = frozenset((PHASE_PRIORITY["event-dispatch"], PHASE_PRIORITY["custom-element-reactions"]))
DISPATCH_LIKE_PHASES = DISPATCH_PHASES | {PHASE_SCRIPT}

# Layout algorithm (first matching frame in a layout stack).
LAYOUT_ALGORITHMS = [
    ("Flex", re.compile(r"FlexLayoutAlgorithm")),
    ("Grid", re.compile(r"GridLayoutAlgorithm")),
    ("Table", re.compile(r"Table\w*LayoutAlgorithm")),
    ("Inline", re.compile(r"InlineLayoutAlgorithm")),
    ("SVG", re.compile(r"LayoutSVG")),
    ("OutOfFlow", re.compile(r"OutOfFlowLayoutPart")),
    ("Simplified", re.compile(r"SimplifiedLayout")),
    ("Block", re.compile(r"BlockLayoutAlgorithm")),
    ("Other", re.compile(r"LayoutAlgorithm")),
]
LAYOUT_ALGORITHM_NAMES = [name for name, _ in LAYOUT_ALGORITHMS]

# 4. Bindings callback frames (forced-layout attribution).
CALLBACK_RE = re.compile(r"v8_(\w+)::(\w+)Callback|blink::V8(\w+)::(\w+)Callback")
UNKNOWN_FORCED_ENTRY = "(rendering-update-or-unknown)"

# 5/7. Inclusive lens flags: (bit name, regex).  A stack carries a flag when
# any of its frames matches.
INCLUSIVE_FLAGS = [
    ("noFeedback_ic", re.compile(r"Builtins_\w*NoFeedback")),
    ("ic_miss_runtime", re.compile(
        r"Runtime_(?:Load|Store|KeyedLoad|KeyedStore|KeyedHas|Has|LoadNoFeedback)IC_Miss|Runtime_\w*IC_Slow")),
    ("compile_lazy", re.compile(r"Runtime_CompileLazy|Builtins_CompileLazy|Compiler::Compile\(")),
    ("maglev_main_thread", re.compile(
        r"StartMaglevOptimizeJob|MaglevConcurrentDispatcher::FinalizeFinishedJobs|"
        r"FinalizeMaglevCompilationJob|MaglevCompilationInfo::MaglevCompilationInfo")),
    ("baseline_compile", re.compile(r"baseline::|Builtins_CompileBaseline|InstallBaselineCode")),
    ("interceptor_runtime", re.compile(r"Runtime_\w*Interceptor")),
    ("json", re.compile(r"JsonParser|JsonStringifier|Builtin_JsonParse|Builtin_JsonStringify")),
    ("proxy", re.compile(r"Builtins_Proxy|JSProxy::")),
    ("gc", re.compile(
        r"Heap::CollectGarbage|Scavenger|MarkCompact|MinorMarkSweep|"
        r"cppgc::internal::(?:Sweeper|Marker)|MinorGC")),
    ("api_callback_generic", re.compile(r"Builtins_CallApiCallbackGeneric")),
    ("api_callback_optimized", re.compile(r"Builtins_CallApiCallbackOptimized")),
    ("perf_logging", re.compile(
        r"Logger::CodeCreateEvent|CodeEventLogger|LogFunctionCompilation|RecordFunctionCompilation|"
        r"PerfBasicLogger|PerfJitLogger|LinuxPerf|CodeEventDispatcher|V8FileLogger")),
    ("perf_write", re.compile(r"__GI___libc_write|fprintf|fwrite|_IO_file|__printf|OS::FPrint|write@plt")),
    ("heap_sampler_recording", re.compile(r"DoRecordAllocation|SamplingHeapProfiler|HeapProfilerController")),
    ("layout_phase", LAYOUT_PHASE_RE),
]
INCLUSIVE_BIT = {name: 1 << index for index, (name, _) in enumerate(INCLUSIVE_FLAGS)}
IC_MISS_BIT = INCLUSIVE_BIT["ic_miss_runtime"]
# Owners whose presence beneath an IC-miss frame means the stack is doing the
# missed property's real work (a DOM setter, JS, shaping) rather than V8's
# miss handling.
NON_V8_OWNERS = {
    OWNER_INDEX[name] for name in ("blink", "jit-js", "harfbuzz-icu", "cc-skia-gpu", "chromium-other")
    if name in OWNER_INDEX
}
V8_INCLUSIVE_KEYS = [
    "noFeedback_ic", "compile_lazy", "maglev_main_thread", "baseline_compile",
    "interceptor_runtime", "json", "proxy", "gc", "api_callback_generic",
    "api_callback_optimized",
]

# Leaf-only flags.
LEAF_FLAGS = [
    ("noFeedback_ic", re.compile(r"Builtins_\w*NoFeedback")),
    ("megamorphic_ic", re.compile(r"Builtins_\w*Megamorphic")),
    ("blink_to_v8", re.compile(
        r"blink::V8ScriptRunner::CallFunction|blink::JSBasedEventListener::Invoke|"
        r"blink::V8EventListener::Invoke|blink::JSEventHandler::Invoke|"
        r"blink::bindings::CallbackInvokeHelper|blink::IsCallbackFunctionRunnable|"
        r"blink::CallbackInterfaceBase|blink::CallbackFunctionBase|blink::ScriptState|"
        r"blink::ScriptForbiddenScope|v8::Function::Call|v8::internal::Execution::|"
        r"v8::internal::\(anonymous namespace\)::Invoke|v8::Object::CallAsConstructor|"
        r"blink::V8CustomElement\w+::Invoke|blink::V8VoidFunction::Invoke|"
        r"blink::EventDispatcher::|blink::EventTarget::FireEventListeners|blink::EventPath|"
        r"blink::Event::")),
    ("v8_to_blink", re.compile(
        r"Builtins_CallApiCallback|Builtins_HandleApiCall|v8::internal::Builtin_HandleApi|"
        r"v8::internal::FunctionCallbackArguments|v8::internal::PropertyCallbackArguments|"
        r"blink::\(anonymous namespace\)::v8_\w+::|blink::V8\w+::\w+Callback|"
        r"blink::bindings::(?!CallbackInvokeHelper)|blink::ToScriptWrappable|blink::V8DOMWrapper|"
        r"blink::ToBlinkString|blink::NativeValueTraits|blink::ExceptionState|"
        r"blink::V8SetReturnValue|blink::ToV8Traits|blink::ScriptWrappable::Wrap|"
        r"blink::V8PerContextData|blink::DOMDataStore|v8::Object::Wrap|v8::Object::Get\b|"
        r"v8::Object::Set\b|v8::internal::Runtime_\w*Interceptor|"
        r"v8::internal::(?:LoadIC|StoreIC|KeyedLoadIC|KeyedStoreIC)::|"
        r"v8::internal::Runtime_(?:Load|Store|KeyedLoad|KeyedStore)IC_Miss|"
        r"v8::internal::LookupIterator|v8::internal::IC::|"
        r"v8::internal::(?:JSObject|Object|JSReceiver)::(?:Get|Set|Has)Property|"
        r"v8::internal::Runtime_(?:Get|Set)(?:Keyed|Named)?Property|v8::internal::AccessorInfo|"
        r"v8::internal::Runtime::GetObjectProperty")),
    ("allocator_hook", re.compile(r"base::allocator::dispatcher|base::PoissonAllocationSampler")),
    ("unknown", re.compile(r"^\[unknown\]")),
    ("kernel", re.compile(r"^\[kernel|entry_SYSCALL|do_syscall|\bsys_")),
]
LEAF_BIT = {name: 1 << index for index, (name, _) in enumerate(LEAF_FLAGS)}

# 8. Wrapper frames never reported as nested descendants.
WRAPPER_RE = re.compile(
    r"^(?:_start|__libc|ChromeMain|content::|base::|non-virtual thunk|cc::ProxyMain|"
    r"blink::WidgetBase::BeginMainFrame|blink::V8ScriptRunner|v8::Function::Call|"
    r"v8::internal::MicrotaskQueue|blink::scheduler|blink::PageAnimator|"
    r"blink::FrameRequestCallbackCollection|blink::V8Frame|blink::JSBasedEventListener|"
    r"blink::V8EventListener|blink::EventTarget::FireEventListeners|blink::EventDispatcher|"
    r"blink::\(anonymous namespace\)::v8_|blink::bindings::|Builtins_|\[unknown\]|JS:|"
    r"LazyCompile|Function:|Script:|RegExp:|Eval:|v8::internal::\(anonymous namespace\)::Invoke|"
    r"v8::internal::Execution|void blink::$|blink::$)"
)

# Platform sensitivity tags for descendants (first match wins).
PLATFORM_SENSITIVITY = [
    ("font-shaping", re.compile(
        r"^hb_|_hb_|HarfBuzz|ShapeResult|SimpleFontData|Font::|ShapeCache|BoundsForGlyphs|ICU|\bicu")),
    ("rendering-backend", re.compile(
        r"(?<![A-Za-z])Sk[A-Z]|skia|cc::Paint|Raster|gpu::|Canvas2D|PaintOp|Compositor|Layerizer")),
    ("process-plumbing", re.compile(r"mojo|IPC|ipc::")),
]

MAX_SYMBOL_LENGTH = 120
TOP_V8_SELF = 8
# Chain folding for nested descendants: a frame with self share below
# CHAIN_SELF_PCT whose inclusive share is within CHAIN_ABS_PCT (absolute) or
# CHAIN_REL (relative) of an already-retained descendant of the same phase is a
# pass-through wrapper of that descendant and is folded into it.
CHAIN_SELF_PCT = 0.05
CHAIN_ABS_PCT = 0.02
CHAIN_REL = 0.01
# How many unfolded descendants (as a multiple of --top) to keep per entry for
# the cross-capture mean, so folding decisions do not have to agree per capture.
UNFOLDED_MULTIPLIER = 4

# FrameInfo tuple slots.
F_OWNER, F_TRIG, F_BMF, F_PHASE, F_ALGO, F_CB, F_FLAGS, F_LEAF, F_WRAP, F_HEAD, F_PS, F_ENTRIES = range(12)


# --------------------------------------------------------------------------
# Symbol helpers.
# --------------------------------------------------------------------------

def function_head(symbol: str) -> str:
    """Strip the parameter list, ignoring parentheses inside template args."""
    protected = symbol.replace("(anonymous namespace)", "{anonymous namespace}")
    depth = 0
    for index, char in enumerate(protected):
        if char == "<":
            depth += 1
        elif char == ">" and depth:
            depth -= 1
        elif char == "(" and depth == 0:
            protected = protected[:index]
            break
    return protected.replace("{anonymous namespace}", "(anonymous namespace)").strip()


def short_symbol(head: str) -> str:
    return head if len(head) <= MAX_SYMBOL_LENGTH else head[: MAX_SYMBOL_LENGTH - 1] + "…"


def platform_tag(head: str):
    for tag, pattern in PLATFORM_SENSITIVITY:
        if pattern.search(head):
            return tag
    return None


def callback_name(frame: str):
    match = CALLBACK_RE.search(frame)
    if not match:
        return None
    if match.group(1):
        return f"{match.group(1)}.{match.group(2)}"
    return f"{match.group(3)}.{match.group(4)}"


def pct(weight: float, total: float) -> float:
    return round(weight * 100.0 / total, 3) if total else 0.0


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Frontier entries.
# --------------------------------------------------------------------------

def candidate_symbol(candidate: dict, story: str) -> tuple[str, str]:
    """Return (kind, symbol) for a frontier candidate."""
    kind = candidate.get("kind") or "function"
    key = candidate.get("entry_key") or ""
    prefix = f"story:{story}/"
    if key.startswith(prefix):
        key = key[len(prefix):]
    for known in ("function:", "context:", "class:"):
        if key.startswith(known):
            kind = known[:-1]
            key = key[len(known):]
            break
    if kind == "context" and "@" in key:
        key = key.rsplit("@", 1)[0]
    symbol = candidate.get("name") or key
    return kind, symbol


class EntryTable:
    """Maps a frame head to the frontier entries it belongs to."""

    def __init__(self, frontier: list[dict], story: str):
        self.entries = []
        self.head_index: dict[str, list[int]] = {}
        self.class_prefixes: list[tuple[str, int]] = []
        for candidate in frontier:
            kind, symbol = candidate_symbol(candidate, story)
            head = function_head(symbol)
            index = len(self.entries)
            self.entries.append({
                "entry": symbol,
                "kind": kind,
                "head": head,
                "platform_sensitivity": candidate.get("platform_sensitivity"),
                "frontier_inclusive_share": candidate.get("inclusive_share"),
                "rank": candidate.get("rank"),
            })
            if kind == "class":
                self.class_prefixes.append((head + "::", index))
            else:
                self.head_index.setdefault(head, []).append(index)

    def lookup(self, head: str) -> tuple:
        found = self.head_index.get(head)
        result = list(found) if found else []
        for prefix, index in self.class_prefixes:
            if head.startswith(prefix):
                result.append(index)
        return tuple(result)


# --------------------------------------------------------------------------
# Frame classification (cached per distinct frame string).
# --------------------------------------------------------------------------

class FrameCache(dict):
    def __init__(self, entries: EntryTable):
        super().__init__()
        self.entries = entries

    def __missing__(self, frame: str):
        info = classify_frame(frame, self.entries)
        self[frame] = info
        return info


def classify_frame(frame: str, entries: EntryTable) -> tuple:
    owner = OWNER_INDEX["other"]
    for name, pattern in OWNERSHIP:
        if pattern.search(frame):
            owner = OWNER_INDEX[name]
            break
    trig = -1
    for index, (_, pattern) in enumerate(TRIGGERS):
        if pattern.search(frame):
            trig = index
            break
    bmf = bool(BEGIN_MAIN_FRAME_RE.search(frame))
    phase = -1
    for name, pattern in PHASES:
        if pattern.search(frame):
            phase = PHASE_PRIORITY[name]
            break
    algo = -1
    for index, (_, pattern) in enumerate(LAYOUT_ALGORITHMS):
        if pattern.search(frame):
            algo = index
            break
    flags = 0
    for name, pattern in INCLUSIVE_FLAGS:
        if pattern.search(frame):
            flags |= INCLUSIVE_BIT[name]
    leaf = 0
    for name, pattern in LEAF_FLAGS:
        if pattern.search(frame):
            leaf |= LEAF_BIT[name]
    head = function_head(frame)
    return (
        owner, trig, bmf, phase, algo, callback_name(frame), flags, leaf,
        bool(WRAPPER_RE.search(head)), head, platform_tag(head), entries.lookup(head),
    )


# --------------------------------------------------------------------------
# Nested descendant folding.
# --------------------------------------------------------------------------

def own_phase_of(symbol: str | None) -> str | None:
    """Phase named by the symbol itself (highest priority first), or None."""
    if not symbol:
        return None
    for name, pattern in PHASES:
        if pattern.search(symbol):
            return name
    return None


# Promotion: a nested descendant is a separate mechanism when its own symbol
# names a phase different from the entry symbol's own phase.  Container
# phases (layout, style recalc) count only as a genuine sub-part of the entry,
# not when they restate nearly all of it; dispatch and script phases never
# promote.  campaign_lens.py applies the same rule when it reads the file.
PROMOTION_CONTAINER_PHASES = {"layout", "style-recalc"}
PROMOTION_CONTAINER_MAX_RATIO = 0.8
PROMOTION_NEVER = {"event-dispatch", "script-execution", "other"}


def is_promoted(symbol: str, incl_pct: float, floor_pct: float,
                entry_symbol: str | None, entry_share: float | None) -> bool:
    phase = own_phase_of(symbol)
    if phase is None or phase in PROMOTION_NEVER or incl_pct < floor_pct:
        return False
    if phase == own_phase_of(entry_symbol):
        return False
    if phase in PROMOTION_CONTAINER_PHASES and entry_share and incl_pct > PROMOTION_CONTAINER_MAX_RATIO * entry_share:
        return False
    return True


def fold_descendants(unfolded: list[dict], top: int, dominant_phase: str, floor_pct: float,
                     entry_symbol: str | None = None, entry_share: float | None = None) -> list[dict]:
    """Fold pass-through chain frames and return the top descendants.

    A frame with self share below CHAIN_SELF_PCT whose inclusive share is within
    CHAIN_ABS_PCT (absolute) or CHAIN_REL (relative) of an already-retained
    descendant of the same phase is call-chain plumbing for that descendant and
    is folded into it (counted in ``chain_frames``), so the table shows
    mechanisms rather than wrappers.  ``promoted`` marks descendants whose own
    symbol names a different phase than the entry's own symbol (see
    ``is_promoted``) and whose share is at least ``floor_pct``.
    """
    ranked = sorted(unfolded, key=lambda item: (-item["inclusive_pct"], item.get("depth", 0), item["symbol"]))
    kept: list[dict] = []
    for item in ranked:
        incl_pct = item["inclusive_pct"]
        phase = item["phase"]
        if item["self_pct"] < CHAIN_SELF_PCT:
            folded = False
            for retained in kept:
                if retained["phase"] == phase and abs(retained["inclusive_pct"] - incl_pct) <= max(
                        CHAIN_ABS_PCT, CHAIN_REL * retained["inclusive_pct"]):
                    retained["chain_frames"] += 1
                    folded = True
                    break
            if folded:
                continue
        kept.append({
            "symbol": item["symbol"],
            "inclusive_pct": incl_pct,
            "self_pct": item["self_pct"],
            "phase": phase,
            "platform_sensitivity": item.get("platform_sensitivity"),
            "depth": item.get("depth", 0),
            "promoted": is_promoted(item["symbol"], incl_pct, floor_pct, entry_symbol, entry_share),
            "chain_frames": 0,
        })
        if len(kept) >= top:
            break
    return kept


# --------------------------------------------------------------------------
# Per-story aggregation.
# --------------------------------------------------------------------------

class StoryAccumulator:
    def __init__(self, entries: EntryTable, top: int, floor_pct: float):
        self.entries = entries
        self.top = top
        self.floor_pct = floor_pct
        self.cache = FrameCache(entries)
        self.total = 0.0
        self.stacks = 0
        self.owner_w = [0.0] * len(OWNER_NAMES)
        self.trigger_w = [0.0] * len(TRIGGER_NAMES)
        self.phase_w: dict[int, float] = {}
        # Self-time view: each stack is attributed to the phase of its leaf-most
        # phase-matching frame (the phase whose code is actually running).
        self.phase_self_w: dict[int, float] = {}
        self.phase_by_trigger: list[dict[int, float]] = [dict() for _ in TRIGGER_NAMES]
        self.algo_w = [0.0] * (len(LAYOUT_ALGORITHM_NAMES) + 1)
        self.forced_entry_w: dict[str, float] = {}
        self.incl_w = {name: 0.0 for name, _ in INCLUSIVE_FLAGS}
        self.leaf_w = {name: 0.0 for name, _ in LEAF_FLAGS}
        self.perf_write_w = 0.0
        self.ic_miss_v8self_w = 0.0
        self.v8_self: dict[str, float] = {}
        self.entry_incl = [0.0] * len(entries.entries)
        self.entry_self = [0.0] * len(entries.entries)
        self.entry_phase: list[dict[int, float]] = [dict() for _ in entries.entries]
        # descendants[entry][head] = [incl, self, {span phase: w}, {stack phase: w}, min depth]
        # span phase: highest-priority phase among frames entry..descendant (the
        # mechanism the descendant sits in, ignoring callers above the entry);
        # stack phase: the whole stack's phase, used when the span has none.
        self.descendants: list[dict[str, list]] = [dict() for _ in entries.entries]
        self.union_w = 0.0
        self.unexplained_addr_w = 0.0

    # The hot loop: one collapsed line.
    def add_line(self, line: str) -> None:
        stack, sep, weight_text = line.rpartition(" ")
        if not sep:
            return
        try:
            weight = float(weight_text)
        except ValueError:
            return
        if not stack:
            return
        cache = self.cache
        infos = [cache[frame] for frame in stack.split(";")]
        count = len(infos)
        self.total += weight
        self.stacks += 1
        leaf = infos[-1]
        leaf_owner = leaf[F_OWNER]
        self.owner_w[leaf_owner] += weight

        flags = 0
        best_phase = -1
        leaf_phase = -1  # leaf-most frame matching any phase
        dispatch_leaf = -1  # leaf-most frame matching a dispatch-like phase
        first_trig = -1
        has_frame_update = False
        has_hit_test = False
        bmf = False
        forced_pos = -1
        algo = -1
        first_pos: dict[int, int] = {}
        miss_pos = -1  # first IC-miss runtime frame
        work_after_miss = False  # non-V8 work (Blink, JS, fonts, Skia) beneath it
        for index, info in enumerate(infos):
            flags |= info[F_FLAGS]
            if info[F_FLAGS] & IC_MISS_BIT and miss_pos < 0:
                miss_pos = index
            elif miss_pos >= 0 and info[F_OWNER] in NON_V8_OWNERS:
                work_after_miss = True
            phase = info[F_PHASE]
            if phase >= 0:
                if phase > best_phase:
                    best_phase = phase
                leaf_phase = phase
                if phase in DISPATCH_LIKE_PHASES:
                    dispatch_leaf = phase
            trig = info[F_TRIG]
            if trig >= 0:
                if trig == 0:
                    has_frame_update = True
                elif trig == 1:
                    has_hit_test = True
                    if forced_pos < 0:
                        forced_pos = index
                else:
                    if first_trig < 0:
                        first_trig = trig
                    if trig == 2 and forced_pos < 0:
                        forced_pos = index
            if info[F_BMF]:
                bmf = True
            if algo < 0 and info[F_ALGO] >= 0:
                algo = info[F_ALGO]
            if info[F_ENTRIES]:
                for entry in info[F_ENTRIES]:
                    if entry not in first_pos:
                        first_pos[entry] = index

        if has_frame_update:
            trigger = 0
        elif has_hit_test:
            trigger = 1
        elif first_trig >= 0:
            trigger = first_trig
        elif bmf:
            trigger = TRIGGER_INDEX[TRIGGER_SCRIPT_OTHER]
        else:
            trigger = TRIGGER_INDEX[TRIGGER_OTHER]
        self.trigger_w[trigger] += weight
        # Leaf-most rule: dispatch machinery only owns the stack when no script
        # ran underneath it; Blink phases (anything outside the dispatch-like
        # set) always outrank both, exactly as before.
        if best_phase in DISPATCH_PHASES and dispatch_leaf == PHASE_SCRIPT:
            best_phase = PHASE_SCRIPT
        self.phase_w[best_phase] = self.phase_w.get(best_phase, 0.0) + weight
        self.phase_self_w[leaf_phase] = self.phase_self_w.get(leaf_phase, 0.0) + weight
        by_trigger = self.phase_by_trigger[trigger]
        by_trigger[best_phase] = by_trigger.get(best_phase, 0.0) + weight

        if flags:
            for name, bit in INCLUSIVE_BIT.items():
                if flags & bit:
                    self.incl_w[name] += weight
            if flags & INCLUSIVE_BIT["perf_logging"] and flags & INCLUSIVE_BIT["perf_write"]:
                self.perf_write_w += weight
            if flags & INCLUSIVE_BIT["layout_phase"]:
                self.algo_w[algo if algo >= 0 else len(LAYOUT_ALGORITHM_NAMES)] += weight
            # IC-miss runtime tax: the C++ miss handling itself, i.e. stacks
            # where nothing but V8 runs beneath the miss frame.  A DOM setter
            # reached through a StoreIC miss carries its Blink work and is
            # not counted here.
            if miss_pos >= 0 and not work_after_miss:
                self.ic_miss_v8self_w += weight
        leaf_flags = leaf[F_LEAF]
        if leaf_flags:
            for name, bit in LEAF_BIT.items():
                if leaf_flags & bit:
                    self.leaf_w[name] += weight
        if leaf_owner == OWNER_INDEX["v8-builtin"] or leaf_owner == OWNER_INDEX["v8-cpp"]:
            head = leaf[F_HEAD]
            self.v8_self[head] = self.v8_self.get(head, 0.0) + weight

        if trigger == 1 or trigger == 2:
            name = UNKNOWN_FORCED_ENTRY
            for index in range(forced_pos - 1, -1, -1):
                callback = infos[index][F_CB]
                if callback:
                    name = callback
                    break
            self.forced_entry_w[name] = self.forced_entry_w.get(name, 0.0) + weight

        if first_pos:
            self.union_w += weight
            leaf_entries = leaf[F_ENTRIES]
            for entry, position in first_pos.items():
                self.entry_incl[entry] += weight
                if entry in leaf_entries:
                    self.entry_self[entry] += weight
                phases = self.entry_phase[entry]
                phases[best_phase] = phases.get(best_phase, 0.0) + weight
                table = self.descendants[entry]
                entry_head = self.entries.entries[entry]["head"]
                seen = set()
                last = count - 1
                span_phase = infos[position][F_PHASE]
                for index in range(position + 1, count):
                    info = infos[index]
                    phase = info[F_PHASE]
                    if phase > span_phase:
                        span_phase = phase
                    if info[F_WRAP]:
                        continue
                    head = info[F_HEAD]
                    if head in seen or head == entry_head:
                        continue
                    seen.add(head)
                    record = table.get(head)
                    if record is None:
                        record = table[head] = [0.0, 0.0, {}, {}, index - position]
                    elif index - position < record[4]:
                        record[4] = index - position
                    record[0] += weight
                    if index == last:
                        record[1] += weight
                    record[2][span_phase] = record[2].get(span_phase, 0.0) + weight
                    record[3][best_phase] = record[3].get(best_phase, 0.0) + weight
        elif OWNER_NAMES[leaf_owner] in ADDRESSABLE_OWNERS:
            self.unexplained_addr_w += weight

    # ------------------------------------------------------------------
    def finish(self) -> dict:
        total = self.total
        owners = {name: pct(self.owner_w[index], total) for index, name in enumerate(OWNER_NAMES)}
        addressable = sum(self.owner_w[OWNER_INDEX[name]] for name in ADDRESSABLE_OWNERS)
        handoff = sum(self.owner_w[OWNER_INDEX[name]] for name in HANDOFF_OWNERS)
        owners["addressable_pct"] = pct(addressable, total)
        owners["handoff_pct"] = pct(handoff, total)

        triggers = {name: pct(self.trigger_w[index], total) for index, name in enumerate(TRIGGER_NAMES)}
        phases = self._phase_shares(self.phase_w, total)
        phase_self = self._phase_shares(self.phase_self_w, total)
        phases_by_trigger = {
            name: self._phase_shares(self.phase_by_trigger[index], total, nonzero_only=True)
            for index, name in enumerate(TRIGGER_NAMES) if self.trigger_w[index] > 0
        }
        layout_by_algorithm = {
            name: pct(self.algo_w[index], total) for index, name in enumerate(LAYOUT_ALGORITHM_NAMES)
        }
        # "Other" covers both unrecognised *LayoutAlgorithm frames and layout stacks without one.
        layout_by_algorithm["Other"] = pct(
            self.algo_w[LAYOUT_ALGORITHM_NAMES.index("Other")] + self.algo_w[len(LAYOUT_ALGORITHM_NAMES)], total)
        layout_by_algorithm["total_layout_pct"] = pct(self.incl_w["layout_phase"], total)

        forced = sorted(self.forced_entry_w.items(), key=lambda item: (-item[1], item[0]))
        forced_layout_by_entry = [
            {"entry": name, "inclusive_pct": pct(weight, total)} for name, weight in forced[: self.top]
        ]

        v8_lens = {}
        v8_lens["noFeedback_ic_incl"] = pct(self.incl_w["noFeedback_ic"], total)
        v8_lens["noFeedback_ic_self"] = pct(self.leaf_w["noFeedback_ic"], total)
        v8_lens["megamorphic_ic_self"] = pct(self.leaf_w["megamorphic_ic"], total)
        v8_lens["ic_miss_runtime_v8self"] = pct(self.ic_miss_v8self_w, total)
        for key in V8_INCLUSIVE_KEYS[1:]:
            v8_lens[f"{key}_incl"] = pct(self.incl_w[key], total)
        top_v8 = sorted(self.v8_self.items(), key=lambda item: (-item[1], item[0]))[:TOP_V8_SELF]
        v8_lens["top_v8_self"] = [
            {"symbol": short_symbol(head), "self_pct": pct(weight, total)} for head, weight in top_v8
        ]

        plumbing = {
            "blink_to_v8_self": pct(self.leaf_w["blink_to_v8"], total),
            "v8_to_blink_self": pct(self.leaf_w["v8_to_blink"], total),
        }
        overhead = {
            "perf_logging_incl": pct(self.incl_w["perf_logging"], total),
            "perf_logging_with_write_incl": pct(self.perf_write_w, total),
            "allocator_hook_self": pct(self.leaf_w["allocator_hook"], total),
            "heap_sampler_recording_incl": pct(self.incl_w["heap_sampler_recording"], total),
            "unknown_leaf_pct": pct(self.leaf_w["unknown"], total),
            "kernel_leaf_pct": pct(self.leaf_w["kernel"], total),
        }

        nested_view = []
        for index, entry in enumerate(self.entries.entries):
            phase_mix_w = self.entry_phase[index]
            dominant = -1
            if phase_mix_w:
                dominant = max(phase_mix_w.items(), key=lambda item: (item[1], item[0]))[0]
            phase_mix = self._phase_shares(phase_mix_w, total, nonzero_only=True)
            phase_mix = dict(sorted(phase_mix.items(), key=lambda item: (-item[1], item[0]))[:6])
            # Rank by inclusive share; on ties prefer the outermost frame so chain
            # folding keeps the caller rather than an alphabetically earlier callee.
            ranked = sorted(self.descendants[index].items(), key=lambda item: (-item[1][0], item[1][4], item[0]))
            unfolded = []
            for head, (incl, self_w, span_w, stack_w, depth) in ranked[: max(UNFOLDED_MULTIPLIER * self.top, 1)]:
                phase = max(span_w.items(), key=lambda item: (item[1], item[0]))[0]
                if phase < 0:
                    phase = max(stack_w.items(), key=lambda item: (item[1], item[0]))[0]
                unfolded.append({
                    "symbol": short_symbol(head),
                    "inclusive_pct": pct(incl, total),
                    "self_pct": pct(self_w, total),
                    "phase": PHASE_BY_PRIORITY[phase],
                    "platform_sensitivity": platform_tag(head),
                    "depth": depth,
                })
            descendants = fold_descendants(
                unfolded, self.top, PHASE_BY_PRIORITY[dominant], self.floor_pct,
                entry["entry"], pct(self.entry_incl[index], total))
            nested_view.append({
                "entry": entry["entry"],
                "kind": entry["kind"],
                "rank": entry["rank"],
                "inclusive_pct": pct(self.entry_incl[index], total),
                "self_pct": pct(self.entry_self[index], total),
                "frontier_inclusive_pct": (
                    round(entry["frontier_inclusive_share"] * 100.0, 3)
                    if isinstance(entry["frontier_inclusive_share"], (int, float)) else None),
                "platform_sensitivity": entry["platform_sensitivity"],
                "dominant_phase": PHASE_BY_PRIORITY[dominant],
                "phase_mix": phase_mix,
                "descendants": descendants,
                # Unfolded top-K list used to build the cross-capture mean; removed from the output.
                "_descendants_unfolded": unfolded,
            })

        coverage = {
            "frontier_inclusive_union_pct": pct(self.union_w, total),
            "addressable_pct": owners["addressable_pct"],
            "handoff_pct": owners["handoff_pct"],
            "overhead_pct": overhead["perf_logging_incl"],
            "unexplained_addressable_pct": pct(self.unexplained_addr_w, total),
        }
        return {
            "total_weight": total,
            "stack_count": self.stacks,
            "ownership_self": owners,
            "triggers": triggers,
            "phases": phases,
            "phase_self": phase_self,
            "phases_by_trigger": phases_by_trigger,
            "layout_by_algorithm": layout_by_algorithm,
            "forced_layout_by_entry": forced_layout_by_entry,
            "v8_lens": v8_lens,
            "binding_plumbing_self": plumbing,
            "overhead": overhead,
            "nested_view": nested_view,
            "coverage": coverage,
        }

    @staticmethod
    def _phase_shares(weights: dict[int, float], total: float, nonzero_only: bool = False) -> dict:
        shares = {}
        for name in PHASE_NAMES:
            priority = PHASE_PRIORITY.get(name, -1)
            weight = weights.get(priority, 0.0)
            if nonzero_only and weight <= 0:
                continue
            shares[name] = pct(weight, total)
        return shares


# --------------------------------------------------------------------------
# Capture discovery and story processing.
# --------------------------------------------------------------------------

def resolve_capture(path_text: str) -> tuple[pathlib.Path, pathlib.Path]:
    """Return (capture_root, stories_dir)."""
    path = pathlib.Path(path_text).resolve()
    if (path / "analysis" / "stories" / "stories_index.json").exists():
        return path, path / "analysis" / "stories"
    if (path / "stories_index.json").exists():
        root = path
        if path.name == "stories" and path.parent.name == "analysis":
            root = path.parent.parent
        return root, path
    raise FileNotFoundError(f"{path_text}: neither <root>/analysis/stories/stories_index.json "
                            f"nor <dir>/stories_index.json exists")


def load_stories_index(stories_dir: pathlib.Path) -> tuple[dict, str]:
    path = stories_dir / "stories_index.json"
    data = path.read_bytes()
    return json.loads(data), hashlib.sha256(data).hexdigest()


def story_tasks(capture_id: str, root: pathlib.Path, stories_dir: pathlib.Path, index: dict) -> list[dict]:
    tasks = []
    records = index.get("stories") or []
    if isinstance(records, dict):
        records = [dict(value, story=key) for key, value in records.items()]
    for record in records:
        story = record.get("story") or record.get("dir")
        if not story:
            continue
        story_dir = stories_dir / (record.get("dir") or story)
        collapsed = story_dir / "profile.collapsed"
        frontier = record.get("candidate_frontier_json")
        frontier_path = stories_dir / frontier if frontier else story_dir / "candidate_frontier.json"
        if not collapsed.exists():
            continue
        tasks.append({
            "capture_id": capture_id,
            "root": str(root),
            "story": story,
            "collapsed": str(collapsed),
            "frontier": str(frontier_path) if frontier_path.exists() else None,
            "samples": record.get("samples"),
            "samples_all_threads": record.get("samples_all_threads"),
            "score_time_composition": record.get("score_time_composition"),
        })
    return tasks


def process_story(task: dict, top: int, floor_pct: float) -> dict:
    started = time.monotonic()
    digests = {}
    frontier = []
    frontier_meta = {}
    if task["frontier"]:
        data = pathlib.Path(task["frontier"]).read_bytes()
        digests[task["frontier"]] = hashlib.sha256(data).hexdigest()
        loaded = json.loads(data)
        frontier = loaded.get("frontier") or []
        frontier_meta = {
            "quality_samples": (loaded.get("quality") or {}).get("samples"),
        }
    entries = EntryTable(frontier, task["story"])
    accumulator = StoryAccumulator(entries, top, floor_pct)
    digest = hashlib.sha256()
    collapsed = pathlib.Path(task["collapsed"])
    with collapsed.open("rb") as handle:
        remainder = b""
        add_line = accumulator.add_line
        while True:
            chunk = handle.read(1 << 23)
            if not chunk:
                break
            digest.update(chunk)
            chunk = remainder + chunk
            lines = chunk.split(b"\n")
            remainder = lines.pop()
            for raw in lines:
                if raw:
                    add_line(raw.decode("utf-8", "replace"))
        if remainder:
            add_line(remainder.decode("utf-8", "replace"))
    digests[str(collapsed)] = digest.hexdigest()
    record = accumulator.finish()
    record.update({
        "capture_id": task["capture_id"],
        "story": task["story"],
        "samples": task["samples"],
        "samples_all_threads": task["samples_all_threads"],
        "score_time_composition": task["score_time_composition"],
        "distinct_frames": len(accumulator.cache),
        "elapsed_s": round(time.monotonic() - started, 3),
    })
    if frontier_meta:
        record["frontier_meta"] = frontier_meta
    return {"story": task["story"], "capture_id": task["capture_id"], "record": record, "digests": digests}


def _worker(args):
    task, top, floor_pct = args
    return process_story(task, top, floor_pct)


# --------------------------------------------------------------------------
# Cross-capture mean.
# --------------------------------------------------------------------------

LIST_KEYS = ("symbol", "entry")
RANK_KEYS = ("inclusive_pct", "self_pct", "pct")


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def mean_records(values: list, n: int):
    """Average a list of same-shaped records (missing values count as zero)."""
    present = [value for value in values if value is not None]
    if not present:
        return None
    sample = present[0]
    if _is_number(sample):
        numbers = [value for value in present if _is_number(value)]
        return round(sum(numbers) / n, 3)
    if isinstance(sample, bool):
        return any(value for value in present if isinstance(value, bool))
    if isinstance(sample, str):
        return sample
    if isinstance(sample, dict):
        keys = []
        for value in present:
            if isinstance(value, dict):
                for key in value:
                    if key not in keys:
                        keys.append(key)
        return {
            key: mean_records([value.get(key) if isinstance(value, dict) else None for value in values], n)
            for key in keys
        }
    if isinstance(sample, list):
        lists = [value for value in present if isinstance(value, list)]
        if not lists or not all(isinstance(item, dict) for one in lists for item in one):
            return sample
        key_name = next((key for key in LIST_KEYS if all(key in item for one in lists for item in one)), None)
        if key_name is None:
            return sample
        order = []
        grouped: dict[str, list] = {}
        for one in lists:
            seen = set()
            for item in one:
                key = item[key_name]
                if key in seen:
                    continue
                seen.add(key)
                if key not in grouped:
                    grouped[key] = []
                    order.append(key)
                grouped[key].append(item)
        merged = [mean_records(grouped[key], n) for key in order]
        rank_key = next((key for key in RANK_KEYS if all(key in item for item in merged)), None)
        if rank_key:
            merged.sort(key=lambda item: (-(item.get(rank_key) or 0), str(item.get(key_name))))
        limit = max(len(one) for one in lists)
        return merged[:limit]
    return sample


def build_story_mean(per_capture: dict[str, dict], top: int, floor_pct: float) -> dict:
    """Average the per-capture records; nested descendants are merged unfolded and folded afterwards."""
    n = len(per_capture)
    captures = [per_capture[key] for key in sorted(per_capture)]
    mean = mean_records(captures, n)
    if isinstance(mean, dict):
        mean.pop("capture_id", None)
        mean.pop("elapsed_s", None)
        mean["captures"] = n
        for entry in mean.get("nested_view") or []:
            mix = entry.get("phase_mix") or {}
            if mix:
                entry["dominant_phase"] = max(mix.items(), key=lambda item: (item[1], item[0]))[0]
            unfolded = entry.pop("_descendants_unfolded", None) or entry.get("descendants") or []
            entry["descendants"] = fold_descendants(
                unfolded, top, entry.get("dominant_phase"), floor_pct,
                entry.get("entry"), entry.get("inclusive_pct"))
    for record in captures:
        for entry in record.get("nested_view") or []:
            entry.pop("_descendants_unfolded", None)
    return mean


# --------------------------------------------------------------------------
# Markdown rendering.
# --------------------------------------------------------------------------

MAX_TABLE_ROWS = 12


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _table(headers: list[str], rows: list[list], limit: int = MAX_TABLE_ROWS) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows[:limit]:
        lines.append("| " + " | ".join(_fmt(cell) for cell in row) + " |")
    return lines


def render_markdown(report: dict) -> str:
    out = ["# Story lens", ""]
    captures = report.get("captures") or []
    out.append("Captures: " + ", ".join(capture["capture_id"] for capture in captures))
    out.append("")
    out.append("All numbers are percent of each story's total main-thread collapsed weight "
               f"(mean over {len(captures)} capture(s)); `*` marks a nested descendant promoted as a separate mechanism "
               "because its own symbol names a different phase than the entry's symbol (above the floor; "
               "layout/style recalc only as a genuine sub-part).")
    out.append("")
    for story in sorted(report.get("stories") or {}):
        record = report["stories"][story]["mean"]
        owners = record["ownership_self"]
        overhead = record["overhead"]
        out.append(f"## {story}")
        out.append("")
        out.append(f"addressable {owners['addressable_pct']:.1f}% | handoff {owners['handoff_pct']:.1f}% | "
                   f"overhead (perf logging) {overhead['perf_logging_incl']:.1f}% | "
                   f"frontier union {record['coverage']['frontier_inclusive_union_pct']:.1f}% | "
                   f"unexplained addressable {record['coverage']['unexplained_addressable_pct']:.1f}%")
        out.append("")
        owner_rows = sorted(
            ((name, owners[name]) for name in OWNER_NAMES), key=lambda item: -item[1])
        out.append("Self ownership: " + ", ".join(f"{name} {share:.1f}" for name, share in owner_rows if share >= 0.05))
        out.append("")
        out.append("### Triggers")
        out.append("")
        trigger_rows = []
        for name in TRIGGER_NAMES:
            share = record["triggers"].get(name, 0.0)
            if share <= 0:
                continue
            mix = record["phases_by_trigger"].get(name) or {}
            top_phases = sorted(mix.items(), key=lambda item: -item[1])[:3]
            trigger_rows.append([name, share, ", ".join(f"{phase} {value:.1f}" for phase, value in top_phases)])
        trigger_rows.sort(key=lambda row: -row[1])
        out.extend(_table(["trigger", "share", "top phases"], trigger_rows))
        out.append("")
        out.append("### Phases (whole story)")
        out.append("")
        phase_self = record.get("phase_self") or {}
        phase_rows = sorted(
            ([name, share, phase_self.get(name, 0.0)] for name, share in record["phases"].items()
             if share > 0 or phase_self.get(name, 0.0) > 0),
            key=lambda row: (-row[1], -row[2]))
        out.extend(_table(["phase", "share", "self (leaf-most phase)"], phase_rows))
        algorithms = record.get("layout_by_algorithm") or {}
        algo_text = ", ".join(
            f"{name} {algorithms[name]:.1f}" for name in LAYOUT_ALGORITHM_NAMES if algorithms.get(name, 0) > 0)
        if algo_text:
            out.append("")
            out.append(f"Layout stacks {algorithms.get('total_layout_pct', 0):.1f}% by algorithm: {algo_text}")
        out.append("")
        forced = record.get("forced_layout_by_entry") or []
        if forced:
            out.append("### Forced style/layout by bindings entry")
            out.append("")
            out.extend(_table(["entry", "share"], [[item["entry"], item["inclusive_pct"]] for item in forced]))
            out.append("")
        v8 = record["v8_lens"]
        v8_bits = [f"{key.replace('_incl', '').replace('_self', ' self')} {value:.1f}"
                   for key, value in v8.items() if key != "top_v8_self" and value >= 0.05]
        out.append("V8: " + (", ".join(v8_bits) if v8_bits else "nothing above 0.05%"))
        top_v8 = v8.get("top_v8_self") or []
        if top_v8:
            out.append("")
            out.append("Top V8 self: " + ", ".join(f"`{item['symbol']}` {item['self_pct']:.1f}" for item in top_v8[:6]))
        plumbing = record["binding_plumbing_self"]
        out.append("")
        out.append(f"Plumbing self: blink->v8 {plumbing['blink_to_v8_self']:.1f}%, "
                   f"v8->blink {plumbing['v8_to_blink_self']:.1f}%")
        out.append("")
        out.append("Overhead: " + ", ".join(f"{key} {value:.1f}" for key, value in overhead.items()))
        out.append("")
        for entry in record.get("nested_view") or []:
            tag = entry.get("platform_sensitivity")
            tag_text = ""
            if isinstance(tag, dict):
                tag_text = f" [{tag.get('tag')}]"
            elif tag:
                tag_text = f" [{tag}]"
            out.append(f"### Underneath `{short_symbol(function_head(entry['entry']))}` "
                       f"({entry['kind']}, incl {entry['inclusive_pct']:.1f}%, self {entry['self_pct']:.1f}%, "
                       f"dominant phase {entry['dominant_phase']}){tag_text}")
            out.append("")
            mix = ", ".join(f"{phase} {value:.1f}" for phase, value in (entry.get("phase_mix") or {}).items())
            if mix:
                out.append(f"Phase mix: {mix}")
                out.append("")
            rows = []
            for descendant in entry.get("descendants") or []:
                marker = "*" if descendant.get("promoted") else ""
                chain = int(round(descendant.get("chain_frames") or 0))
                chain_text = f" (+{chain} chain)" if chain >= 1 else ""
                rows.append([
                    f"{marker}`{descendant['symbol']}`{chain_text}", descendant["inclusive_pct"],
                    descendant["self_pct"], descendant["phase"], descendant.get("platform_sensitivity") or "",
                ])
            out.extend(_table(["descendant", "incl", "self", "phase", "sensitivity"], rows))
            out.append("")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# Driver.
# --------------------------------------------------------------------------

def build_report(capture_dirs: list[str], top: int, floor_pct: float, jobs: int | None = None,
                 stories_filter: list[str] | None = None) -> dict:
    captures = []
    tasks = []
    seen_ids = set()
    for text in capture_dirs:
        root, stories_dir = resolve_capture(text)
        capture_id = root.name
        if capture_id in seen_ids:
            raise ValueError(f"duplicate capture id {capture_id!r}; capture roots must have distinct basenames")
        seen_ids.add(capture_id)
        index, index_digest = load_stories_index(stories_dir)
        captures.append({
            "capture_id": capture_id,
            "root": str(root),
            "stories_dir": str(stories_dir),
            "stories_index_sha256": index_digest,
        })
        tasks.extend(
            task for task in story_tasks(capture_id, root, stories_dir, index)
            if not stories_filter or task["story"] in stories_filter)
    if not tasks:
        raise ValueError("no stories with profile.collapsed found")

    worker_args = [(task, top, floor_pct) for task in tasks]
    if jobs is None:
        jobs = min(len(tasks), os.cpu_count() or 1)
    if jobs > 1 and len(tasks) > 1:
        context = multiprocessing.get_context("fork" if sys.platform != "win32" else "spawn")
        with context.Pool(jobs) as pool:
            results = pool.map(_worker, worker_args, chunksize=1)
    else:
        results = [_worker(args) for args in worker_args]

    stories: dict[str, dict] = {}
    digests: dict[str, str] = {}
    for result in results:
        stories.setdefault(result["story"], {"per_capture": {}})["per_capture"][result["capture_id"]] = result["record"]
        digests.update(result["digests"])
    for story in stories.values():
        story["mean"] = build_story_mean(story["per_capture"], top, floor_pct)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "parameters": {"top": top, "floor_pct": floor_pct},
        "captures": captures,
        "stories": dict(sorted(stories.items())),
        "input_digests": dict(sorted(digests.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capture-dir", action="append", required=True,
                        help="capture root (containing analysis/) or its analysis/stories directory; repeatable")
    parser.add_argument("--out", required=True, help="lens.json output path")
    parser.add_argument("--markdown", help="optional lens.md output path")
    parser.add_argument("--top", type=int, default=12, help="rows per top-N list (default 12)")
    parser.add_argument("--floor-pct", type=float, default=1.0,
                        help="minimum inclusive share for a nested descendant to be promoted (default 1.0)")
    parser.add_argument("--jobs", type=int, default=None, help="worker processes (default: cpu count)")
    parser.add_argument("--story", action="append", help="only analyse these stories (repeatable)")
    args = parser.parse_args(argv)

    started = time.monotonic()
    report = build_report(args.capture_dir, args.top, args.floor_pct, args.jobs, args.story)
    report["elapsed_s"] = round(time.monotonic() - started, 3)
    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    if args.markdown:
        md_path = pathlib.Path(args.markdown)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(report))
    print(f"story_lens: {len(report['stories'])} stories x {len(report['captures'])} captures "
          f"in {report['elapsed_s']:.1f}s -> {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
