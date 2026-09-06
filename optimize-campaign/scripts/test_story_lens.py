#!/usr/bin/env python3
"""Tests for story_lens.py (synthetic captures with hand-computed shares)."""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

import story_lens

HERE = pathlib.Path(__file__).resolve().parent

PFX = "_start;ChromeMain;base::RunLoop::Run(base::Location const&);cc::ProxyMain::BeginMainFrame(std::unique_ptr<cc::BeginMainFrameAndCommitState>)"
BMF = "blink::WidgetBase::BeginMainFrame(viz::BeginFrameArgs const&)"
UPDATE = "blink::Document::UpdateStyleAndLayout(blink::DocumentUpdateReason)"
FORCED_NODE = "blink::Document::UpdateStyleAndLayoutForNode(blink::Node const*, blink::DocumentUpdateReason)"
LFV_UPDATE = "blink::LocalFrameView::UpdateStyleAndLayout()"
LFV_LAYOUT = "blink::LocalFrameView::UpdateLayout()"
BLOCK_LAYOUT = "blink::BlockNode::Layout(blink::ConstraintSpace const&)"
SCROLLTOP = "blink::(anonymous namespace)::v8_element::ScrollTopAttributeSetCallback(v8::FunctionCallbackInfo<v8::Value> const&)"
GBCR = "blink::(anonymous namespace)::v8_element::GetBoundingClientRectOperationCallback(v8::FunctionCallbackInfo<v8::Value> const&)"
EFP = "blink::(anonymous namespace)::v8_document::ElementFromPointOperationCallback(v8::FunctionCallbackInfo<v8::Value> const&)"

# Story A: total weight 100, so every weight is directly a percentage.
STORY_A_LINES = [
    # 1. frame-update beats the forced frame it contains; ink-overflow beats layout; Flex algorithm.
    (f"{PFX};cc::LayerTreeHost::RequestMainFrameUpdate(bool);blink::WidgetBase::UpdateVisualState();"
     f"{LFV_UPDATE};{LFV_LAYOUT};{BLOCK_LAYOUT};blink::FlexLayoutAlgorithm::Layout();"
     "blink::LayoutText::RecalcInkOverflow() 30"),
    # 2. forced layout entered through element.scrollTop, ending in text shaping (harfbuzz leaf).
    (f"{PFX};{BMF};JS:^tick http://localhost/app.js:1:1;Builtins_CallApiCallbackGeneric;{SCROLLTOP};"
     f"blink::Element::setScrollTop(double);{FORCED_NODE};{UPDATE};{LFV_UPDATE};{LFV_LAYOUT};{BLOCK_LAYOUT};"
     "blink::HarfBuzzShaper::Shape(blink::Font const*) const;hb_shape_full 20"),
    # 3. forced layout through getBoundingClientRect, style recalc leaf.
    (f"{PFX};{BMF};JS:^measure http://localhost/app.js:2:2;Builtins_CallApiCallbackOptimized;{GBCR};"
     f"blink::Element::GetBoundingClientRect();{UPDATE};{LFV_UPDATE};blink::StyleEngine::RecalcStyle() 10"),
    # 4. NoFeedback IC that misses into the runtime with a V8 C++ leaf.
    (f"{PFX};{BMF};JS:^render http://localhost/app.js:3:3;Builtins_LoadIC_NoFeedback;"
     "v8::internal::Runtime_LoadNoFeedbackIC_Miss(int, unsigned long*, v8::internal::Isolate*);"
     "v8::internal::LookupIterator::Start() 15"),
    # 4b. NoFeedback IC as the leaf itself.
    (f"{PFX};{BMF};JS:^render http://localhost/app.js:3:3;Builtins_LoadIC_NoFeedback 5"),
    # 5. perf logging with a write leaf inside a timer task (lazy compile).
    (f"{PFX};blink::TimerBase::RunInternal();blink::DOMTimer::Fired();JS:^later http://localhost/app.js:4:4;"
     "v8::internal::Runtime_CompileLazy(int, unsigned long*, v8::internal::Isolate*);"
     "v8::internal::Compiler::Compile(v8::internal::Isolate*, v8::internal::Handle<v8::internal::JSFunction>);"
     "v8::internal::Logger::CodeCreateEvent(v8::internal::LogEventListener::CodeTag);"
     "v8::internal::PerfJitLogger::LogRecordedBuffer(v8::internal::Tagged<v8::internal::AbstractCode>);"
     "__GI___libc_write 8"),
    # 6. perf logging without a write.
    (f"{PFX};blink::TimerBase::RunInternal();JS:^later http://localhost/app.js:4:4;"
     "v8::internal::Logger::CodeCreateEvent(v8::internal::LogEventListener::CodeTag);"
     "v8::internal::CodeEventLogger::NameBuffer::AppendString(v8::internal::Tagged<v8::internal::String>) 5"),
    # 7. hit-test lifecycle wins even though a forced frame precedes it.
    (f"{PFX};{BMF};JS:^probe http://localhost/app.js:5:5;{EFP};blink::Document::ElementFromPoint(double, double);"
     f"{UPDATE};blink::LayoutView::HitTest(blink::HitTestLocation const&, blink::HitTestResult&);"
     "blink::LayoutView::HitTestNoLifecycleUpdate(blink::HitTestLocation const&, blink::HitTestResult&);"
     "blink::PaintLayer::HitTest(blink::HitTestLocation const&) 4"),
    # 8. a bare unknown frame.
    "[unknown] 3",
]

STORY_B_LINES = {
    "capA": [
        (f"{PFX};cc::LayerTreeHost::RequestMainFrameUpdate(bool);"
         "blink::LocalFrameView::RunPaintLifecyclePhase(blink::PaintBenchmarkMode);"
         "blink::PaintLayerPainter::Paint(blink::GraphicsContext&) 10"),
        "_start;blink::TimerBase::RunInternal();JS:^x http://localhost/b.js:1:1 10",
    ],
    "capB": [
        (f"{PFX};cc::LayerTreeHost::RequestMainFrameUpdate(bool);"
         "blink::LocalFrameView::RunPaintLifecyclePhase(blink::PaintBenchmarkMode);"
         "blink::PaintLayerPainter::Paint(blink::GraphicsContext&) 10"),
        "_start;blink::TimerBase::RunInternal();JS:^x http://localhost/b.js:1:1 30",
    ],
}


def candidate(story, kind, name, rank, share, suffix=""):
    return {
        "entry_key": f"story:{story}/{kind}:{name}{suffix}",
        "kind": kind,
        "name": name,
        "rank": rank,
        "inclusive_share": share,
        "marginal_share": share,
        "self_share_of_candidate": 0.0,
        "platform_sensitivity": None,
        "branch_hotspots": [],
        "related_hotspots": [],
        "top_callees": [],
        "top_callers": [],
    }


def frontier_doc(story, frontier):
    return {
        "area_inventory": [],
        "frontier": frontier,
        "overlapping_alternatives": [],
        "quality": {"accepted": True, "samples": 100, "samples_all_threads": 300, "issues": []},
        "score_time_composition": {},
        "selection": {"story": story, "display_limit": 20},
    }


def write_capture(root: pathlib.Path, capture_id: str) -> pathlib.Path:
    stories_dir = root / capture_id / "analysis" / "stories"
    stories_dir.mkdir(parents=True)
    stories = {
        "StoryA": STORY_A_LINES,
        "StoryB": STORY_B_LINES[capture_id],
    }
    frontiers = {
        "StoryA": [
            candidate("StoryA", "function", UPDATE, 1, 0.34),
            candidate("StoryA", "context", "cc::LayerTreeHost::RequestMainFrameUpdate(bool)", 2, 0.30,
                      suffix="@aabe5e3bc3bae3c6"),
        ],
        "StoryB": [
            candidate("StoryB", "function", "cc::LayerTreeHost::RequestMainFrameUpdate(bool)", 1, 0.5),
        ],
    }
    index = {
        "accepted": True,
        "schema_version": 1,
        "scope": "main-thread",
        "story_count": 2,
        "stories": [],
    }
    for story, lines in stories.items():
        story_dir = stories_dir / story
        story_dir.mkdir()
        (story_dir / "profile.collapsed").write_text("\n".join(lines) + "\n")
        (story_dir / "candidate_frontier.json").write_text(json.dumps(frontier_doc(story, frontiers[story])))
        index["stories"].append({
            "story": story,
            "dir": story,
            "candidate_frontier_json": f"{story}/candidate_frontier.json",
            "accepted": True,
            "issues": [],
            "samples": 100,
            "samples_all_threads": 300,
            "scope": "main-thread",
            "score_time_composition": {"sync_wall_ms": 1000.0 if capture_id == "capA" else 3000.0,
                                       "async_wall_ms": 100.0, "estimation_note": "synthetic"},
        })
    (stories_dir / "stories_index.json").write_text(json.dumps(index))
    return root / capture_id


class StoryLensTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls._tmp.name)
        cls.cap_a = write_capture(root, "capA")
        cls.cap_b = write_capture(root, "capB")
        cls.report = story_lens.build_report([str(cls.cap_a)], top=12, floor_pct=1.0, jobs=1)
        cls.story_a = cls.report["stories"]["StoryA"]["per_capture"]["capA"]
        cls.story_b = cls.report["stories"]["StoryB"]["per_capture"]["capA"]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_triggers_precedence(self):
        triggers = self.story_a["triggers"]
        self.assertEqual(triggers["frame-update"], 30.0)  # beats the forced frame inside stack 1
        self.assertEqual(triggers["forced-style-layout"], 30.0)  # stacks 2 and 3
        self.assertEqual(triggers["hit-test-lifecycle"], 4.0)  # beats the earlier forced frame
        self.assertEqual(triggers["timer-task"], 13.0)
        self.assertEqual(triggers["script-other"], 20.0)
        self.assertEqual(triggers["other"], 3.0)
        self.assertEqual(triggers["commit"], 0.0)
        self.assertAlmostEqual(sum(triggers.values()), 100.0, places=3)

    def test_phase_priority(self):
        phases = self.story_a["phases"]
        self.assertEqual(phases["ink-overflow"], 30.0)  # wins over the layout frames in the same stack
        self.assertEqual(phases["layout"], 0.0)
        self.assertEqual(phases["text-shaping"], 20.0)
        self.assertEqual(phases["style-recalc"], 10.0)
        self.assertEqual(phases["hit-test"], 4.0)
        self.assertEqual(phases["script-execution"], 33.0)  # stacks 4, 4b, 5, 6: JS with no Blink phase
        self.assertEqual(phases["other"], 3.0)  # only the bare [unknown] stack matches nothing
        self.assertAlmostEqual(sum(phases.values()), 100.0, places=3)
        self.assertAlmostEqual(sum(self.story_a["phase_self"].values()), 100.0, places=3)
        by_trigger = self.story_a["phases_by_trigger"]
        self.assertEqual(by_trigger["frame-update"], {"ink-overflow": 30.0})
        self.assertEqual(by_trigger["forced-style-layout"], {"text-shaping": 20.0, "style-recalc": 10.0})
        algorithms = self.story_a["layout_by_algorithm"]
        self.assertEqual(algorithms["Flex"], 30.0)
        self.assertEqual(algorithms["Other"], 20.0)
        self.assertEqual(algorithms["total_layout_pct"], 50.0)

    def test_forced_layout_by_entry(self):
        entries = self.story_a["forced_layout_by_entry"]
        self.assertEqual(entries, [
            {"entry": "element.ScrollTopAttributeSet", "inclusive_pct": 20.0},
            {"entry": "element.GetBoundingClientRectOperation", "inclusive_pct": 10.0},
            {"entry": "document.ElementFromPointOperation", "inclusive_pct": 4.0},
        ])

    def test_ownership(self):
        owners = self.story_a["ownership_self"]
        self.assertEqual(owners["blink"], 44.0)
        self.assertEqual(owners["harfbuzz-icu"], 20.0)
        self.assertEqual(owners["libc"], 8.0)
        self.assertEqual(owners["v8-cpp"], 20.0)
        self.assertEqual(owners["v8-builtin"], 5.0)
        self.assertEqual(owners["kernel-unknown"], 3.0)
        self.assertEqual(owners["addressable_pct"], 72.0)
        self.assertEqual(owners["handoff_pct"], 28.0)

    def test_v8_lens(self):
        v8 = self.story_a["v8_lens"]
        self.assertEqual(v8["noFeedback_ic_incl"], 20.0)
        self.assertEqual(v8["noFeedback_ic_self"], 5.0)
        self.assertEqual(v8["ic_miss_runtime_v8self"], 15.0)
        self.assertEqual(v8["compile_lazy_incl"], 8.0)
        self.assertEqual(v8["api_callback_generic_incl"], 20.0)
        self.assertEqual(v8["api_callback_optimized_incl"], 10.0)
        symbols = {item["symbol"]: item["self_pct"] for item in v8["top_v8_self"]}
        self.assertEqual(symbols["v8::internal::LookupIterator::Start"], 15.0)
        self.assertEqual(symbols["Builtins_LoadIC_NoFeedback"], 5.0)
        plumbing = self.story_a["binding_plumbing_self"]
        self.assertEqual(plumbing["v8_to_blink_self"], 15.0)  # LookupIterator leaf
        self.assertEqual(plumbing["blink_to_v8_self"], 0.0)

    def test_overhead(self):
        overhead = self.story_a["overhead"]
        self.assertEqual(overhead["perf_logging_incl"], 13.0)
        self.assertEqual(overhead["perf_logging_with_write_incl"], 8.0)
        self.assertEqual(overhead["unknown_leaf_pct"], 3.0)
        self.assertEqual(overhead["kernel_leaf_pct"], 0.0)
        self.assertEqual(overhead["allocator_hook_self"], 0.0)

    def test_nested_view_and_promotion(self):
        nested = {entry["entry"]: entry for entry in self.story_a["nested_view"]}
        update = nested[UPDATE]
        self.assertEqual(update["kind"], "function")
        self.assertEqual(update["inclusive_pct"], 34.0)
        self.assertEqual(update["self_pct"], 0.0)
        self.assertEqual(update["dominant_phase"], "text-shaping")
        self.assertEqual(update["phase_mix"], {"text-shaping": 20.0, "style-recalc": 10.0, "hit-test": 4.0})
        descendants = {item["symbol"]: item for item in update["descendants"]}
        self.assertNotIn("blink::(anonymous namespace)::v8_element::ScrollTopAttributeSetCallback", descendants)
        self.assertEqual(descendants["blink::LocalFrameView::UpdateStyleAndLayout"]["inclusive_pct"], 30.0)
        layout = descendants["blink::LocalFrameView::UpdateLayout"]
        self.assertEqual(layout["inclusive_pct"], 20.0)
        self.assertEqual(layout["phase"], "layout")
        self.assertTrue(layout["promoted"])
        self.assertEqual(layout["chain_frames"], 1)  # BlockNode::Layout folded in
        self.assertNotIn("blink::BlockNode::Layout", descendants)
        shaper = descendants["blink::HarfBuzzShaper::Shape"]
        self.assertEqual(shaper["phase"], "text-shaping")
        self.assertEqual(shaper["platform_sensitivity"], "font-shaping")
        # Promotion is decided by the descendant's own symbol: shaping is a
        # different mechanism than the entry's forced style/layout root.
        self.assertTrue(shaper["promoted"])
        self.assertEqual(descendants["hb_shape_full"]["self_pct"], 20.0)
        recalc = descendants["blink::StyleEngine::RecalcStyle"]
        self.assertEqual(recalc["self_pct"], 10.0)
        self.assertTrue(recalc["promoted"])
        hit = descendants["blink::LayoutView::HitTest"]
        self.assertEqual(hit["phase"], "hit-test")  # sits above the phase frame; takes its stacks' phase
        # Its own symbol names no phase (a wrapper), so it is not promoted.
        self.assertFalse(hit["promoted"])

        context = nested["cc::LayerTreeHost::RequestMainFrameUpdate(bool)"]
        self.assertEqual(context["kind"], "context")
        self.assertEqual(context["inclusive_pct"], 30.0)
        self.assertEqual(context["dominant_phase"], "ink-overflow")
        context_descendants = {item["symbol"]: item for item in context["descendants"]}
        # Pass-through chain frames fold into the first retained descendant of the same phase:
        # UpdateLayout keeps BlockNode::Layout and FlexLayoutAlgorithm::Layout (identical share, no self).
        self.assertNotIn("blink::FlexLayoutAlgorithm::Layout", context_descendants)
        self.assertNotIn("blink::BlockNode::Layout", context_descendants)
        update_layout = context_descendants["blink::LocalFrameView::UpdateLayout"]
        self.assertEqual(update_layout["phase"], "layout")
        self.assertEqual(update_layout["chain_frames"], 2)
        # Layout covering the whole frame-update entry (30 of 30) restates
        # the entry rather than naming a sub-mechanism: not promoted.
        self.assertFalse(update_layout["promoted"])
        # UpdateVisualState folds LocalFrameView::UpdateStyleAndLayout (both take the stack's ink-overflow phase).
        self.assertEqual(context_descendants["blink::WidgetBase::UpdateVisualState"]["chain_frames"], 1)
        ink = context_descendants["blink::LayoutText::RecalcInkOverflow"]
        self.assertEqual(ink["self_pct"], 30.0)  # self share keeps it out of the chain fold
        self.assertEqual(ink["chain_frames"], 0)
        # Ink overflow inside a frame-update entry is a separate mechanism.
        self.assertTrue(ink["promoted"])

    def test_coverage(self):
        coverage = self.story_a["coverage"]
        self.assertEqual(coverage["frontier_inclusive_union_pct"], 64.0)
        self.assertEqual(coverage["addressable_pct"], 72.0)
        self.assertEqual(coverage["handoff_pct"], 28.0)
        self.assertEqual(coverage["overhead_pct"], 13.0)
        self.assertEqual(coverage["unexplained_addressable_pct"], 8.0)  # the libc write leaf in stack 5

    def test_story_record_metadata(self):
        self.assertEqual(self.story_a["samples"], 100)
        self.assertEqual(self.story_a["samples_all_threads"], 300)
        self.assertEqual(self.story_a["score_time_composition"]["sync_wall_ms"], 1000.0)
        self.assertEqual(self.story_a["total_weight"], 100.0)
        self.assertEqual(self.story_a["stack_count"], 9)
        self.assertEqual(self.story_b["triggers"]["frame-update"], 50.0)
        self.assertEqual(self.story_b["phases"]["paint"], 50.0)

    def test_accepts_stories_dir_and_means_across_captures(self):
        report = story_lens.build_report(
            [str(self.cap_a), str(self.cap_b / "analysis" / "stories")], top=12, floor_pct=1.0, jobs=1)
        self.assertEqual([capture["capture_id"] for capture in report["captures"]], ["capA", "capB"])
        story_b = report["stories"]["StoryB"]
        self.assertEqual(story_b["per_capture"]["capB"]["triggers"]["frame-update"], 25.0)
        mean = story_b["mean"]
        self.assertEqual(mean["captures"], 2)
        self.assertEqual(mean["triggers"]["frame-update"], 37.5)
        self.assertEqual(mean["triggers"]["timer-task"], 62.5)
        self.assertEqual(mean["score_time_composition"]["sync_wall_ms"], 2000.0)
        self.assertEqual(mean["score_time_composition"]["estimation_note"], "synthetic")
        entry = mean["nested_view"][0]
        self.assertEqual(entry["inclusive_pct"], 37.5)
        self.assertEqual(entry["descendants"][0]["symbol"], "blink::LocalFrameView::RunPaintLifecyclePhase")
        self.assertEqual(entry["descendants"][0]["inclusive_pct"], 37.5)
        # StoryA is identical in both captures, so its mean equals the per-capture record.
        story_a = report["stories"]["StoryA"]
        self.assertEqual(story_a["mean"]["triggers"], story_a["per_capture"]["capA"]["triggers"])
        self.assertEqual(story_a["mean"]["forced_layout_by_entry"],
                         story_a["per_capture"]["capA"]["forced_layout_by_entry"])
        for path in (self.cap_a / "analysis" / "stories" / "StoryA" / "profile.collapsed",
                     self.cap_b / "analysis" / "stories" / "StoryB" / "candidate_frontier.json"):
            self.assertIn(str(path), report["input_digests"])

    def test_cli_end_to_end(self):
        with tempfile.TemporaryDirectory() as out_dir:
            out = pathlib.Path(out_dir)
            completed = subprocess.run(
                [sys.executable, str(HERE / "story_lens.py"),
                 "--capture-dir", str(self.cap_a), "--capture-dir", str(self.cap_b),
                 "--out", str(out / "lens.json"), "--markdown", str(out / "lens.md"), "--top", "5"],
                capture_output=True, text=True, check=True)
            self.assertIn("2 stories x 2 captures", completed.stderr)
            report = json.loads((out / "lens.json").read_text())
            self.assertEqual(sorted(report), sorted([
                "schema_version", "generated_at", "parameters", "captures", "stories", "input_digests",
                "elapsed_s"]))
            self.assertEqual(report["schema_version"], 1)
            self.assertEqual(sorted(report["stories"]), ["StoryA", "StoryB"])
            for story in report["stories"].values():
                self.assertEqual(sorted(story), ["mean", "per_capture"])
                self.assertEqual(sorted(story["per_capture"]), ["capA", "capB"])
                for record in story["per_capture"].values():
                    for key in ("ownership_self", "triggers", "phases", "phase_self", "phases_by_trigger",
                                "layout_by_algorithm", "forced_layout_by_entry", "v8_lens",
                                "binding_plumbing_self", "overhead", "nested_view", "coverage",
                                "score_time_composition", "samples", "samples_all_threads"):
                        self.assertIn(key, record)
                    for entry in record["nested_view"]:
                        self.assertLessEqual(len(entry["descendants"]), 5)
            for capture in report["captures"]:
                self.assertEqual(sorted(capture), ["capture_id", "root", "stories_dir", "stories_index_sha256"])
            self.assertEqual(len(report["input_digests"]), 8)
            markdown = (out / "lens.md").read_text()
            self.assertIn("## StoryA", markdown)
            self.assertIn("## StoryB", markdown)
            self.assertIn("element.ScrollTopAttributeSet", markdown)
            self.assertIn("*`blink::LocalFrameView::UpdateLayout`", markdown)


DISPATCH = ("blink::EventDispatcher::Dispatch();"
            "blink::EventTarget::FireEventListeners(blink::Event&, blink::EventTargetData*, "
            "blink::HeapVector<blink::RegisteredEventListener>&)")
LISTENER_JS = "blink::JSBasedEventListener::Invoke(blink::ExecutionContext*, blink::Event*);JS:^onClick http://localhost/app.js:1:1"
RAF = ("blink::PageAnimator::ServiceScriptedAnimations(base::TimeTicks);"
       "blink::FrameRequestCallbackCollection::ExecuteFrameCallbacks(double, double);"
       "blink::V8FrameRequestCallback::InvokeAndReportException(blink::ScriptWrappable*, double)")


class PhaseAssignmentTest(unittest.TestCase):
    """Leaf-most rule for dispatch-like phases and the phase_self self-time view (story total 100)."""

    @classmethod
    def setUpClass(cls):
        lines = [
            # 1. dispatch + JS listener with a V8 builtin leaf: the script owns the stack.
            f"{PFX};{BMF};{DISPATCH};{LISTENER_JS};Builtins_LoadIC 30",
            # 2. dispatch machinery only (no script ran): stays event-dispatch.
            f"{PFX};{BMF};{DISPATCH.split(';')[0]};blink::EventPath::Initialize() 10",
            # 3. dispatch + JS + forced layout: the Blink phase still wins.
            (f"{PFX};{BMF};{DISPATCH};{LISTENER_JS};Builtins_CallApiCallbackGeneric;{GBCR};"
             f"blink::Element::GetBoundingClientRect();{UPDATE};{LFV_UPDATE};{LFV_LAYOUT};{BLOCK_LAYOUT} 25"),
            # 4. rAF callback running plain JS with no Blink phase frame: script-execution, not other.
            f"{PFX};cc::LayerTreeHost::RequestMainFrameUpdate(bool);{RAF};JS:^frame http://localhost/app.js:2:2 20",
            # 5. custom element reaction that invokes script: the script owns the stack.
            (f"{PFX};{BMF};blink::CustomElementReactionStack::PopInvokingReactions();"
             "blink::CustomElementReaction::Invoke(blink::Element&);"
             "JS:^connectedCallback http://localhost/app.js:3:3;Builtins_StoreIC 8"),
            # 6. JS that re-enters dispatch synchronously with no script under it: dispatch is leaf-most.
            f"{PFX};{BMF};{LISTENER_JS};blink::EventDispatcher::DispatchEvent();blink::EventPath::Initialize() 4",
            # 7. nothing matches any phase.
            "[unknown] 3",
        ]
        accumulator = story_lens.StoryAccumulator(story_lens.EntryTable([], "StoryC"), top=12, floor_pct=1.0)
        for line in lines:
            accumulator.add_line(line)
        cls.record = accumulator.finish()

    def test_dispatch_with_script_is_script_execution(self):
        phases = self.record["phases"]
        self.assertEqual(phases["script-execution"], 30.0 + 20.0 + 8.0)
        by_trigger = self.record["phases_by_trigger"]
        self.assertEqual(by_trigger["frame-update"], {"script-execution": 20.0})  # the rAF stack
        self.assertEqual(by_trigger["script-other"]["script-execution"], 38.0)

    def test_dispatch_only_is_event_dispatch(self):
        phases = self.record["phases"]
        self.assertEqual(phases["event-dispatch"], 10.0 + 4.0)
        self.assertEqual(phases["custom-element-reactions"], 0.0)

    def test_blink_phase_beats_dispatch_and_script(self):
        phases = self.record["phases"]
        self.assertEqual(phases["layout"], 25.0)
        self.assertEqual(self.record["phases_by_trigger"]["forced-style-layout"], {"layout": 25.0})

    def test_raf_script_only_is_script_execution(self):
        self.assertEqual(self.record["phases_by_trigger"]["frame-update"], {"script-execution": 20.0})
        self.assertEqual(self.record["phases"]["other"], 3.0)
        self.assertAlmostEqual(sum(self.record["phases"].values()), 100.0, places=3)

    def test_phase_self_sums_to_total(self):
        phase_self = self.record["phase_self"]
        self.assertEqual(sorted(phase_self), sorted(self.record["phases"]))
        self.assertAlmostEqual(sum(phase_self.values()), 100.0, places=3)
        # Leaf-most phase frame per stack: JS (1, 4, 5), dispatch (2, 6), layout (3), nothing (7).
        self.assertEqual(phase_self["script-execution"], 58.0)
        self.assertEqual(phase_self["event-dispatch"], 14.0)
        self.assertEqual(phase_self["layout"], 25.0)
        self.assertEqual(phase_self["other"], 3.0)


if __name__ == "__main__":
    unittest.main()
