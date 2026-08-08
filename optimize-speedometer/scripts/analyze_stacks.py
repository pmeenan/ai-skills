#!/usr/bin/env python3
"""Build an overlap-aware candidate frontier from Linux perf-script stacks.

The output is intended for optimization discovery, not just visualization.  It
aggregates both context-sensitive stacks and context-merged functions/classes,
then greedily chooses operation candidates by marginal sample coverage so
nested hot frames are not reported as independent opportunities. Broad class
areas remain a separate discovery lens and never suppress concrete operations.
"""

from __future__ import annotations

import argparse
import bisect
import collections
import dataclasses
import hashlib
import json
import pathlib
import re
import statistics
import subprocess
import sys
from typing import Iterable


HEADER_RE = re.compile(
    r"^\s*(?P<comm>.*?)\s+(?P<pid>\d+)(?:/(?P<tid>\d+))?\s+"
    r"(?P<time>\d+\.\d+):\s+(?P<period>\d+)\s+(?P<event>\S+):\s*$"
)
FRAME_RE = re.compile(r"^\s+(?P<ip>[0-9a-fA-F]+)\s+(?P<body>.*)$")
OFFSET_RE = re.compile(r"\+0x[0-9a-fA-F]+$")
CLONE_RE = re.compile(r"\s+\[clone [^]]+\](?:\s+\[clone [^]]+\])*$")

DEFAULT_INCLUDE = re.compile(
    r"^(?:blink|WTF|base|content|cc|gfx|ui|mojo|partition_alloc|"
    r"autofill|network|net|viz|views|chrome|gpu|media|components|device|"
    r"services|skia)::"
)
DEFAULT_EXCLUDE = re.compile(
    r"^(?:v8|angle|std|__gnu_cxx)::|"
    r"^(?:base::RunLoop|base::MessagePump|"
    r"base::sequence_manager::internal::ThreadControllerWithMessagePump|"
    r"base::Thread::(?:ThreadMain|Run)|"
    r"base::RepeatingCallback<.*>::Run|"
    r"base::\(anonymous namespace\)(?:::(?:ThreadFunc|WorkSourceDispatch).*)?$|"
    r"base::internal::(?:WorkerThread|TaskTracker)(?:::.*)?$|"
    r"base::internal::PostTaskAndReplyRelay::RunTaskAndPostReply)|"
    r"^(?:ChromeMain|content::ContentMainRunnerImpl|content::ContentMain\(|"
    r"content::RendererMain|content::BrowserMain|"
    r"content::BrowserProcessIOThread::IOThreadRun|"
    r"content::\(anonymous namespace\)::ChildIOThread::Run|"
    r"content::RunOtherNamedProcessTypeMain|content::RunBrowserProcessMain)|"
    r"^cc::ProxyMain$|^cc::ProxyMain::BeginMainFrame|"
    r"^cc::CategorizedWorkerPoolJob::Run|"
    r"^(?:blink::WidgetBase|blink::WebFrameWidgetImpl)(?:::BeginMainFrame)?(?:\(|$)|"
    r"^blink::scheduler::NonMainThreadImpl::SimpleThreadImpl::Run|"
    r"^blink::(?:V8ScriptRunner::CallFunction|"
    r"\(anonymous namespace\)::v8_.*(?:Operation|Attribute).*Callback|"
    r"bindings::CallbackInvokeHelper<|"
    r"FrameRequestCallbackCollection::ExecuteFrameCallbacks|"
    r"Page::Animate|PageAnimator::ServiceScriptedAnimations|"
    r"TimerBase::RunInternal|DOMTimer::Fired|ScheduledAction::Execute|"
    r"V8[^:]*::Invoke(?:WithoutRunnabilityCheck)?|"
    r"JSBasedEventListener::Invoke|"
    r"JSEventHandler::Invoke|"
    r"EventTarget::(?:FireEventListeners|DispatchEventInternal|"
    r"dispatchEventForBindings|DispatchEvent)|"
    r"EventDispatcher::(?:Dispatch\(\)|DispatchEvent\(|"
    r"DispatchSimulatedClick)|"
    r"Node::DispatchSimulatedClick|"
    r"scheduler::EventLoop::(?:RunPendingMicrotasks?|PerformMicrotaskCheckpoint))|"
    r"^base::WaitableEvent(?:::|$)|"
    r"(?:Invoker<|TaskAnnotator::RunTask)"
)
OUT_OF_SCOPE_OWNER = re.compile(
    r"^(?:v8|angle|skgpu)::|^(?:Sk[A-Z_]|Gr[A-Z_])|"
    r"^(?:JS:|JIT:|LazyCompile:|Function:|Builtin:|Stub:|"
    r"Builtins_|RegExp:|BytecodeHandler:|LoadIC:|StoreIC:)"
)
TREE_TRUNK_NOISE = re.compile(
    r"^(?:ChromeMain|content::ContentMain|content::RendererMain|"
    r"content::BrowserMain|content::RunOtherNamedProcessTypeMain|"
    r"content::RunBrowserProcessMain|base::RunLoop|base::MessagePump|"
    r"base::Thread::(?:ThreadMain|Run)|"
    r"base::sequence_manager::internal::ThreadControllerWithMessagePump|"
    r"base::\(anonymous namespace\)::ThreadFunc|"
    r"base::TaskAnnotator::RunTask)|(?:Invoker<|TaskAnnotator::RunTask)"
)
V8_TREE_AREA = re.compile(
    r"^(?:v8::|JS:|JIT:|LazyCompile:|Function:|Builtin:|Stub:|Builtins_|"
    r"RegExp:|BytecodeHandler:|LoadIC:|StoreIC:|Wasm)"
)
APPLICATION_SCRIPT_FRAME = re.compile(r"^(?:JS:|JIT:|LazyCompile:|Function:|RegExp:)")
ANGLE_TREE_AREA = re.compile(r"^(?:angle|rx|egl|gl|sh)::")
SKIA_TREE_AREA = re.compile(r"^(?:Sk[A-Z_]|skgpu::|Gr[A-Z_])")
CHROMIUM_TREE_AREA = re.compile(
    r"^(?:base|content|cc|gfx|ui|mojo|partition_alloc|autofill|network|net|"
    r"viz|views|chrome|gpu|media|components|device|services|skia)::"
)


@dataclasses.dataclass(frozen=True, slots=True)
class Frame:
    kernel: bool
    symbol: str
    dso: str


@dataclasses.dataclass(slots=True)
class Sample:
    group: str
    comm: str
    pid: int
    tid: int
    timestamp: float
    weight: int
    frames: tuple[Frame, ...]  # root to leaf


@dataclasses.dataclass(slots=True)
class Aggregate:
    kind: str
    name: str
    path: tuple[str, ...] = ()
    sample_mask: int = 0
    owner_exclusive_mask: int = 0
    self_mask: int = 0
    callers: collections.Counter[str] = dataclasses.field(
        default_factory=collections.Counter
    )
    callees: collections.Counter[str] = dataclasses.field(
        default_factory=collections.Counter
    )
    groups: collections.Counter[str] = dataclasses.field(
        default_factory=collections.Counter
    )
    depth_sum: int = 0
    occurrences: int = 0


@dataclasses.dataclass(slots=True)
class TreeNode:
    name: str
    area: str | None
    weight: int = 0
    self_weight: int = 0
    children: dict[tuple[str, str | None], "TreeNode"] = dataclasses.field(
        default_factory=dict
    )


def normalize_symbol(raw: str) -> tuple[str, str]:
    body = raw.rstrip()
    dso = ""
    if body.endswith(")") and " (" in body:
        symbol_part, possible_dso = body.rsplit(" (", 1)
        dso = possible_dso[:-1]
        body = symbol_part
    body = OFFSET_RE.sub("", body)
    body = CLONE_RE.sub("", body)
    return body.strip(), dso


def parse_perf_script(
    lines: Iterable[str],
    group: str,
    intervals: list[tuple[float, float]] | None = None,
    pids: set[int] | None = None,
) -> list[Sample]:
    samples: list[Sample] = []
    header: re.Match[str] | None = None
    leaf_to_root: list[Frame] = []
    in_scope = make_interval_checker(intervals or [])

    def finish() -> None:
        nonlocal header, leaf_to_root
        if header and leaf_to_root:
            pid = int(header.group("pid"))
            timestamp = float(header.group("time"))
            if (pids is None or pid in pids) and in_scope(timestamp):
                samples.append(
                    Sample(
                        group=group,
                        comm=sys.intern(header.group("comm").strip()),
                        pid=pid,
                        tid=int(header.group("tid") or pid),
                        timestamp=timestamp,
                        weight=int(header.group("period")),
                        frames=tuple(reversed(leaf_to_root)),
                    )
                )
        header = None
        leaf_to_root = []

    for line in lines:
        match = HEADER_RE.match(line)
        if match:
            finish()
            header = match
            continue
        if not line.strip():
            finish()
            continue
        if header:
            match = FRAME_RE.match(line)
            if match:
                symbol, dso = normalize_symbol(match.group("body"))
                if symbol:
                    ip = match.group("ip")
                    leaf_to_root.append(
                        Frame(
                            ip.lower().startswith("ffff"),
                            sys.intern(symbol),
                            sys.intern(dso),
                        )
                    )
    finish()
    return samples


def load_intervals(path: pathlib.Path | None) -> list[tuple[float, float]]:
    if path is None:
        return []
    data = json.loads(path.read_text())
    if isinstance(data, dict) and "measurement_intervals" in data:
        raw = data["measurement_intervals"]
    elif isinstance(data, dict) and data.get("start_time_mono") is not None:
        raw = [data]
    else:
        raw = data
    intervals = []
    for item in raw:
        if isinstance(item, dict):
            start = item.get("start_time_mono", item.get("start"))
            end = item.get("end_time_mono", item.get("end"))
        else:
            start, end = item
        if start is not None and end is not None and float(end) > float(start):
            intervals.append((float(start), float(end)))
    return sorted(intervals)


def in_intervals(timestamp: float, intervals: list[tuple[float, float]]) -> bool:
    return not intervals or any(start <= timestamp <= end for start, end in intervals)


def make_interval_checker(intervals: list[tuple[float, float]]):
    """O(log K) membership test over the union of intervals.

    Full-suite captures pair millions of samples with hundreds of scored
    intervals, so the naive per-sample linear scan is a real cost. Intervals
    are sorted and merged (overlaps collapse) so a single bisect on the start
    list decides membership; inclusive-bound semantics match in_intervals().
    """
    if not intervals:
        return lambda timestamp: True
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    starts = [start for start, _ in merged]
    ends = [end for _, end in merged]

    def contains(timestamp: float) -> bool:
        index = bisect.bisect_right(starts, timestamp) - 1
        return index >= 0 and timestamp <= ends[index]

    return contains


def load_mark_intervals(paths: list[pathlib.Path]) -> list[tuple[float, float]]:
    intervals = []
    for path in paths:
        pending_start = None
        for line in path.read_text(errors="replace").splitlines():
            if "[SP3_MONO_TIME]" not in line:
                continue
            start = re.search(r"sp3-measurement-start:\s*([\d.]+)", line)
            end = re.search(r"sp3-measurement-end:\s*([\d.]+)", line)
            if start:
                if pending_start is not None:
                    raise ValueError(f"Unmatched measurement start in {path}")
                pending_start = float(start.group(1))
            elif end:
                if pending_start is None:
                    raise ValueError(f"Unmatched measurement end in {path}")
                end_time = float(end.group(1))
                if end_time <= pending_start:
                    raise ValueError(f"Invalid measurement interval in {path}")
                intervals.append((pending_start, end_time))
                pending_start = None
        if pending_start is not None:
            raise ValueError(f"Unmatched measurement start in {path}")
    return sorted(intervals)


def function_head(symbol: str) -> str:
    protected = symbol.replace("(anonymous namespace)", "{anonymous namespace}")
    angle_depth = 0
    for index, char in enumerate(protected):
        if char == "<":
            angle_depth += 1
        elif char == ">" and angle_depth:
            angle_depth -= 1
        elif char == "(" and angle_depth == 0:
            protected = protected[:index]
            break
    return protected.replace("{anonymous namespace}", "(anonymous namespace)").strip()


def split_qualified(head: str) -> list[str]:
    parts = []
    start = 0
    angle_depth = 0
    index = 0
    while index < len(head) - 1:
        if head[index] == "<":
            angle_depth += 1
        elif head[index] == ">" and angle_depth:
            angle_depth -= 1
        elif head[index : index + 2] == "::" and angle_depth == 0:
            parts.append(head[start:index])
            start = index + 2
            index += 1
        index += 1
    parts.append(head[start:])
    return parts


def collapse_templates(value: str) -> str:
    output = []
    depth = 0
    for char in value:
        if char == "<":
            if depth == 0:
                output.append("<…>")
            depth += 1
        elif char == ">" and depth:
            depth -= 1
        elif depth == 0:
            output.append(char)
    return "".join(output)


def tree_area(frame: Frame) -> str | None:
    symbol = frame.symbol
    if symbol.startswith(("blink::", "WTF::")):
        return "blink"
    if V8_TREE_AREA.search(symbol):
        return "v8-js"
    if ANGLE_TREE_AREA.search(symbol) or re.search(
        r"(?:libGLESv2|libEGL|angle)", frame.dso, re.IGNORECASE
    ):
        return "angle"
    if SKIA_TREE_AREA.search(symbol):
        return "skia"
    if CHROMIUM_TREE_AREA.search(symbol):
        return "chromium"
    return None


def tree_symbol(symbol: str, max_length: int = 140) -> str:
    if APPLICATION_SCRIPT_FRAME.search(symbol):
        return "[application script execution]"
    shortened = collapse_templates(function_head(symbol)) or symbol
    shortened = re.sub(r"\s+", " ", shortened).strip()
    if len(shortened) > max_length:
        shortened = shortened[: max_length - 3].rstrip() + "..."
    return shortened


def tree_frame_is_noise(frame: Frame) -> bool:
    symbol = frame.symbol
    if frame.kernel or symbol == "[unknown]" or symbol.startswith("0x"):
        return True
    head = tree_symbol(symbol)
    method = split_qualified(head)[-1]
    return bool(
        TREE_TRUNK_NOISE.search(symbol)
        or method.startswith("~")
        or method in {"operator", "operator bool", "reset", "empty", "data"}
    )


def projected_tree_frames(sample: Sample, area: str | None) -> list[tuple[str, str]]:
    start_index = 0
    if area is not None:
        recognized = [tree_area(frame) for frame in sample.frames]
        owner_index = next(
            (
                index
                for index in range(len(recognized) - 1, -1, -1)
                if recognized[index]
            ),
            None,
        )
        if owner_index is None or recognized[owner_index] != area:
            return []
        for index in range(owner_index - 1, -1, -1):
            if recognized[index] is not None and recognized[index] != area:
                start_index = index + 1
                break
    projected = []
    for frame in sample.frames[start_index:]:
        frame_area = tree_area(frame)
        if frame_area is None or (area is not None and frame_area != area):
            continue
        if tree_frame_is_noise(frame):
            continue
        item = (tree_symbol(frame.symbol), frame_area)
        if not projected or projected[-1] != item:
            projected.append(item)
    return projected


def build_text_tree(samples: list[Sample], area: str | None = None) -> TreeNode:
    root = TreeNode("[root]", area)
    for sample in samples:
        frames = projected_tree_frames(sample, area)
        if not frames:
            continue
        root.weight += sample.weight
        node = root
        for name, frame_area in frames:
            key = (name, frame_area)
            node = node.children.setdefault(key, TreeNode(name, frame_area))
            node.weight += sample.weight
        node.self_weight += sample.weight
    return root


def material_children(
    node: TreeNode, min_weight: int, max_children: int
) -> tuple[list[TreeNode], int]:
    eligible = sorted(
        (child for child in node.children.values() if child.weight >= min_weight),
        key=lambda child: child.weight,
        reverse=True,
    )
    shown = eligible[:max_children]
    hidden_weight = sum(child.weight for child in eligible[max_children:])
    hidden_weight += sum(
        child.weight for child in node.children.values() if child.weight < min_weight
    )
    return shown, hidden_weight


def render_text_tree(
    root: TreeNode,
    total_weight: int,
    min_share: float,
    max_depth: int,
    max_children: int,
    frontier_names: set[str],
    show_area: bool,
) -> list[str]:
    min_weight = max(1, int(total_weight * min_share))
    lines = []

    def render(node: TreeNode, depth: int, prefix: str, is_last: bool) -> None:
        marker = "[*] " if node.name in frontier_names else ""
        area_tag = f"[{node.area}] " if show_area and node.area else ""
        connector = "└── " if is_last else "├── "
        lines.append(
            f"{prefix}{connector}{marker}{area_tag}{node.name} "
            f"({node.weight / total_weight:.2%})"
        )
        children, hidden_weight = material_children(node, min_weight, max_children)
        if depth >= max_depth:
            return

        if len(children) == 1:
            child = children[0]
            while True:
                grandchildren, grand_hidden = material_children(
                    child, min_weight, max_children
                )
                keep_child = (
                    child.name in frontier_names
                    or child.area != node.area
                    or child.weight < node.weight * 0.90
                    or len(grandchildren) != 1
                    or grand_hidden >= min_weight
                )
                if keep_child:
                    break
                child = grandchildren[0]
            children = [child]

        child_prefix = prefix + ("    " if is_last else "│   ")
        for index, child in enumerate(children):
            render(
                child,
                depth + 1,
                child_prefix,
                is_last=index == len(children) - 1,
            )

    top_children, _ = material_children(root, min_weight, max_children)
    for index, child in enumerate(top_children):
        render(child, 0, "", is_last=index == len(top_children) - 1)
    return lines


def write_text_trees(
    samples: list[Sample],
    frontier: list[dict],
    path: pathlib.Path,
    min_share: float,
    max_depth: int,
    max_children: int,
) -> None:
    total_weight = sum(sample.weight for sample in samples)
    frontier_names = {tree_symbol(candidate["name"]) for candidate in frontier}
    lines = [
        "SIMPLIFIED TEXT FLAME TREES",
        "",
        f"Global denominator: {total_weight:,} weighted cycles.",
        f"Display floor: {min_share:.2%} of the global profile; maximum visible "
        f"depth: {max_depth}; maximum children per node: {max_children}.",
        "[*] marks an operation selected by the autonomous coverage frontier.",
        "Linear same-area trunks are collapsed. Intermediate, depth-limited, and "
        "pruned work is omitted without placeholder rows.",
        "The cross-area tree is raw inclusive stack coverage and may include work "
        "owned by a deeper repository. Repository trees assign each sample to its "
        "innermost recognized owner segment, so outer Blink or Chromium wrappers do "
        "not inherit nested V8/JavaScript, ANGLE, or Skia work.",
        "Application-owned JavaScript and JIT frames are canonicalized as "
        "[application script execution]; V8 plumbing remains expanded.",
        "",
        "== CROSS-AREA OPPORTUNITY TREE ==",
        "",
    ]
    overall = build_text_tree(samples)
    lines.extend(
        render_text_tree(
            overall,
            total_weight,
            min_share,
            max_depth,
            max_children,
            frontier_names,
            show_area=True,
        )
        or ["[no material recognized frames]"]
    )
    area_titles = (
        ("blink", "BLINK"),
        ("chromium", "CHROMIUM (NON-BLINK)"),
        ("v8-js", "V8 / JAVASCRIPT"),
        ("angle", "ANGLE"),
        ("skia", "SKIA"),
    )
    omitted_areas = []
    for area, title in area_titles:
        root = build_text_tree(samples, area)
        if root.weight < total_weight * min_share:
            omitted_areas.append((title, root.weight / total_weight))
            continue
        lines.extend(
            [
                "",
                f"== {title} OWNED TREE ({root.weight / total_weight:.2%} "
                "exclusive coverage) ==",
                "",
            ]
        )
        lines.extend(
            render_text_tree(
                root,
                total_weight,
                min_share,
                max_depth,
                max_children,
                frontier_names,
                show_area=False,
            )
        )
    if omitted_areas:
        lines.extend(["", "== AREAS BELOW DISPLAY FLOOR ==", ""])
        lines.extend(f"- {title}: {share:.3%}" for title, share in omitted_areas)
    path.write_text("\n".join(lines) + "\n")


def class_area(symbol: str) -> str | None:
    parts = split_qualified(function_head(symbol))
    if len(parts) < 3:
        return None
    return collapse_templates("::".join(parts[:-1]))


def add_weighted(counter: collections.Counter[str], key: str, weight: int) -> None:
    if key:
        counter[key] += weight


def addressable_start(
    sample: Sample, include: re.Pattern[str] = DEFAULT_INCLUDE
) -> int | None:
    owner_is_chromium = False
    last_engine_boundary = -1
    for index, frame in enumerate(sample.frames):
        if frame.kernel:
            continue
        if OUT_OF_SCOPE_OWNER.search(frame.symbol):
            owner_is_chromium = False
            last_engine_boundary = index
        elif include.search(frame.symbol):
            owner_is_chromium = True
    return last_engine_boundary + 1 if owner_is_chromium else None


def sample_is_addressable(
    sample: Sample, include: re.Pattern[str] = DEFAULT_INCLUDE
) -> bool:
    return addressable_start(sample, include) is not None


def sample_has_chromium_opportunity(
    sample: Sample, include: re.Pattern[str] = DEFAULT_INCLUDE
) -> bool:
    return any(
        not frame.kernel and include.search(frame.symbol) for frame in sample.frames
    )


def aggregate_samples(
    samples: list[Sample], include: re.Pattern[str] = DEFAULT_INCLUDE
) -> dict[tuple[str, object], Aggregate]:
    aggregates: dict[tuple[str, object], Aggregate] = {}
    context_ids: dict[tuple[int, str], int] = {}
    next_context_id = 1

    def get(
        kind: str,
        name: str,
        identity: object | None = None,
        path: tuple[str, ...] = (),
    ) -> Aggregate:
        return aggregates.setdefault(
            (kind, identity or name), Aggregate(kind, name, path=path)
        )

    for sample_id, sample in enumerate(samples):
        start_depth = addressable_start(sample, include)
        seen_functions: set[str] = set()
        seen_areas: set[str] = set()
        parent_context_id = 0
        context_path: tuple[str, ...] = ()
        for depth in range(len(sample.frames)):
            frame = sample.frames[depth]
            symbol = frame.symbol
            caller = sample.frames[depth - 1].symbol if depth else "[root]"
            callee = (
                sample.frames[depth + 1].symbol
                if depth + 1 < len(sample.frames)
                else "[leaf]"
            )
            context_identity = (parent_context_id, symbol)
            context_id = context_ids.get(context_identity)
            if context_id is None:
                context_id = next_context_id
                next_context_id += 1
                context_ids[context_identity] = context_id
            context_path = context_path + (symbol,)
            if include.search(symbol):
                context = get("context", symbol, context_id, path=context_path)
                context.sample_mask |= 1 << sample_id
                if start_depth is not None and depth >= start_depth:
                    context.owner_exclusive_mask |= 1 << sample_id
                context.depth_sum += depth
                context.occurrences += 1
                add_weighted(context.callers, caller, sample.weight)
                add_weighted(context.callees, callee, sample.weight)
                add_weighted(context.groups, sample.group, sample.weight)
            parent_context_id = context_id
            if include.search(symbol) and symbol not in seen_functions:
                agg = get("function", symbol)
                agg.sample_mask |= 1 << sample_id
                agg.depth_sum += depth
                agg.occurrences += 1
                add_weighted(agg.callers, caller, sample.weight)
                add_weighted(agg.callees, callee, sample.weight)
                add_weighted(agg.groups, sample.group, sample.weight)
                seen_functions.add(symbol)
            if (
                start_depth is not None
                and depth >= start_depth
                and include.search(symbol)
            ):
                get("function", symbol).owner_exclusive_mask |= 1 << sample_id
            area = class_area(symbol) if include.search(symbol) else None
            if area and area not in seen_areas:
                agg = get("class", area)
                agg.sample_mask |= 1 << sample_id
                agg.depth_sum += depth
                agg.occurrences += 1
                add_weighted(agg.callers, caller, sample.weight)
                add_weighted(agg.callees, callee, sample.weight)
                add_weighted(agg.groups, sample.group, sample.weight)
                seen_areas.add(area)
            if area and start_depth is not None and depth >= start_depth:
                get("class", area).owner_exclusive_mask |= 1 << sample_id
        if sample.frames and include.search(sample.frames[-1].symbol):
            get("function", sample.frames[-1].symbol).self_mask |= 1 << sample_id
            get(
                "context",
                sample.frames[-1].symbol,
                parent_context_id,
                path=context_path,
            ).self_mask |= (
                1 << sample_id
            )
    return aggregates


def weight_of(sample_mask: int, samples: list[Sample]) -> int:
    weight = 0
    while sample_mask:
        lowest_bit = sample_mask & -sample_mask
        weight += samples[lowest_bit.bit_length() - 1].weight
        sample_mask ^= lowest_bit
    return weight


def top_counter(counter: collections.Counter[str], limit: int = 5) -> list[dict]:
    total = sum(counter.values()) or 1
    return [
        {"name": name, "weight": weight, "share": weight / total}
        for name, weight in counter.most_common(limit)
    ]


def aggregate_entry_key(agg: Aggregate) -> str:
    """Return a stable machine identity, preserving caller-sensitive contexts."""
    if agg.kind != "context":
        return f"{agg.kind}:{agg.name}"
    context_digest = hashlib.sha256("\0".join(agg.path).encode()).hexdigest()[:16]
    return f"context:{agg.name}@{context_digest}"


def make_candidate(
    agg: Aggregate,
    samples: list[Sample],
    total_weight: int,
    group_totals: collections.Counter[str],
    uncovered: int,
) -> dict:
    inclusive = weight_of(agg.sample_mask, samples)
    owner_exclusive = weight_of(agg.owner_exclusive_mask, samples)
    self_weight = weight_of(agg.self_mask, samples)
    marginal_mask = agg.sample_mask & uncovered
    marginal = weight_of(marginal_mask, samples)
    max_caller = max(agg.callers.values(), default=inclusive)
    caller_diversity = 1.0 - (max_caller / inclusive if inclusive else 1.0)
    group_shares = [
        agg.groups.get(group, 0) / weight
        for group, weight in group_totals.items()
        if weight
    ]
    group_breadth = (
        sum(share > 0 for share in group_shares) / len(group_shares)
        if group_shares
        else 0
    )
    if len(group_shares) > 1 and statistics.fmean(group_shares):
        group_stability = max(
            0.0,
            1.0 - statistics.pstdev(group_shares) / statistics.fmean(group_shares),
        )
    else:
        group_stability = 0.0
    self_fraction = self_weight / inclusive if inclusive else 0.0
    tree_fraction = 1.0 - self_fraction
    average_depth = agg.depth_sum / agg.occurrences if agg.occurrences else 0.0
    score = (inclusive / total_weight) * (
        1.0
        + 0.35 * caller_diversity
        + 0.15 * group_breadth * group_stability
        + 0.05 * tree_fraction
        - 0.005 * min(average_depth, 10)
    )
    return {
        "entry_key": aggregate_entry_key(agg),
        "kind": agg.kind,
        "name": agg.name,
        "score": score,
        "inclusive_weight": inclusive,
        "inclusive_share": inclusive / total_weight,
        "owner_exclusive_weight": owner_exclusive,
        "owner_exclusive_share": owner_exclusive / total_weight,
        "owner_exclusive_fraction": owner_exclusive / inclusive if inclusive else 0.0,
        "self_weight": self_weight,
        "self_share_of_candidate": self_fraction,
        "tree_share_of_candidate": tree_fraction,
        "marginal_weight": marginal,
        "marginal_share": marginal / total_weight,
        "caller_contexts": len(agg.callers),
        "caller_diversity": caller_diversity,
        "group_breadth": group_breadth,
        "group_stability": group_stability,
        "groups": sorted(
            [
                {
                    "name": group,
                    "weight": agg.groups.get(group, 0),
                    "profile_share": agg.groups.get(group, 0) / weight,
                }
                for group, weight in group_totals.items()
            ],
            key=lambda item: item["profile_share"],
            reverse=True,
        ),
        "average_depth": average_depth,
        "path_tail": list(agg.path[-8:]),
        "top_callers": top_counter(agg.callers),
        "top_callees": top_counter(agg.callees),
        "sample_mask": agg.sample_mask,
    }


def add_related_hotspots(
    frontier: list[dict],
    eligible: list[tuple[float, Aggregate]],
    samples: list[Sample],
    total_weight: int,
    representative_limit: int = 16,
) -> None:
    """Attach nested/cross-context functions to each selected operation.

    Direct callees often just expose one link in a deep recursive chain. The
    overlap calculation below instead finds functions anywhere in the selected
    region, while requiring most of each related function's samples to actually
    belong to that region. This makes expensive descendants auditable without
    pretending that their inclusive costs add to the parent opportunity.
    """
    function_aggregates = [agg for _, agg in eligible if agg.kind == "function"]
    for candidate in frontier:
        related = []
        candidate_mask = candidate["sample_mask"]
        candidate_weight = candidate["inclusive_weight"] or 1
        for agg in function_aggregates:
            if agg.name == candidate["name"]:
                continue
            overlap_mask = candidate_mask & agg.sample_mask
            if not overlap_mask:
                continue
            overlap_weight = weight_of(overlap_mask, samples)
            hotspot_weight = weight_of(agg.sample_mask, samples)
            contained_fraction = overlap_weight / hotspot_weight
            if contained_fraction < 0.5:
                continue
            candidate_fraction = overlap_weight / candidate_weight
            related.append(
                {
                    "name": agg.name,
                    "overlap_weight": overlap_weight,
                    "overlap_share": overlap_weight / total_weight,
                    "candidate_fraction": candidate_fraction,
                    "contained_fraction": contained_fraction,
                    "inclusive_share": hotspot_weight / total_weight,
                    "caller_contexts": len(agg.callers),
                    "_overlap_mask": overlap_mask,
                }
            )
        related.sort(
            key=lambda item: (
                item["overlap_weight"],
                item["contained_fraction"],
                item["caller_contexts"],
            ),
            reverse=True,
        )
        representatives = []
        for item in related:
            item_mask = item["_overlap_mask"]
            duplicates_existing_branch = False
            for existing in representatives:
                existing_mask = existing["_overlap_mask"]
                intersection = weight_of(item_mask & existing_mask, samples)
                union = weight_of(item_mask | existing_mask, samples)
                if union and intersection / union >= 0.8:
                    duplicates_existing_branch = True
                    break
            if not duplicates_existing_branch:
                representatives.append(item)
                if len(representatives) >= representative_limit:
                    break
        candidate["branch_hotspots"] = [
            {key: value for key, value in item.items() if key != "_overlap_mask"}
            for item in representatives
        ]
        candidate["related_hotspots"] = [
            {key: value for key, value in item.items() if key != "_overlap_mask"}
            for item in related
        ]


def build_frontier(
    samples: list[Sample],
    aggregates: dict[tuple[str, str], Aggregate],
    min_share: float,
    min_marginal_share: float,
    limit: int,
    include: re.Pattern[str],
    exclude: re.Pattern[str],
) -> tuple[list[dict], list[dict], list[dict]]:
    total_weight = sum(sample.weight for sample in samples)
    addressable_mask = 0
    for index, sample in enumerate(samples):
        if sample_has_chromium_opportunity(sample, include):
            addressable_mask |= 1 << index
    group_totals = collections.Counter()
    for sample in samples:
        group_totals[sample.group] += sample.weight
    eligible = []
    area_eligible = []
    all_ids = addressable_mask
    for agg in aggregates.values():
        if not include.search(agg.name) or exclude.search(agg.name):
            continue
        candidate = make_candidate(agg, samples, total_weight, group_totals, all_ids)
        if candidate["inclusive_share"] >= min_share:
            destination = area_eligible if agg.kind == "class" else eligible
            destination.append((candidate["score"], agg))
    eligible.sort(key=lambda item: item[0], reverse=True)
    area_eligible.sort(key=lambda item: item[0], reverse=True)

    frontier: list[dict] = []
    selected_aggregate_ids: set[int] = set()
    uncovered = addressable_mask
    remaining = list(eligible)
    # `limit` is presentation-only. The machine-readable frontier must continue
    # until the marginal floor so lower-ranked disjoint work cannot remain
    # permanently hidden behind recurrent hot parents.
    while remaining:
        rescored = []
        for _, agg in remaining:
            candidate = make_candidate(
                agg, samples, total_weight, group_totals, uncovered
            )
            marginal_score = candidate["score"] * (
                candidate["marginal_weight"] / candidate["inclusive_weight"]
                if candidate["inclusive_weight"]
                else 0
            )
            rescored.append((marginal_score, candidate, agg))
        _, candidate, selected_agg = max(rescored, key=lambda item: item[0])
        if candidate["marginal_share"] < min_marginal_share:
            break
        frontier.append(candidate)
        selected_aggregate_ids.add(id(selected_agg))
        uncovered &= ~selected_agg.sample_mask
        remaining = [item for item in remaining if item[1] is not selected_agg]

    add_related_hotspots(frontier, eligible, samples, total_weight)
    alternatives = []
    for _, agg in eligible:
        if id(agg) in selected_aggregate_ids:
            continue
        candidate = make_candidate(agg, samples, total_weight, group_totals, uncovered)
        overlaps = []
        for frontier_candidate in frontier:
            overlap_weight = weight_of(
                agg.sample_mask & frontier_candidate["sample_mask"], samples
            )
            if not overlap_weight:
                continue
            overlaps.append({
                "entry_key": frontier_candidate["entry_key"],
                "overlap_weight": overlap_weight,
                "overlap_share": overlap_weight / total_weight,
                "alternative_fraction": (
                    overlap_weight / candidate["inclusive_weight"]
                    if candidate["inclusive_weight"] else 0.0
                ),
            })
        overlaps.sort(
            key=lambda item: (item["overlap_weight"], item["entry_key"]),
            reverse=True,
        )
        candidate["frontier_overlaps"] = overlaps
        candidate["assigned_frontier_entry"] = (
            overlaps[0]["entry_key"] if overlaps else None
        )
        alternatives.append(candidate)
    alternatives.sort(key=lambda item: item["inclusive_weight"], reverse=True)

    for rank, candidate in enumerate(frontier, 1):
        candidate["rank"] = rank
    areas = [
        make_candidate(agg, samples, total_weight, group_totals, all_ids)
        for _, agg in area_eligible
    ]
    return frontier, alternatives, areas


def public_candidate(candidate: dict) -> dict:
    return {key: value for key, value in candidate.items() if key != "sample_mask"}


def write_collapsed(samples: list[Sample], path: pathlib.Path) -> None:
    with path.open("w") as output:
        for sample in samples:
            stack = ";".join(frame.symbol.replace(";", ":") for frame in sample.frames)
            output.write(f"{stack} {sample.weight}\n")


def write_markdown(report: dict, path: pathlib.Path, display_limit: int = 20) -> None:
    lines = [
        "# Stack candidate frontier",
        "",
        f"Samples: {report['quality']['samples']:,}; weighted cycles: "
        f"{report['quality']['total_weight']:,}; median stack depth: "
        f"{report['quality']['median_depth']:.1f}.",
        "",
    ]
    if not report["quality"]["accepted"]:
        lines.extend(
            [
                "**PROFILE REJECTED:** " + "; ".join(report["quality"]["issues"]) + ".",
                "",
                "Do not use the rankings below for implementation selection.",
                "",
            ]
        )
    lines.extend(
        [
            "Candidates are merged across caller contexts and selected by marginal "
            "sample coverage. Inclusive share retains all descendant work as an "
            "opportunity bound; Owned is the deepest-owner-exclusive subset. "
            "Neither predicts benchmark improvement.",
            "See `opportunity_trees.txt` for a pruned text flame tree of the same "
            "profile, including cross-area and exclusive repository-owned views.",
            "",
            "| Rank | Kind | Candidate | Inclusive | Owned | Tree | Marginal | Callers |",
            "|---:|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    displayed_frontier = report["frontier"][:display_limit]
    for candidate in displayed_frontier:
        lines.append(
            "| {rank} | {kind} | `{name}` | {inclusive_share:.2%} | "
            "{owner_exclusive_share:.2%} | {tree_share_of_candidate:.1%} | "
            "{marginal_share:.2%} | "
            "{caller_contexts} |".format(**candidate)
        )
    lines.extend(["", "## Investigation context", ""])
    for candidate in displayed_frontier:
        callers = ", ".join(
            f"`{item['name']}` ({item['share']:.0%})"
            for item in candidate["top_callers"][:3]
        )
        callees = ", ".join(
            f"`{item['name']}` ({item['share']:.0%})"
            for item in candidate["top_callees"][:5]
        )
        lines.extend([f"### {candidate['rank']}. `{candidate['name']}`", ""])
        if candidate["kind"] == "context":
            path_tail = " → ".join(f"`{item}`" for item in candidate["path_tail"])
            lines.extend([f"Context tail: {path_tail}.", ""])
        lines.extend(
            [
                f"Top callers: {callers or 'none'}.",
                "",
                f"Top callees: {callees or 'none'}.",
                "",
            ]
        )
        hotspots = candidate.get("branch_hotspots", [])[:12]
        if hotspots:
            lines.extend(["Nested/cross-context hotspots (overlap, not additive):", ""])
            for hotspot in hotspots:
                lines.append(
                    "- `{name}`: {overlap_share:.2%} of profile in this region; "
                    "{contained_fraction:.0%} of the hotspot is contained here.".format(
                        **hotspot
                    )
                )
            lines.append("")
    lines.extend(["## Cross-context class areas", ""])
    lines.append(
        "These are broad search lenses. They do not consume coverage or suppress "
        "operation candidates."
    )
    lines.append("")
    lines.extend(
        [
            "| Rank | Area | Inclusive | Callers |",
            "|---:|---|---:|---:|",
        ]
    )
    for rank, candidate in enumerate(report["area_inventory"][:20], 1):
        lines.append(
            f"| {rank} | `{candidate['name']}` | "
            f"{candidate['inclusive_share']:.2%} | {candidate['caller_contexts']} |"
        )
    path.write_text("\n".join(lines))


def read_input(
    spec: str,
    perf_binary: str,
    expand_inline: bool,
    intervals: list[tuple[float, float]],
    pids: set[int] | None,
) -> tuple[str, Iterable[str], subprocess.Popen[str] | None]:
    if "=" in spec:
        group, raw_path = spec.split("=", 1)
    else:
        raw_path = spec
        group = pathlib.Path(raw_path).stem
    path = pathlib.Path(raw_path)
    if path.suffix == ".data":
        command = [
            perf_binary,
            "script",
            "-i",
            str(path),
            "-F",
            "comm,pid,tid,time,period,event,ip,sym,dso",
        ]
        if intervals:
            command.extend(["--time", f"{intervals[0][0]:.9f},{intervals[-1][1]:.9f}"])
        if pids:
            command.extend(["--pid", ",".join(str(pid) for pid in sorted(pids))])
        command.append("--inline" if expand_inline else "--no-inline")
        process = subprocess.Popen(
            command,
            text=True,
            stdout=subprocess.PIPE,
        )
        assert process.stdout
        return group, process.stdout, process
    handle = path.open(errors="replace")
    return group, handle, None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an overlap-aware optimization frontier from perf stacks."
    )
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        metavar="[GROUP=]PATH",
        help="perf.data or perf-script text; repeat for story/repetition groups",
    )
    parser.add_argument("--intervals", type=pathlib.Path)
    parser.add_argument(
        "--browser-log",
        action="append",
        type=pathlib.Path,
        default=[],
        help="Extract measurement intervals from a probed browser.stdout.log",
    )
    parser.add_argument(
        "--role",
        help="Keep only PIDs with this role in the --intervals manifest (for example renderer)",
    )
    parser.add_argument("--out-dir", type=pathlib.Path, required=True)
    parser.add_argument("--perf-binary", default="perf")
    inline_group = parser.add_mutually_exclusive_group()
    inline_group.add_argument(
        "--expand-inline",
        dest="expand_inline",
        action="store_true",
        default=True,
        help="Expand inline frames (the authoritative default)",
    )
    inline_group.add_argument(
        "--no-inline",
        dest="expand_inline",
        action="store_false",
        help="Skip inline expansion for a faster, lower-fidelity screen",
    )
    parser.add_argument("--weight", choices=("period", "samples"), default="period")
    parser.add_argument("--min-share", type=float, default=0.001)
    parser.add_argument("--min-marginal-share", type=float, default=0.001)
    parser.add_argument(
        "--limit", type=int, default=20,
        help="Markdown presentation limit; JSON selection always runs to the marginal floor",
    )
    parser.add_argument(
        "--tree-min-share",
        type=float,
        default=0.005,
        help="Global profile-share floor for simplified text flame trees",
    )
    parser.add_argument(
        "--tree-max-depth",
        type=int,
        default=10,
        help="Maximum visible depth in simplified text flame trees",
    )
    parser.add_argument(
        "--tree-max-children",
        type=int,
        default=8,
        help="Maximum children displayed per text-tree node",
    )
    parser.add_argument("--include-regex", default=DEFAULT_INCLUDE.pattern)
    parser.add_argument("--exclude-regex", default=DEFAULT_EXCLUDE.pattern)
    parser.add_argument(
        "--allow-low-quality",
        action="store_true",
        help="Write diagnostic output and exit successfully even if quality gates fail",
    )
    args = parser.parse_args()
    if not 0 < args.tree_min_share < 1:
        parser.error("--tree-min-share must be between 0 and 1")
    if args.tree_max_depth < 1:
        parser.error("--tree-max-depth must be at least 1")
    if args.tree_max_children < 1:
        parser.error("--tree-max-children must be at least 1")

    intervals = load_intervals(args.intervals) + load_mark_intervals(args.browser_log)
    intervals.sort()
    role_pids: set[int] | None = None
    if args.role:
        if not args.intervals:
            parser.error("--role requires a manifest passed with --intervals")
        manifest = json.loads(args.intervals.read_text())
        role_pids = {
            int(process["pid"])
            for process in manifest.get("processes", [])
            if process.get("role") == args.role
        }
        if not role_pids:
            print(f"No PIDs found for role {args.role!r}.", file=sys.stderr)
            return 2
    samples: list[Sample] = []
    for spec in args.input:
        group, lines, process = read_input(
            spec, args.perf_binary, args.expand_inline, intervals, role_pids
        )
        try:
            samples.extend(
                parse_perf_script(lines, group, intervals=intervals, pids=role_pids)
            )
        finally:
            if process:
                return_code = process.wait()
                if return_code:
                    raise subprocess.CalledProcessError(return_code, process.args)
            elif hasattr(lines, "close"):
                lines.close()
    if args.weight == "samples":
        for sample in samples:
            sample.weight = 1
    if not samples:
        print("No stack samples remained after parsing/filtering.", file=sys.stderr)
        return 2

    aggregates = aggregate_samples(samples)
    frontier, alternatives, areas = build_frontier(
        samples,
        aggregates,
        args.min_share,
        args.min_marginal_share,
        args.limit,
        re.compile(args.include_regex),
        re.compile(args.exclude_regex),
    )
    depths = [len(sample.frames) for sample in samples]
    user_frames = [
        frame for sample in samples for frame in sample.frames if not frame.kernel
    ]
    unknown_user_frames = sum(frame.symbol == "[unknown]" for frame in user_frames)
    unknown_user_fraction = (
        unknown_user_frames / len(user_frames) if user_frames else 1.0
    )
    quality_issues = []
    if not intervals:
        quality_issues.append("measurement intervals unavailable; capture is unscoped")
    elif args.intervals:
        interval_manifest = json.loads(args.intervals.read_text())
        if (
            "measurement_intervals" not in interval_manifest
            and interval_manifest.get("start_time_mono") is not None
        ):
            quality_issues.append(
                "legacy first-start/last-end envelope does not preserve scored intervals"
            )
        elif interval_manifest.get("scoped_to_scored_work") is False:
            quality_issues.append("historical broad interval includes unscored work")
    if len(samples) < 5000:
        quality_issues.append("fewer than 5,000 samples")
    if unknown_user_fraction > 0.15:
        quality_issues.append("more than 15% unknown user-space frames")
    if statistics.median(depths) < 3:
        quality_issues.append("median stack depth below 3")
    if not args.expand_inline:
        quality_issues.append("inline expansion disabled; diagnostic output only")
    report = {
        "quality": {
            "accepted": not quality_issues,
            "issues": quality_issues,
            "samples": len(samples),
            "total_weight": sum(sample.weight for sample in samples),
            "median_depth": statistics.median(depths),
            "p90_depth": sorted(depths)[min(len(depths) - 1, int(len(depths) * 0.9))],
            "unknown_user_frame_fraction": unknown_user_fraction,
            "measurement_intervals": intervals,
            "role": args.role or "all",
            "pids": sorted(role_pids) if role_pids is not None else [],
        },
        "selection": {
            "min_inclusive_share": args.min_share,
            "min_marginal_share": args.min_marginal_share,
            "inventory_complete": True,
            "display_limit": args.limit,
            "tree_min_share": args.tree_min_share,
            "tree_max_depth": args.tree_max_depth,
            "tree_max_children": args.tree_max_children,
            "weight": args.weight,
            "note": (
                "Inclusive and marginal shares retain descendant engine work as an "
                "opportunity bound. Owner-exclusive share attributes samples to the "
                "deepest repository segment. Shares do not predict score delta."
            ),
        },
        "frontier": [public_candidate(item) for item in frontier],
        "overlapping_alternatives": [public_candidate(item) for item in alternatives],
        "area_inventory": [public_candidate(item) for item in areas],
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "candidate_frontier.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    write_markdown(report, args.out_dir / "candidate_frontier.md", args.limit)
    write_text_trees(
        samples,
        frontier,
        args.out_dir / "opportunity_trees.txt",
        args.tree_min_share,
        args.tree_max_depth,
        args.tree_max_children,
    )
    write_collapsed(samples, args.out_dir / "profile.collapsed")
    print(args.out_dir / "candidate_frontier.md")
    print(args.out_dir / "opportunity_trees.txt")
    if quality_issues and not args.allow_low_quality:
        print("Profile rejected: " + "; ".join(quality_issues), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
