#!/usr/bin/env python3

import importlib.util
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).with_name("analyze_stacks.py")
SPEC = importlib.util.spec_from_file_location("analyze_stacks", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def sample(pid, timestamp, period, frames):
    lines = [f"chrome  {pid} {timestamp:.6f}: {period:10d} cycles: \n"]
    for index, frame in enumerate(frames):
        lines.append(f"\t{0x1000 + index:x} {frame}+0x1 (/tmp/chrome)\n")
    lines.append("\n")
    return lines


class IntervalCheckerTest(unittest.TestCase):
    def test_matches_naive_membership_including_bounds(self):
        intervals = [(10.0, 12.0), (11.5, 13.0), (20.0, 21.0), (30.0, 30.0)]
        checker = MODULE.make_interval_checker(intervals)
        probes = [
            9.999, 10.0, 11.0, 12.0, 12.5, 13.0, 13.001, 19.9, 20.0, 20.5,
            21.0, 21.1, 29.9, 30.0, 30.1, 0.0, 100.0,
        ]
        for timestamp in probes:
            self.assertEqual(
                MODULE.in_intervals(timestamp, intervals),
                checker(timestamp),
                f"divergence at {timestamp}",
            )

    def test_empty_intervals_accepts_everything(self):
        checker = MODULE.make_interval_checker([])
        self.assertTrue(checker(0.0))
        self.assertTrue(checker(1e12))


class AnalyzeStacksTest(unittest.TestCase):
    def test_text_tree_preserves_material_branches_and_area_views(self):
        lines = []
        lines += sample(
            10,
            1.0,
            50,
            [
                "blink::Element::RecalcStyle()",
                "blink::LocalFrameView::UpdateStyleAndLayoutIfNeededRecursive()",
                "blink::WidgetBase::BeginMainFrame()",
                "cc::ProxyMain::BeginMainFrame()",
            ],
        )
        lines += sample(
            10,
            2.0,
            30,
            [
                "blink::LocalFrameView::RunPaintLifecyclePhase()",
                "blink::WidgetBase::BeginMainFrame()",
                "cc::ProxyMain::BeginMainFrame()",
            ],
        )
        lines += sample(
            10,
            3.0,
            20,
            [
                "JS:clickHandler app.js:1:1",
                "v8::internal::Execution::Call()",
                "blink::EventDispatcher::Dispatch()",
                "cc::ProxyMain::BeginMainFrame()",
            ],
        )
        parsed = MODULE.parse_perf_script(lines, "story")
        frontier = [
            {"name": "blink::LocalFrameView::UpdateStyleAndLayoutIfNeededRecursive()"}
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "opportunity_trees.txt"
            MODULE.write_text_trees(parsed, frontier, path, 0.1, 8, 8)
            output = path.read_text()
        self.assertIn("== CROSS-AREA OPPORTUNITY TREE ==", output)
        self.assertIn("cc::ProxyMain::BeginMainFrame (100.00%)", output)
        self.assertIn("blink::WidgetBase::BeginMainFrame (80.00%)", output)
        self.assertIn(
            "[*] blink::LocalFrameView::UpdateStyleAndLayoutIfNeededRecursive "
            "(50.00%)",
            output,
        )
        self.assertIn("== BLINK OWNED TREE (80.00% exclusive coverage) ==", output)
        self.assertIn(
            "== V8 / JAVASCRIPT OWNED TREE (20.00% exclusive coverage) ==",
            output,
        )
        self.assertIn("[application script execution]", output)
        self.assertNotIn("clickHandler app.js", output)

    def test_text_tree_collapses_linear_same_area_trunks(self):
        lines = sample(
            10,
            1.0,
            100,
            [
                "blink::Tree::Leaf()",
                "blink::Tree::C()",
                "blink::Tree::B()",
                "blink::Tree::A()",
            ],
        )
        parsed = MODULE.parse_perf_script(lines, "story")
        tree = MODULE.build_text_tree(parsed)
        rendered = "\n".join(
            MODULE.render_text_tree(tree, 100, 0.01, 8, 8, set(), True)
        )
        self.assertNotIn("same-area trunk", rendered)
        self.assertNotIn("deeper material work", rendered)
        self.assertNotIn("self / pruned branches", rendered)
        self.assertNotIn("other roots", rendered)
        self.assertNotIn("blink::Tree::B", rendered)
        self.assertNotIn("blink::Tree::C", rendered)
        self.assertIn("└── [blink] blink::Tree::A", rendered)
        self.assertIn("    └── [blink] blink::Tree::Leaf", rendered)

    def test_text_tree_draws_sibling_continuation_lines(self):
        lines = []
        lines += sample(
            10,
            1.0,
            60,
            ["blink::Tree::LeafA()", "blink::Tree::BranchA()", "cc::Root()"],
        )
        lines += sample(
            10,
            2.0,
            40,
            ["blink::Tree::LeafB()", "blink::Tree::BranchB()", "cc::Root()"],
        )
        parsed = MODULE.parse_perf_script(lines, "story")
        rendered = "\n".join(
            MODULE.render_text_tree(
                MODULE.build_text_tree(parsed), 100, 0.01, 8, 8, set(), True
            )
        )
        self.assertIn("└── [chromium] cc::Root (100.00%)", rendered)
        self.assertIn("    ├── [blink] blink::Tree::BranchA (60.00%)", rendered)
        self.assertIn("    │   └── [blink] blink::Tree::LeafA (60.00%)", rendered)
        self.assertIn("    └── [blink] blink::Tree::BranchB (40.00%)", rendered)

    def test_text_tree_folds_application_script_but_keeps_v8_plumbing(self):
        for symbol in (
            "JS:clickHandler https://example.test/app.js:42:7",
            "JIT:*render dashboard.js:12:3",
            "LazyCompile:*update view.js:8:1",
            "Function: anonymous",
            "RegExp:^item-[0-9]+$",
        ):
            self.assertEqual(
                "[application script execution]", MODULE.tree_symbol(symbol)
            )
        self.assertEqual(
            "Builtins_InterpreterEntryTrampoline",
            MODULE.tree_symbol("Builtins_InterpreterEntryTrampoline"),
        )
        self.assertEqual(
            "v8::internal::JsonParser<…>::ParseJsonArray",
            MODULE.tree_symbol("v8::internal::JsonParser<int>::ParseJsonArray()"),
        )

    def test_generic_execution_shells_are_not_candidates(self):
        for symbol in (
            "base::Thread::ThreadMain()",
            "base::RepeatingCallback<void (int)>::Run(int) &&",
            "base::(anonymous namespace)::WorkSourceDispatch(_GSource*, int (*)(void*), void*)",
            "base::internal::PostTaskAndReplyRelay::RunTaskAndPostReply(base::internal::PostTaskAndReplyRelay)",
            "content::(anonymous namespace)::ChildIOThread::Run(base::RunLoop*)",
            "cc::CategorizedWorkerPoolJob::Run(base::span<int>)",
            "blink::scheduler::NonMainThreadImpl::SimpleThreadImpl::Run()",
            "blink::bindings::CallbackInvokeHelper<blink::CallbackBase>::Call(int)",
            "blink::(anonymous namespace)::v8_html_element::ClickOperationCallback(v8::FunctionCallbackInfo<v8::Value> const&)",
            "blink::V8ScriptRunner::CallFunction(v8::Local<v8::Function>)",
            "blink::FrameRequestCallbackCollection::ExecuteFrameCallbacks(double)",
            "blink::WidgetBase::BeginMainFrame(viz::BeginFrameArgs const&)",
            "blink::PageAnimator::ServiceScriptedAnimations(base::TimeTicks)",
            "blink::TimerBase::RunInternal()",
            "blink::DOMTimer::Fired()",
            "blink::ScheduledAction::Execute(blink::ExecutionContext*)",
            "blink::EventTarget::DispatchEventInternal(blink::Event&)",
            "blink::EventDispatcher::Dispatch()",
            "blink::EventDispatcher::DispatchEvent(blink::Node&, blink::Event&)",
        ):
            self.assertIsNotNone(MODULE.DEFAULT_EXCLUDE.search(symbol), symbol)

    def test_parser_reverses_perf_leaf_first_stacks(self):
        lines = sample(
            10,
            1.25,
            99,
            ["blink::Leaf()", "blink::Parent()", "content::Root()"],
        )
        parsed = MODULE.parse_perf_script(lines, "story")
        self.assertEqual(1, len(parsed))
        self.assertEqual(99, parsed[0].weight)
        self.assertEqual(
            ["content::Root()", "blink::Parent()", "blink::Leaf()"],
            [frame.symbol for frame in parsed[0].frames],
        )

    def test_parser_accepts_perf_event_modifiers(self):
        lines = sample(10, 1.25, 99, ["blink::Leaf()"])
        lines[0] = lines[0].replace("cycles:", "cycles:P:")
        parsed = MODULE.parse_perf_script(lines, "story")
        self.assertEqual(1, len(parsed))
        self.assertEqual(99, parsed[0].weight)

    def test_perf_script_command_explicitly_controls_inline_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path = pathlib.Path(directory) / "profile.data"
            data_path.touch()
            for expand_inline, expected in ((True, "--inline"), (False, "--no-inline")):
                process = mock.Mock()
                process.stdout = iter(())
                with mock.patch.object(
                    MODULE.subprocess, "Popen", return_value=process
                ) as popen:
                    _, _, returned_process = MODULE.read_input(
                        str(data_path), "perf", expand_inline, [], None
                    )
                command = popen.call_args.args[0]
                self.assertIn(expected, command)
                self.assertNotIn(
                    "--no-inline" if expand_inline else "--inline", command
                )
                self.assertIs(process, returned_process)

    def test_merged_parent_beats_overlapping_leaves(self):
        lines = []
        lines += sample(
            10,
            1.0,
            60,
            [
                "blink::Tree::LeafA()",
                "blink::Tree::Walk()",
                "content::RendererMain()",
            ],
        )
        lines += sample(
            10,
            2.0,
            40,
            [
                "blink::Tree::LeafB()",
                "blink::Tree::Walk()",
                "content::RendererMain()",
            ],
        )
        parsed = MODULE.parse_perf_script(lines, "story")
        aggregates = MODULE.aggregate_samples(parsed)
        frontier, _, areas = MODULE.build_frontier(
            parsed,
            aggregates,
            min_share=0.01,
            min_marginal_share=0.01,
            limit=10,
            include=MODULE.DEFAULT_INCLUDE,
            exclude=MODULE.DEFAULT_EXCLUDE,
        )
        self.assertEqual("blink::Tree::Walk()", frontier[0]["name"])
        self.assertEqual(1.0, frontier[0]["inclusive_share"])
        self.assertGreater(frontier[0]["tree_share_of_candidate"], 0.0)
        self.assertEqual(1, len(frontier))
        self.assertEqual("blink::Tree", areas[0]["name"])

    def test_machine_frontier_continues_past_display_limit(self):
        lines = []
        for index in range(25):
            lines += sample(
                10,
                1.0 + index,
                40,
                [f"blink::IndependentArea{index}::Run()"],
            )
        parsed = MODULE.parse_perf_script(lines, "story")
        aggregates = MODULE.aggregate_samples(parsed)
        frontier, _, _ = MODULE.build_frontier(
            parsed,
            aggregates,
            min_share=0.001,
            min_marginal_share=0.001,
            limit=5,
            include=MODULE.DEFAULT_INCLUDE,
            exclude=MODULE.DEFAULT_EXCLUDE,
        )
        self.assertGreaterEqual(len(frontier), 25)

    def test_configured_floor_below_point_one_percent_is_honored(self):
        lines = []
        lines += sample(10, 1.0, 75, ["blink::TinyOpportunity::Run()"])
        lines += sample(10, 2.0, 99925, ["libc::UnownedWork()"])
        parsed = MODULE.parse_perf_script(lines, "story")
        frontier, _, _ = MODULE.build_frontier(
            parsed,
            MODULE.aggregate_samples(parsed),
            min_share=0.0005,
            min_marginal_share=0.0005,
            limit=20,
            include=MODULE.DEFAULT_INCLUDE,
            exclude=MODULE.DEFAULT_EXCLUDE,
        )
        self.assertTrue(any(
            item["name"] == "blink::TinyOpportunity::Run()"
            for item in frontier
        ))

    def test_shared_hot_alternative_is_assigned_to_one_frontier_area(self):
        lines = []
        for index in range(3):
            lines += sample(
                10, 1.0 + index * 2, 8,
                [f"blink::Own{index}::Run()", f"blink::Parent{index}::Run()"],
            )
            lines += sample(
                10, 2.0 + index * 2, 2,
                ["blink::SharedF::Run()", f"blink::Parent{index}::Run()"],
            )
        parsed = MODULE.parse_perf_script(lines, "story")
        frontier, alternatives, _ = MODULE.build_frontier(
            parsed,
            MODULE.aggregate_samples(parsed),
            min_share=0.01,
            min_marginal_share=0.01,
            limit=20,
            include=MODULE.DEFAULT_INCLUDE,
            exclude=MODULE.DEFAULT_EXCLUDE,
        )
        shared = next(
            item for item in alternatives
            if item["name"] == "blink::SharedF::Run()"
        )
        self.assertIsNotNone(shared["assigned_frontier_entry"])
        self.assertEqual(3, len(shared["frontier_overlaps"]))
        self.assertFalse(any(
            hotspot["name"] == "blink::SharedF::Run()"
            for item in frontier
            for hotspot in item.get("related_hotspots", [])
        ))

    def test_split_shared_alternative_stays_global_and_contexts_are_distinct(self):
        lines = []
        lines += sample(
            10, 1.0, 12,
            ["blink::OwnA::Run()", "blink::ParentA::Run()"],
        )
        lines += sample(
            10, 2.0, 8,
            ["blink::SharedF::Run()", "blink::ParentA::Run()"],
        )
        lines += sample(
            10, 3.0, 13,
            ["blink::OwnB::Run()", "blink::ParentB::Run()"],
        )
        lines += sample(
            10, 4.0, 7,
            ["blink::SharedF::Run()", "blink::ParentB::Run()"],
        )
        lines += sample(10, 5.0, 9960, ["libc::UnownedWork()"])
        parsed = MODULE.parse_perf_script(lines, "story")
        frontier, alternatives, _ = MODULE.build_frontier(
            parsed,
            MODULE.aggregate_samples(parsed),
            min_share=0.001,
            min_marginal_share=0.001,
            limit=20,
            include=MODULE.DEFAULT_INCLUDE,
            exclude=MODULE.DEFAULT_EXCLUDE,
        )
        shared_function = next(
            item for item in alternatives
            if item["kind"] == "function"
            and item["name"] == "blink::SharedF::Run()"
        )
        self.assertAlmostEqual(0.0015, shared_function["inclusive_share"])
        self.assertIsNotNone(shared_function["assigned_frontier_entry"])

    def test_same_symbol_context_alternatives_have_stable_distinct_keys(self):
        lines = []
        lines += sample(10, 1.0, 30, ["blink::OwnA::Run()", "blink::ParentA::Run()"])
        lines += sample(10, 2.0, 10, ["blink::SharedF::Run()", "blink::ParentA::Run()"])
        lines += sample(10, 3.0, 30, ["blink::OwnB::Run()", "blink::ParentB::Run()"])
        lines += sample(10, 4.0, 10, ["blink::SharedF::Run()", "blink::ParentB::Run()"])
        lines += sample(10, 5.0, 20, ["libc::UnownedWork()"])
        parsed = MODULE.parse_perf_script(lines, "story")
        _, alternatives, _ = MODULE.build_frontier(
            parsed,
            MODULE.aggregate_samples(parsed),
            min_share=0.05,
            min_marginal_share=0.05,
            limit=20,
            include=MODULE.DEFAULT_INCLUDE,
            exclude=MODULE.DEFAULT_EXCLUDE,
        )
        shared_contexts = [
            item for item in alternatives
            if item["kind"] == "context"
            and item["name"] == "blink::SharedF::Run()"
        ]
        self.assertEqual(2, len(shared_contexts))
        self.assertEqual(2, len({item["entry_key"] for item in shared_contexts}))
        self.assertTrue(all(item["assigned_frontier_entry"] for item in shared_contexts))

    def test_floor_worthy_low_score_entry_is_not_skipped(self):
        # After ParentC is selected, TargetB's residual falls below the
        # marginal floor but still outscores deep single-caller TargetA.
        # Selection must skip TargetB and still take TargetA, or TargetA
        # would become an alternative overlapping no frontier entry.
        lines = []
        lines += sample(10, 1.0, 2000, ["blink::ParentC::Run()"])
        lines += sample(10, 2.0, 500, [
            "blink::TargetB::Run()", "libapp::CallerX()",
            "blink::ParentC::Run()",
        ])
        lines += sample(10, 3.0, 450, [
            "blink::TargetB::Run()", "libapp::CallerY()",
            "blink::ParentC::Run()",
        ])
        lines += sample(10, 4.0, 95, [
            "blink::TargetB::Run()", "libapp::CallerZ()",
        ])
        lines += sample(10, 5.0, 100, [
            "blink::TargetA::Run()", "libapp::Wrap1()", "libapp::Wrap2()",
            "libapp::Wrap3()", "libapp::Wrap4()", "libapp::Wrap5()",
        ])
        lines += sample(10, 6.0, 96855, ["libc::UnownedWork()"])
        parsed = MODULE.parse_perf_script(lines, "story")
        frontier, alternatives, _ = MODULE.build_frontier(
            parsed,
            MODULE.aggregate_samples(parsed),
            min_share=0.001,
            min_marginal_share=0.001,
            limit=20,
            include=MODULE.DEFAULT_INCLUDE,
            exclude=MODULE.DEFAULT_EXCLUDE,
        )
        self.assertTrue(any(
            item["name"] == "blink::TargetA::Run()" for item in frontier
        ))
        self.assertFalse(any(
            item["marginal_share"] < 0.001 for item in frontier
        ))
        self.assertTrue(all(
            item["assigned_frontier_entry"] for item in alternatives
        ))

    def test_class_area_does_not_hide_distinct_operations(self):
        lines = []
        lines += sample(
            10,
            1.0,
            60,
            ["blink::Element::RecalcStyle()", "blink::StyleEngine::Update()"],
        )
        lines += sample(
            10,
            2.0,
            40,
            ["blink::Element::DetachLayoutTree()", "blink::Document::Shutdown()"],
        )
        parsed = MODULE.parse_perf_script(lines, "story")
        aggregates = MODULE.aggregate_samples(parsed)
        frontier, alternatives, areas = MODULE.build_frontier(
            parsed,
            aggregates,
            min_share=0.01,
            min_marginal_share=0.01,
            limit=10,
            include=MODULE.DEFAULT_INCLUDE,
            exclude=MODULE.DEFAULT_EXCLUDE,
        )
        self.assertEqual("blink::Element", areas[0]["name"])
        selected_names = {candidate["name"] for candidate in frontier}
        alternative_names = {candidate["name"] for candidate in alternatives}
        self.assertNotIn("blink::Element", selected_names)
        self.assertTrue(
            {"blink::Element::RecalcStyle()", "blink::StyleEngine::Update()"}
            & (selected_names | alternative_names)
        )

    def test_parent_dossier_lists_nested_hotspots(self):
        lines = []
        lines += sample(
            10,
            1.0,
            60,
            [
                "blink::StyleCascade::Apply()",
                "blink::Element::RecalcStyle()",
                "blink::LocalFrameView::UpdateStyleAndLayout()",
            ],
        )
        lines += sample(
            10,
            2.0,
            40,
            [
                "blink::StyleResolver::ApplyBaseStyle()",
                "blink::Element::RecalcStyle()",
                "blink::LocalFrameView::UpdateStyleAndLayout()",
            ],
        )
        parsed = MODULE.parse_perf_script(lines, "story")
        aggregates = MODULE.aggregate_samples(parsed)
        frontier, _, _ = MODULE.build_frontier(
            parsed,
            aggregates,
            min_share=0.01,
            min_marginal_share=0.01,
            limit=10,
            include=MODULE.DEFAULT_INCLUDE,
            exclude=MODULE.DEFAULT_EXCLUDE,
        )
        parent = next(
            candidate
            for candidate in frontier
            if candidate["name"] == "blink::LocalFrameView::UpdateStyleAndLayout()"
        )
        hotspot_names = {item["name"] for item in parent["related_hotspots"]}
        self.assertIn("blink::Element::RecalcStyle()", hotspot_names)
        self.assertIn("blink::StyleCascade::Apply()", hotspot_names)
        branch_names = {item["name"] for item in parent["branch_hotspots"]}
        self.assertIn("blink::Element::RecalcStyle()", branch_names)
        self.assertIn("blink::StyleCascade::Apply()", branch_names)

    def test_intervals_accept_new_and_legacy_manifests(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "intervals.json"
            path.write_text(
                '{"measurement_intervals": [{"start": 1, "end": 2}, [3, 4]]}'
            )
            self.assertEqual([(1.0, 2.0), (3.0, 4.0)], MODULE.load_intervals(path))
            path.write_text('{"start_time_mono": 5, "end_time_mono": 6}')
            self.assertEqual([(5.0, 6.0)], MODULE.load_intervals(path))

    def test_function_merge_spans_distinct_call_trees(self):
        lines = []
        lines += sample(
            10,
            1.0,
            60,
            [
                "blink::Shared::Compute()",
                "blink::CallerA::Run()",
                "content::RootA()",
            ],
        )
        lines += sample(
            10,
            2.0,
            40,
            [
                "blink::Shared::Compute()",
                "blink::CallerB::Run()",
                "content::RootB()",
            ],
        )
        parsed = MODULE.parse_perf_script(lines, "story")
        aggregate = MODULE.aggregate_samples(parsed)[
            ("function", "blink::Shared::Compute()")
        ]
        candidate = MODULE.make_candidate(
            aggregate,
            parsed,
            total_weight=100,
            group_totals=MODULE.collections.Counter(story=100),
            uncovered=0b11,
        )
        self.assertEqual(1.0, candidate["inclusive_share"])
        self.assertEqual(2, candidate["caller_contexts"])
        self.assertGreater(candidate["caller_diversity"], 0.0)

    def test_mark_log_preserves_disjoint_intervals(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "browser.stdout.log"
            path.write_text(
                "[SP3_MONO_TIME] sp3-measurement-start: 1.0\n"
                "[SP3_MONO_TIME] sp3-measurement-end: 2.0\n"
                "unscored gap\n"
                "[SP3_MONO_TIME] sp3-measurement-start: 4.0\n"
                "[SP3_MONO_TIME] sp3-measurement-end: 5.5\n"
            )
            self.assertEqual(
                [(1.0, 2.0), (4.0, 5.5)], MODULE.load_mark_intervals([path])
            )

    def test_mark_log_prefers_exact_score_intervals(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "browser.stdout.log"
            path.write_text(
                "[SP3_SCORE_TIME] sp3-measurement-start: 1.0\n"
                "[SP3_SCORE_TIME] Suite.Test-start: 1.2\n"
                "[SP3_SCORE_TIME] Suite.Test-sync-end: 1.4\n"
                "[SP3_SCORE_TIME] Suite.Test-async-start: 1.5\n"
                "[SP3_SCORE_TIME] Suite.Test-async-end: 1.8\n"
                "[SP3_SCORE_TIME] sp3-measurement-end: 2.0\n"
                "[SP3_MONO_TIME] sp3-measurement-start: 1.0\n"
                "[SP3_MONO_TIME] sp3-measurement-end: 2.0\n"
            )
            self.assertEqual(
                [(1.2, 1.4), (1.5, 1.8)], MODULE.load_mark_intervals([path])
            )

    def test_deepest_owner_excludes_v8_but_keeps_native_primitive(self):
        v8_lines = sample(
            10,
            1.0,
            10,
            ["v8::internal::Execute()", "blink::V8ScriptRunner::Run()"],
        )
        native_lines = sample(
            10,
            2.0,
            10,
            ["malloc", "blink::LayoutObject::Update()"],
        )
        v8_sample = MODULE.parse_perf_script(v8_lines, "story")[0]
        native_sample = MODULE.parse_perf_script(native_lines, "story")[0]
        self.assertFalse(MODULE.sample_is_addressable(v8_sample))
        self.assertTrue(MODULE.sample_is_addressable(native_sample))

        skia_lines = sample(
            10,
            3.0,
            10,
            ["SkCanvas::drawRect()", "cc::PaintOpBuffer::Playback()"],
        )
        skia_sample = MODULE.parse_perf_script(skia_lines, "story")[0]
        self.assertFalse(MODULE.sample_is_addressable(skia_sample))

        skia_ext_lines = sample(
            10,
            4.0,
            10,
            ["skia::ImageOperations::Resize()", "cc::PaintOpBuffer::Playback()"],
        )
        skia_ext_sample = MODULE.parse_perf_script(skia_ext_lines, "story")[0]
        self.assertTrue(MODULE.sample_is_addressable(skia_ext_sample))
        self.assertEqual("chromium", MODULE.tree_area(skia_ext_sample.frames[-1]))

    def test_class_area_ignores_qualified_template_arguments(self):
        symbol = (
            "blink::bindings::CallbackInvokeHelper<blink::CallbackBase, "
            "v8::Value>::Call(v8::Local<v8::Value>)"
        )
        self.assertEqual(
            "blink::bindings::CallbackInvokeHelper<…>",
            MODULE.class_area(symbol),
        )

    def test_engine_boundary_blocks_outer_blink_attribution(self):
        lines = sample(
            10,
            1.0,
            10,
            [
                "blink::Inner::Leaf()",
                "Builtins_CallApiCallbackGeneric",
                "v8::internal::Execute()",
                "blink::Outer::Call()",
            ],
        )
        parsed = MODULE.parse_perf_script(lines, "story")
        aggregates = MODULE.aggregate_samples(parsed)
        inner = aggregates[("function", "blink::Inner::Leaf()")]
        outer = aggregates[("function", "blink::Outer::Call()")]
        self.assertEqual(0b1, inner.sample_mask)
        self.assertEqual(0b1, inner.owner_exclusive_mask)
        self.assertEqual(0b1, outer.sample_mask)
        self.assertEqual(0, outer.owner_exclusive_mask)

    def test_parent_opportunity_includes_descendant_v8_cycles(self):
        lines = sample(
            10,
            1.0,
            100,
            [
                "JS:applicationWork app.js:1:1",
                "v8::internal::Execution::Call()",
                "blink::Document::Shutdown()",
            ],
        )
        parsed = MODULE.parse_perf_script(lines, "story")
        aggregates = MODULE.aggregate_samples(parsed)
        candidate = MODULE.make_candidate(
            aggregates[("function", "blink::Document::Shutdown()")],
            parsed,
            total_weight=100,
            group_totals=MODULE.collections.Counter(story=100),
            uncovered=0b1,
        )
        self.assertEqual(1.0, candidate["inclusive_share"])
        self.assertEqual(0.0, candidate["owner_exclusive_share"])
        frontier, _, _ = MODULE.build_frontier(
            parsed,
            aggregates,
            min_share=0.01,
            min_marginal_share=0.01,
            limit=10,
            include=MODULE.DEFAULT_INCLUDE,
            exclude=MODULE.DEFAULT_EXCLUDE,
        )
        self.assertIn(
            "blink::Document::Shutdown()",
            {item["name"] for item in frontier},
        )


class PerStoryDecompositionTest(unittest.TestCase):
    def make_sample(self, group, weight=10):
        return MODULE.Sample(
            group=group, comm="chrome", pid=1, tid=1, timestamp=1.0,
            weight=weight, frames=(),
        )

    def test_sample_story_extracts_suite_from_interval_group(self):
        self.assertEqual(
            "Charts-chartjs",
            MODULE.sample_story(
                self.make_sample("perf:cb/browser.log|Charts-chartjs")
            ),
        )
        self.assertIsNone(MODULE.sample_story(self.make_sample("perf")))

    def test_qualify_report_story_namespaces_every_frontier_identity(self):
        report = {
            "frontier": [{"entry_key": "function:blink::Hot", "name": "x"}],
            "overlapping_alternatives": [{
                "entry_key": "symbol:blink::Shared",
                "assigned_frontier_entry": "function:blink::Hot",
            }],
            "area_inventory": [{"entry_key": "class:blink::Hot"}],
            "selection": {"metric_weighting": "speedometer-geomean-v1"},
        }
        MODULE.qualify_report_story(report, "TodoMVC-jQuery")
        self.assertEqual(
            "story:TodoMVC-jQuery/function:blink::Hot",
            report["frontier"][0]["entry_key"],
        )
        alternative = report["overlapping_alternatives"][0]
        self.assertEqual(
            "story:TodoMVC-jQuery/symbol:blink::Shared",
            alternative["entry_key"],
        )
        self.assertEqual(
            "story:TodoMVC-jQuery/function:blink::Hot",
            alternative["assigned_frontier_entry"],
        )
        self.assertEqual(
            "story:TodoMVC-jQuery/class:blink::Hot",
            report["area_inventory"][0]["entry_key"],
        )
        self.assertEqual(
            "speedometer-story-v1", report["selection"]["metric_weighting"]
        )
        self.assertEqual("TodoMVC-jQuery", report["selection"]["story"])


if __name__ == "__main__":
    unittest.main()
