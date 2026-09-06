#!/usr/bin/env python3
"""Story-lens integration for the campaign ledger.

`story_lens.py` re-analyzes a profile capture's per-story collapsed stacks
into fixed decompositions (triggers, lifecycle phases, forced-layout entry
APIs, ownership, V8 signals, binding plumbing, profiler overhead, and the
hotspots nested inside each frontier entry). This module validates that
output at `campaign.py profile --lens`, stores a compact summary in the
ledger, and renders it in STATUS.md and the candidate export so reviewers
see what sits underneath a frontier entry instead of only its outer share.
"""
import hashlib
import json
import pathlib
import re
import shutil

LENS_SCHEMA_VERSION = 1
TOP_PHASES = 5
TOP_ENTRIES = 4
TOP_PROMOTED = 6


def _error(message):
    import campaign
    return campaign.CampaignError(message)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _num(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def _as_pairs(value):
    """Accept {name: pct} or [{name|entry|symbol, inclusive_pct|pct}] shapes."""
    pairs = []
    if isinstance(value, dict):
        for name, pct in value.items():
            if isinstance(pct, dict):
                pct = pct.get("inclusive_pct", pct.get("pct"))
            pairs.append((str(name), _num(pct)))
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("entry") or item.get("symbol") or item.get("api")
            pct = item.get("inclusive_pct", item.get("pct", item.get("share_pct")))
            if name is not None:
                pairs.append((str(name), _num(pct)))
    pairs.sort(key=lambda pair: -pair[1])
    return pairs


def _mean_record(story_record):
    if not isinstance(story_record, dict):
        return {}
    mean = story_record.get("mean")
    if isinstance(mean, dict) and mean:
        return mean
    per_capture = story_record.get("per_capture")
    if isinstance(per_capture, dict) and per_capture:
        return next(iter(per_capture.values())) or {}
    return story_record


def symbol_head(symbol):
    """`blink::Foo(bar, baz) const` -> `blink::Foo`."""
    if not isinstance(symbol, str):
        return ""
    head = symbol.split("(", 1)[0]
    for prefix in ("function:", "context:", "symbol:"):
        if head.startswith(prefix):
            head = head[len(prefix):]
    return head.split("@", 1)[0].strip()


# Mechanism-level phases a nested hotspot can belong to. A descendant whose
# own symbol names one of these phases, different from the phase its frontier
# entry's own symbol names, is a separate mechanism hiding under the entry
# and gets its own decomposition row. Patterns mirror story_lens.py.
MECHANISM_PHASES = (
    ("ink-overflow", r"RecalcInkOverflow|SetTextInkOverflow|ComputeInkBounds"),
    ("text-shaping", r"HarfBuzzShaper|hb_shape|ShapingLineBreaker::ShapeLine|InlineNode::ShapeText"),
    ("line-breaking", r"LineBreaker::NextLine|LazyLineBreakIterator|InlineLayoutAlgorithm::Layout"),
    ("min-max-sizing", r"ComputeMinMaxSizes|CalculateMinMaxSizesIgnoringChildren"),
    ("layerization", r"PaintArtifactCompositor::Update|Layerizer|PendingLayer::"),
    ("prepaint", r"PrePaintTreeWalk|RunPrePaintLifecyclePhase"),
    ("paint", r"RunPaintLifecyclePhase|LocalFrameView::PaintTree|PaintLayerPainter|BoxFragmentPainter|FramePainter"),
    ("hit-test", r"HitTestNoLifecycleUpdate|PaintLayer::HitTest"),
    ("active-style-update", r"StyleEngine::UpdateActiveStyle|CollectFeaturesTo|ApplyRuleSetChanges"),
    ("style-recalc", r"StyleEngine::RecalcStyle|StyleEngine::UpdateStyleAndLayoutTree|Document::UpdateStyleAndLayoutTreeForThisDocument|StyleResolver::|StyleInvalidator|Element::RecalcStyle|StyleEngine::RebuildLayoutTree"),
    ("layout", r"LocalFrameView::UpdateLayout|LocalFrameView::RunLayout|LayoutView::LayoutRoot|LayoutView::UpdateLayout|blink::BlockNode::Layout|blink::BlockNode::SimplifiedLayout|LayoutAlgorithm::"),
    ("text-input-state", r"UpdateTextInputStateInternal|CachedTextInputInfo"),
    ("custom-element-reactions", r"CustomElementReactionStack|CustomElementReaction"),
    ("html-parsing", r"ParseHTMLFragment|TryParsingHTMLFragment|HTMLFastPathParser|HTMLDocumentParser|DOMParser::|SetContentFromDOMParser"),
    ("dom-mutation", r"ContainerNode::(AppendChild|InsertBefore|RemoveChild|RemoveChildren|ReplaceChildren|AppendChildren)|NotifyNodeInserted|NotifyNodeRemoved|DetachLayoutTree"),
    ("selector-query", r"SelectorQuery|querySelector"),
    ("attribute-change", r"SetAttributeHinted|SetAttributeWithoutValidation|AttributeChanged"),
    ("canvas-2d", r"Canvas2DRecorderContext|BaseRenderingContext2D|Canvas2DResourceProvider|FlushCanvasInternal"),
    ("event-dispatch", r"EventDispatcher::|EventTarget::FireEventListeners|DispatchEventInternal"),
)
_MECHANISM_PHASES = [(name, re.compile(pattern)) for name, pattern in MECHANISM_PHASES]
# Container phases restate the whole entry when they cover most of it (a
# forced-layout entry is nearly all `layout`); they are promoted only as a
# genuine sub-part (a frame update splitting into style recalc and layout).
CONTAINER_PHASES = {"layout", "style-recalc"}
CONTAINER_MAX_RATIO = 0.8
NEVER_PROMOTED = {"event-dispatch"}


def own_phase(symbol):
    """Phase named by the symbol itself (not inherited from its stacks)."""
    for name, pattern in _MECHANISM_PHASES:
        if pattern.search(symbol or ""):
            return name
    return None


def degenerate_symbol(head):
    """Template-mangled heads collapse to `void blink::`; skip those."""
    return not head or head.endswith("::") or head.startswith("void ") and head.count("::") <= 1


def promote_descendants(entry_symbol, descendants, floor_pct, entry_share=None):
    """Return the descendants that are separate mechanisms under the entry:
    own-phase differs from the entry's own phase, above the floor, one per
    phase (the outermost, which is the largest)."""
    entry_phase = own_phase(entry_symbol)
    chosen = {}
    for d in descendants:
        if not isinstance(d, dict):
            continue
        head = symbol_head(d.get("symbol"))
        if degenerate_symbol(head):
            continue
        phase = own_phase(head)
        if phase is None or phase == entry_phase or phase in NEVER_PROMOTED:
            continue
        share = _num(d.get("inclusive_pct"))
        if share < floor_pct:
            continue
        if (
            phase in CONTAINER_PHASES
            and entry_share
            and share > CONTAINER_MAX_RATIO * entry_share
        ):
            continue
        if phase not in chosen or share > chosen[phase]["inclusive_pct"]:
            chosen[phase] = {
                "symbol": head,
                "inclusive_pct": share,
                "self_pct": _num(d.get("self_pct")),
                "phase": phase,
                "platform_sensitivity": d.get("platform_sensitivity"),
            }
    return sorted(chosen.values(), key=lambda item: -item["inclusive_pct"])


def summarize_story(mean, floor_pct=1.0):
    ownership = mean.get("ownership_self") or {}
    coverage = mean.get("coverage") or {}
    overhead = mean.get("overhead") or {}
    v8 = mean.get("v8_lens") or {}
    plumbing = mean.get("binding_plumbing_self") or {}
    triggers = _as_pairs(mean.get("triggers"))
    phases = _as_pairs(mean.get("phases"))
    entries = _as_pairs(mean.get("forced_layout_by_entry"))
    promoted = []
    nested = mean.get("nested_view") or []
    for entry in nested if isinstance(nested, list) else []:
        if not isinstance(entry, dict):
            continue
        entry_head = symbol_head(entry.get("entry"))
        for item in promote_descendants(
            entry_head, entry.get("descendants") or [], floor_pct,
            _num(entry.get("inclusive_pct")),
        ):
            promoted.append({
                "entry": entry_head,
                "entry_inclusive_pct": _num(entry.get("inclusive_pct")),
                **item,
            })
    promoted.sort(key=lambda item: -item["inclusive_pct"])
    addressable = coverage.get("addressable_pct", ownership.get("addressable_pct"))
    handoff = coverage.get("handoff_pct", ownership.get("handoff_pct"))
    return {
        "addressable_pct": _num(addressable),
        "handoff_pct": _num(handoff),
        "overhead_pct": _num(overhead.get("perf_logging_incl", coverage.get("overhead_pct"))),
        "unknown_leaf_pct": _num(overhead.get("unknown_leaf_pct")),
        "unexplained_addressable_pct": _num(coverage.get("unexplained_addressable_pct")),
        "frontier_union_pct": _num(coverage.get("frontier_inclusive_union_pct")),
        "top_trigger": triggers[0] if triggers else None,
        "triggers": triggers[:6],
        "top_phases": phases[:TOP_PHASES],
        "forced_entries": entries[:TOP_ENTRIES],
        "v8": {
            key: _num(v8.get(key)) for key in (
                "noFeedback_ic_incl", "noFeedback_ic_self", "megamorphic_ic_self",
                "ic_miss_runtime_v8self", "compile_lazy_incl",
                "maglev_main_thread_incl", "interceptor_runtime_incl",
                "json_incl", "gc_incl",
            ) if key in v8
        },
        "plumbing": {
            key: _num(plumbing.get(key)) for key in (
                "blink_to_v8_self", "v8_to_blink_self",
            ) if key in plumbing
        },
        "promoted": promoted[:TOP_PROMOTED],
        "nested_entries": [
            _nested_entry(entry, floor_pct)
            for entry in (nested if isinstance(nested, list) else [])
            if isinstance(entry, dict)
        ],
    }


def _nested_entry(entry, floor_pct):
    entry_head = symbol_head(entry.get("entry"))
    promoted_symbols = {
        item["symbol"] for item in promote_descendants(
            entry_head, entry.get("descendants") or [], floor_pct,
            _num(entry.get("inclusive_pct")),
        )
    }
    descendants = []
    for d in entry.get("descendants") or []:
        if not isinstance(d, dict):
            continue
        head = symbol_head(d.get("symbol"))
        if degenerate_symbol(head):
            continue
        descendants.append({
            "symbol": head,
            "inclusive_pct": _num(d.get("inclusive_pct")),
            "phase": d.get("phase"),
            "promoted": head in promoted_symbols,
            "platform_sensitivity": d.get("platform_sensitivity"),
        })
        if len(descendants) >= 6:
            break
    return {
        "entry": entry_head,
        "inclusive_pct": _num(entry.get("inclusive_pct")),
        "self_pct": _num(entry.get("self_pct")),
        "descendants": descendants,
    }


def summarize(lens):
    stories = lens.get("stories")
    if not isinstance(stories, dict) or not stories:
        raise _error("lens has no stories")
    floor_pct = _num((lens.get("parameters") or {}).get("floor_pct"), 1.0) or 1.0
    return {
        story: summarize_story(_mean_record(record), floor_pct)
        for story, record in sorted(stories.items())
    }


def load_lens(path):
    try:
        data = json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise _error(f"Cannot read lens {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != LENS_SCHEMA_VERSION:
        raise _error(f"Lens {path} is not a story_lens.py v{LENS_SCHEMA_VERSION} output")
    if not isinstance(data.get("stories"), dict) or not data["stories"]:
        raise _error(f"Lens {path} has no per-story records")
    return data


def load_lens_for_import(path, campaign_dir, profile_id):
    """Validate, copy under measurements/, and summarize a lens file."""
    data = load_lens(path)
    source = pathlib.Path(path)
    target_dir = pathlib.Path(campaign_dir) / "measurements"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"lens-{profile_id}.json"
    if source.resolve() != target.resolve():
        shutil.copyfile(source, target)
    digest_value = _sha256(target)
    if digest_value != _sha256(source):
        raise _error("lens copy does not match its source")
    captures = data.get("captures") or []
    capture_ids = []
    capture_roots = []
    for item in captures:
        if isinstance(item, dict) and item.get("capture_id"):
            capture_ids.append(str(item["capture_id"]))
            if item.get("root"):
                capture_roots.append(str(pathlib.Path(item["root"]).resolve()))
        elif isinstance(item, str):
            capture_ids.append(item)
    return {
        "path": str(target),
        "sha256": digest_value,
        "source_path": str(source.resolve()),
        "capture_ids": capture_ids,
        "capture_roots": capture_roots,
        "summary": summarize(data),
    }


def check_lens_matches_captures(record, capture_stories, captures):
    """`captures` maps capture_id -> local_results directory of the summary.

    The lens names captures by the basename of the directory it was given,
    which may be a symlink to the summary's results directory; either the ids
    or the resolved result roots must agree.
    """
    stories = set(record["summary"])
    expected = {story for story in capture_stories if story}
    if stories != expected:
        missing = sorted(expected - stories)
        extra = sorted(stories - expected)
        raise _error(
            "lens stories do not match the captures"
            + (f"; missing {missing[:5]}" if missing else "")
            + (f"; extra {extra[:5]}" if extra else "")
        )
    if isinstance(captures, dict):
        capture_ids = set(captures)
        expected_roots = {
            str(pathlib.Path(path).resolve())
            for path in captures.values() if path
        }
    else:
        capture_ids = set(captures)
        expected_roots = set()
    lens_ids = set(record.get("capture_ids") or [])
    lens_roots = set(record.get("capture_roots") or [])
    if lens_ids and lens_ids != capture_ids:
        if not (lens_roots and expected_roots and lens_roots == expected_roots):
            raise _error(
                f"lens was computed from captures {sorted(lens_ids)}, not "
                f"{sorted(capture_ids)} (result roots differ too)"
            )
    return sorted(stories)


# ---------------- rendering ----------------

def _pct(value):
    return f"{_num(value):.1f}%"


def _pairs_text(pairs, limit):
    return ", ".join(f"{name} {pct:.1f}" for name, pct in pairs[:limit]) or "—"


def promoted_for_opportunity(summary, opp):
    """Nested hotspots of a different phase inside this discovery's entry."""
    if not summary:
        return []
    story = opp.get("target_story")
    record = summary.get(story) if story else None
    if not record:
        return []
    anchor = opp.get("anchor") or ""
    head = symbol_head(anchor.split("/", 1)[1] if "/" in anchor else anchor)
    return [
        item for item in record.get("promoted", [])
        if item.get("entry") == head
    ]


def nested_for_opportunity(summary, opp):
    if not summary:
        return None
    story = opp.get("target_story")
    record = summary.get(story) if story else None
    if not record:
        return None
    anchor = opp.get("anchor") or ""
    head = symbol_head(anchor.split("/", 1)[1] if "/" in anchor else anchor)
    for entry in record.get("nested_entries", []):
        if entry.get("entry") == head:
            return entry
    return None


def status_sections(profile, ledger=None):
    summary = profile.get("lens_summary") or {}
    lines = []
    if not summary:
        return lines
    lines.append("")
    lines.append(f"## Story lens (`{profile.get('id')}`)")
    lines.append(
        "_Share of each story's scored main-thread cycles. Addressable = Blink/Chromium "
        "self time; hand-off = V8, JIT code and unknown leaves; overhead = profiler "
        "logging; unexplained = addressable cycles no frontier entry covers._"
    )
    lines.append("")
    lines.append(
        "| Story | Addressable | Hand-off | Overhead | Unexplained | Top trigger | Top phases |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | --- | --- |")
    for story, record in summary.items():
        trigger = record.get("top_trigger")
        lines.append(
            f"| {story} | {_pct(record.get('addressable_pct'))} | "
            f"{_pct(record.get('handoff_pct'))} | {_pct(record.get('overhead_pct'))} | "
            f"{_pct(record.get('unexplained_addressable_pct'))} | "
            f"{(trigger[0] + ' ' + f'{trigger[1]:.0f}') if trigger else '—'} | "
            f"{_pairs_text(record.get('top_phases', []), 3)} |"
        )
    forced = [
        (story, record["forced_entries"])
        for story, record in summary.items()
        if record.get("forced_entries") and record["forced_entries"][0][1] >= 1.0
    ]
    if forced:
        lines.append("")
        lines.append("**Forced style/layout by JS entry API:** "
                     + " · ".join(
                         f"{story}: {_pairs_text(entries, 3)}"
                         for story, entries in forced[:12]
                     ))
    promoted = [
        (story, record["promoted"])
        for story, record in summary.items() if record.get("promoted")
    ]
    if promoted:
        lines.append("")
        lines.append("## Underneath the frontier (nested hotspots of a different phase)")
        lines.append("| Story | Frontier entry | Nested hotspot | Share | Phase | Portability |")
        lines.append("| --- | --- | --- | ---: | --- | --- |")
        for story, items in promoted:
            for item in items[:4]:
                lines.append(
                    f"| {story} | `{item['entry']}` ({item['entry_inclusive_pct']:.1f}%) | "
                    f"`{item['symbol']}` | {item['inclusive_pct']:.1f}% | "
                    f"{item.get('phase') or ''} | {item.get('platform_sensitivity') or 'portable'} |"
                )
    v8_rows = [
        (story, record["v8"]) for story, record in summary.items()
        if record.get("v8") and max(record["v8"].values(), default=0.0) >= 2.0
    ]
    if v8_rows:
        lines.append("")
        lines.append("## Hand-off signals (not Chromium-addressable; V8 leads)")
        lines.append("| Story | NoFeedback IC incl | IC-miss runtime self | CompileLazy | Maglev main-thread | Megamorphic self | JSON |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for story, v8 in sorted(v8_rows, key=lambda row: -max(row[1].values())):
            lines.append(
                f"| {story} | {_pct(v8.get('noFeedback_ic_incl'))} | "
                f"{_pct(v8.get('ic_miss_runtime_v8self'))} | {_pct(v8.get('compile_lazy_incl'))} | "
                f"{_pct(v8.get('maglev_main_thread_incl'))} | {_pct(v8.get('megamorphic_ic_self'))} | "
                f"{_pct(v8.get('json_incl'))} |"
            )
    return lines


def export_sections(profile, opps):
    """Markdown sections for candidates.md; also annotates opp rows."""
    summary = profile.get("lens_summary") or {}
    lines = []
    if not summary:
        return lines
    for row in opps:
        row["promoted_descendants"] = promoted_for_opportunity(summary, row)
        nested = nested_for_opportunity(summary, row)
        if nested:
            row["nested_view"] = nested
    lines.append("## Story coverage (from the lens)")
    lines.append("")
    lines.append("| Story | Addressable | Hand-off | Overhead | Frontier union | Unexplained |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for story, record in summary.items():
        lines.append(
            f"| {story} | {_pct(record.get('addressable_pct'))} | {_pct(record.get('handoff_pct'))} | "
            f"{_pct(record.get('overhead_pct'))} | {_pct(record.get('frontier_union_pct'))} | "
            f"{_pct(record.get('unexplained_addressable_pct'))} |"
        )
    lines.append("")
    lines.append("## Underneath each area")
    lines.append("")
    lines.append(
        "_Top nested functions inside each discovery's frontier entry; `*` marks a "
        "nested hotspot of a different phase that clears the floor and must get "
        "its own decomposition row._"
    )
    lines.append("")
    for row in opps:
        nested = row.get("nested_view")
        if not nested or not nested.get("descendants"):
            continue
        parts = []
        for d in nested["descendants"][:6]:
            mark = "*" if d.get("promoted") else ""
            parts.append(f"{mark}`{d['symbol']}` {d['inclusive_pct']:.1f}% [{d.get('phase') or '?'}]")
        lines.append(
            f"- #{row['id']} {row.get('target_story')} `{nested['entry']}` "
            f"({nested['inclusive_pct']:.1f}% incl, {nested['self_pct']:.1f}% self): "
            + "; ".join(parts)
        )
    lines.append("")
    return lines
