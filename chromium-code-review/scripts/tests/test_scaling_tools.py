from __future__ import annotations

import csv
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
PROFILE = SCRIPTS / "profile-review.py"
INDEXES = SCRIPTS / "build-review-indexes.py"
REFRESH = SCRIPTS / "refresh-delivery-gate.py"


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class ProfileReviewTest(unittest.TestCase):
    def make_review(self, base_files: dict[str, str], changed_files: dict[str, str]) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        repo = root / "repo"
        review = root / "review"
        repo.mkdir()
        review.mkdir()
        run("git", "init", "-q", str(repo))
        run("git", "-C", str(repo), "config", "user.email", "test@example.com")
        run("git", "-C", str(repo), "config", "user.name", "Test")
        for name, content in base_files.items():
            write(repo / name, content)
        run("git", "-C", str(repo), "add", ".")
        run("git", "-C", str(repo), "commit", "-qm", "base")
        parent = run("git", "-C", str(repo), "rev-parse", "HEAD").stdout.strip()
        for name, content in changed_files.items():
            write(repo / name, content)
        run("git", "-C", str(repo), "add", ".")
        run("git", "-C", str(repo), "commit", "-qm", "change")
        revision = run("git", "-C", str(repo), "rev-parse", "HEAD").stdout.strip()
        write(
            review / "pin.md",
            f"- Revision SHA: {revision}\n- Parent SHA: {parent}\n- Worktree: {repo} (rev-parse verified)\n",
        )
        return temporary, review

    def write_detail(self, review: Path, message: str) -> None:
        pin = (review / "pin.md").read_text(encoding="utf-8")
        revision = next(
            line.split(":", 1)[1].strip()
            for line in pin.splitlines() if line.startswith("- Revision SHA:")
        )
        write(
            review / "detail.json",
            json.dumps({"revisions": {revision: {"commit": {"message": message}}}}),
        )

    def test_docs_only_change_is_conservatively_micro(self) -> None:
        temporary, review = self.make_review({"docs/readme.md": "old\n"}, {"docs/readme.md": "old\nnew\n"})
        self.addCleanup(temporary.cleanup)
        write(
            review / "gerrit" / "unresolved-threads.json",
            ")]}'\n" + json.dumps({"summary": {"total_threads": 0, "unresolved_threads": 0, "malformed_entries": 0}}),
        )
        run("python3", str(PROFILE), str(review))
        profile = json.loads((review / "profile.json").read_text(encoding="utf-8"))
        self.assertEqual("micro", profile["effort"])
        self.assertTrue(profile["micro_eligibility"]["eligible"])
        self.assertEqual(1, profile["counts"]["files"])
        self.assertEqual("H0001", profile["hunks"][0]["id"])
        self.assertEqual("docs/readme.md", profile["hunks"][0]["path"])
        self.assertEqual(1, profile["hunks"][0]["new_count"])
        self.assertEqual({"files": 1, "changed_lines": 1}, profile["file_classes"]["docs"])
        self.assertIn("**micro**", (review / "profile.md").read_text(encoding="utf-8"))

    def test_small_async_production_change_is_high_risk(self) -> None:
        temporary, review = self.make_review(
            {"net/foo.cc": "void Run() {}\n"},
            {"net/foo.cc": "void Run() { PostTask(BindOnce(&Done)); }\n"},
        )
        self.addCleanup(temporary.cleanup)
        result = run("python3", str(PROFILE), str(review), "--stdout")
        profile = json.loads(result.stdout)
        self.assertEqual("high-risk", profile["effort"])
        self.assertIn("async_or_lifecycle", profile["risk_signals"])
        self.assertFalse((review / "profile.json").exists())

    def test_trigger_only_specialist_files_route_without_high_risk_escalation(self) -> None:
        temporary, review = self.make_review(
            {
                "ui/strings/app.grd": "<grit><message name=\"IDS_APP_NAME\"/></grit>\n",
                "android/Foo.java": "class Foo {}\n",
                "tools/metrics/histograms.xml": "<histograms></histograms>\n",
                "net/plain.cc": "int Value() { return 1; }\n",
            },
            {
                "ui/strings/app.grd": "<grit><message name=\"IDS_APP_NAME\">App</message></grit>\n",
                "android/Foo.java": "class Foo { int value = 1; }\n",
                "tools/metrics/histograms.xml": "<histograms><variants/></histograms>\n",
                "net/plain.cc": "int Value(const ResourceRequest&) { return 2; }\n",
            },
        )
        self.addCleanup(temporary.cleanup)
        profile = json.loads(run("python3", str(PROFILE), str(review), "--stdout").stdout)
        self.assertEqual("standard", profile["effort"])
        triggers = {item["prefix"]: item for item in profile["specialist_triggers"]}
        self.assertTrue({"PLS", "BAG", "PAT", "AXI", "NET"}.issubset(triggers))
        self.assertEqual("Build API And Generated Assets", triggers["BAG"]["roster_entry"])
        self.assertNotIn("build_or_dependency", profile["effort_reasons"])

    def test_blink_and_net_paths_alone_do_not_overroute_specialists(self) -> None:
        temporary, review = self.make_review(
            {
                "third_party/blink/renderer/platform/plain.cc": "int Value() { return 1; }\n",
                "net/plain.cc": "int Other() { return 1; }\n",
            },
            {
                "third_party/blink/renderer/platform/plain.cc": "int Value() { return 2; }\n",
                "net/plain.cc": "int Other() { return 2; }\n",
            },
        )
        self.addCleanup(temporary.cleanup)
        profile = json.loads(run("python3", str(PROFILE), str(review), "--stdout").stdout)
        prefixes = {item["prefix"] for item in profile["specialist_triggers"]}
        self.assertNotIn("OBL", prefixes)
        self.assertNotIn("NET", prefixes)

    def test_behavior_sensitive_specialists_route_and_escalate(self) -> None:
        temporary, review = self.make_review(
            {"third_party/blink/renderer/core/foo.h": "class Foo {};\n"},
            {
                "third_party/blink/renderer/core/foo.h": (
                    "class Foo {\n"
                    "  std::atomic<int> generation_;\n"
                    "  Member<Node> child_;\n"
                    "};\n"
                )
            },
        )
        self.addCleanup(temporary.cleanup)
        profile = json.loads(run("python3", str(PROFILE), str(review), "--stdout").stdout)
        self.assertEqual("high-risk", profile["effort"])
        prefixes = {item["prefix"] for item in profile["specialist_triggers"]}
        self.assertTrue({"TSY", "OBL"}.issubset(prefixes))
        self.assertIn("threading_or_concurrency", profile["risk_signals"])
        self.assertIn("ownership_or_gc_lifecycle", profile["risk_signals"])

    def test_mojom_and_focused_correctness_recipes_are_routed(self) -> None:
        temporary, review = self.make_review(
            {
                "services/example/public/mojom/store.mojom": "interface Store {};\n",
                "components/example/value.cc": "void Update() {}\n",
            },
            {
                "services/example/public/mojom/store.mojom": (
                    "[MinVersion=1] interface Store { Put(string key); };\n"
                ),
                "components/example/value.cc": (
                    "void Update() { CopyFrom(other); values.try_emplace(key, value); }\n"
                ),
            },
        )
        self.addCleanup(temporary.cleanup)
        profile = json.loads(run("python3", str(PROFILE), str(review), "--stdout").stdout)
        self.assertEqual("high-risk", profile["effort"])
        prefixes = {item["prefix"] for item in profile["specialist_triggers"]}
        self.assertTrue({"MIS", "FPM", "ACS"}.issubset(prefixes))
        self.assertIn("persistence_or_wire_format", profile["risk_signals"])

    def test_performance_and_fuzzing_specialists_are_routed(self) -> None:
        temporary, review = self.make_review(
            {"components/example/parser_fuzzer.cc": "int Parse() { return 0; }\n"},
            {
                "components/example/parser_fuzzer.cc": (
                    "int LLVMFuzzerTestOneInput() {\n"
                    "  // Benchmark latency and allocations under adversarial input.\n"
                    "  return Parse();\n"
                    "}\n"
                )
            },
        )
        self.addCleanup(temporary.cleanup)
        profile = json.loads(run("python3", str(PROFILE), str(review), "--stdout").stdout)
        prefixes = {item["prefix"] for item in profile["specialist_triggers"]}
        self.assertTrue({"PRS", "FTS"}.issubset(prefixes))
        self.assertIn("performance_or_memory", profile["risk_signals"])

    def test_specialist_prefixes_and_roster_names_are_canonical(self) -> None:
        temporary, review = self.make_review(
            {"components/example/all_lenses.cc": "void Before() {}\n"},
            {
                "components/example/all_lenses.cc": (
                    "void After() {\n"
                    "  std::atomic<int> generation; Member<Node> child;\n"
                    "  mojo::ReceiverSet<Api> receivers;  // MinVersion\n"
                    "  // benchmark allocations BUILDFLAG COMPONENT_EXPORT\n"
                    "  // UmaHistogram AXRole CORS LLVMFuzzerTestOneInput\n"
                    "  CopyFrom(other); std::map<int, int> values;\n"
                    "}\n"
                )
            },
        )
        self.addCleanup(temporary.cleanup)
        profile = json.loads(run("python3", str(PROFILE), str(review), "--stdout").stdout)
        self.assertEqual(
            {
                "FPM": "Field Propagation Matrix",
                "ACS": "Associative Container Semantics",
                "TSY": "Threading And Synchronization",
                "OBL": "Ownership And Blink Lifecycle",
                "MIS": "Mojo IPC Authorization And Sandbox",
                "PRS": "Performance And Resource Scaling",
                "PLS": "Platform And Language Semantics",
                "BAG": "Build API And Generated Assets",
                "PAT": "Privacy And Telemetry",
                "AXI": "Accessibility And Internationalization",
                "NET": "Network Semantics",
                "FTS": "Fuzzing And Test Strategy",
            },
            {
                item["prefix"]: item["roster_entry"]
                for item in profile["specialist_triggers"]
            },
        )

    def test_build_languages_proto_and_mojom_route_to_pls_and_bag(self) -> None:
        for extension in ("gn", "gni", "proto", "mojom"):
            with self.subTest(extension=extension):
                path = f"components/example/schema.{extension}"
                temporary, review = self.make_review(
                    {path: "old_value\n"},
                    {path: "new_value\n"},
                )
                self.addCleanup(temporary.cleanup)
                profile = json.loads(
                    run("python3", str(PROFILE), str(review), "--stdout").stdout
                )
                prefixes = {
                    item["prefix"] for item in profile["specialist_triggers"]
                }
                self.assertTrue({"PLS", "BAG"}.issubset(prefixes))

    def test_executable_file_under_docs_is_not_micro(self) -> None:
        temporary, review = self.make_review(
            {"docs/README.py": "print('old')\n"},
            {"docs/README.py": "print('new')\n"},
        )
        self.addCleanup(temporary.cleanup)
        profile = json.loads(run("python3", str(PROFILE), str(review), "--stdout").stdout)
        self.assertEqual("standard", profile["effort"])
        self.assertEqual("production", profile["files"][0]["class"])

    def test_external_context_is_reported_and_blocks_only_context_fast_path(self) -> None:
        temporary, review = self.make_review({"README.md": "old\n"}, {"README.md": "new\n"})
        self.addCleanup(temporary.cleanup)
        self.write_detail(
            review,
            "Docs update\n\nDesign: https://example.com/design\nBug: chromium:12345\n",
        )
        profile = json.loads(run("python3", str(PROFILE), str(review), "--stdout").stdout)
        self.assertEqual("micro", profile["effort"])
        self.assertGreater(profile["prior_context"]["external_context"]["count"], 0)
        self.assertFalse(profile["context_fast_path_eligible"])

    def test_link_free_pinned_description_allows_micro_context_fast_path(self) -> None:
        temporary, review = self.make_review({"README.md": "old\n"}, {"README.md": "new\n"})
        self.addCleanup(temporary.cleanup)
        self.write_detail(review, "Docs update only\n\nBug: None\n")
        profile = json.loads(run("python3", str(PROFILE), str(review), "--stdout").stdout)
        self.assertEqual(0, profile["prior_context"]["external_context"]["count"])
        self.assertTrue(profile["context_fast_path_eligible"])

    def test_unresolved_thread_blocks_micro(self) -> None:
        temporary, review = self.make_review({"README.md": "old\n"}, {"README.md": "new\n"})
        self.addCleanup(temporary.cleanup)
        write(
            review / "gerrit" / "unresolved-threads.json",
            json.dumps({"summary": {"total_threads": 1, "unresolved_threads": 1, "malformed_entries": 0}}),
        )
        profile = json.loads(run("python3", str(PROFILE), str(review), "--stdout").stdout)
        self.assertEqual("standard", profile["effort"])
        self.assertIn("no unresolved Gerrit threads", profile["micro_eligibility"]["failed"])

    def test_risky_test_only_change_is_high_risk(self) -> None:
        temporary, review = self.make_review(
            {"net/foo_unittest.cc": "TEST(Foo, Runs) {}\n"},
            {"net/foo_unittest.cc": "TEST(Foo, Runs) { PostTask(BindOnce(&Done)); }\n"},
        )
        self.addCleanup(temporary.cleanup)
        profile = json.loads(run("python3", str(PROFILE), str(review), "--stdout").stdout)
        self.assertEqual("high-risk", profile["effort"])
        self.assertIn("async_or_lifecycle", profile["risk_signals"])

    def test_plain_test_only_change_is_not_micro(self) -> None:
        temporary, review = self.make_review(
            {"net/foo_unittest.cc": "TEST(Foo, Runs) {}\n"},
            {"net/foo_unittest.cc": "TEST(Foo, Runs) { EXPECT_TRUE(true); }\n"},
        )
        self.addCleanup(temporary.cleanup)
        profile = json.loads(run("python3", str(PROFILE), str(review), "--stdout").stdout)
        self.assertEqual("standard", profile["effort"])
        self.assertIn(
            "all files are documentation or non-executable metadata",
            profile["micro_eligibility"]["failed"],
        )

    def test_context_budget_and_check_mode(self) -> None:
        temporary, review = self.make_review({"README.md": "old\n"}, {"README.md": "new\n"})
        self.addCleanup(temporary.cleanup)
        run("python3", str(PROFILE), str(review), "--context-window-tokens", "100000")
        profile = json.loads((review / "profile.json").read_text(encoding="utf-8"))
        self.assertEqual(140000, profile["context_budget"]["worker_input_budget_bytes"])
        checked = run("python3", str(PROFILE), str(review), "--check")
        self.assertIn("current:", checked.stdout)
        write(review / "profile.md", "stale\n")
        stale = run(
            "python3", str(PROFILE), str(review), "--context-window-tokens", "100000", "--check",
            check=False,
        )
        self.assertNotEqual(0, stale.returncode)

    def test_mismatched_worktree_pin_fails(self) -> None:
        temporary, review = self.make_review({"README.md": "old\n"}, {"README.md": "new\n"})
        self.addCleanup(temporary.cleanup)
        pin = (review / "pin.md").read_text(encoding="utf-8")
        write(review / "pin.md", pin.replace("Revision SHA: ", "Revision SHA: " + "0" * 40 + "\n- Ignored: ", 1))
        result = run("python3", str(PROFILE), str(review), check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("worktree HEAD does not match", result.stderr)

    def test_dense_single_file_change_is_large(self) -> None:
        temporary, review = self.make_review(
            {"foo.cc": "int value = 0;\n"},
            {"foo.cc": "".join(f"int value_{number} = {number};\n" for number in range(1502))},
        )
        self.addCleanup(temporary.cleanup)
        profile = json.loads(run("python3", str(PROFILE), str(review), "--stdout").stdout)
        self.assertEqual("large", profile["effort"])
        self.assertGreater(profile["counts"]["max_changed_lines_in_one_file"], 1500)
        self.assertGreater(profile["counts"]["changed_lines_per_hunk"], 1000)


class BuildReviewIndexesTest(unittest.TestCase):
    def make_review(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        write(
            root / "inventory.md",
            """# Inventory

## Changed surfaces

| surface | contract source | callers | old → new behavior | state / lifetime | tests | reachability | scope label |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Foo::Run (foo.cc:10) | foo.h:5 | caller | old to new | pending_ | foo_test.cc:4 | production | core |

## Risk-area map

| file | risk areas |
| --- | --- |
| foo.cc | async/lifecycle |

## Trigger inventory

| scope ID | surface | discovery triggers | root-cause trigger | evidence |
| --- | --- | --- | --- | --- |
| T001 | Foo state | CTL, SMM | required: async | foo.cc:10 |
| T002 | No trust boundary | STB | not required: token scan empty | profile.json:/risk_signals |
""",
        )
        write(
            root / "ledger" / "EPW.md",
            """# EPW

## Candidate rows

| id | claim | location | evidence / hypothesis | origin | severity | status |
| --- | --- | --- | --- | --- | --- | --- |
| EPW-1 | loses callback | foo.cc:11 | trace at foo.cc:11 and caller.cc:20 | CL-introduced | P1 | candidate |

## Amendments

| amendment | target | operation | replacement / reason | evidence | attempt |
| --- | --- | --- | --- | --- | --- |
| EPW-A1 | EPW-1 | replace | corrected trace | foo.cc:12 | 2 |
""",
        )
        write(
            root / "verification" / "V001.md",
            """# Verdict

| id | candidate | verdict | evidence | severity (anchor) | origin |
| --- | --- | --- | --- | --- | --- |
| V001-1 | EPW-1 | CONFIRMED | trace foo.cc:11 to caller.cc:20 | P1 (anchor) | CL-introduced |
""",
        )
        write(
            root / "reconciliation.md",
            """# Reconciliation

| row | thread | disposition |
| --- | --- | --- |
| EPW-1 | Error Path | promoted F001 via V001-1 at foo.cc:11 |
""",
        )
        write(
            root / "root-cause" / "RC001.md",
            """# Root cause

## RC001-1 (for EPW-1 / V001-1)

- Symptom: callback is lost at foo.cc:11.
""",
        )
        return temporary, root

    def read_tsv(self, path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source, delimiter="\t"))

    def test_builds_four_sorted_compact_indexes(self) -> None:
        temporary, root = self.make_review()
        self.addCleanup(temporary.cleanup)
        result = run("python3", str(INDEXES), str(root))
        self.assertIn("candidates.tsv=1", result.stdout)
        inventory = self.read_tsv(root / "indexes" / "inventory.tsv")
        self.assertEqual(
            ["risk", "surface", "trigger", "trigger"],
            [row["kind"] for row in inventory],
        )
        surface = next(row for row in inventory if row["kind"] == "surface")
        self.assertEqual("S0001", surface["id"])
        trigger = next(row for row in inventory if row["kind"] == "trigger")
        self.assertIn("root-cause-required=yes", trigger["tags"])
        trigger_two = next(row for row in inventory if row["id"] == "T002")
        self.assertEqual("profile.json:/risk_signals", trigger_two["citations"])
        self.assertIn("root-cause-required=no", trigger_two["tags"])
        candidates = self.read_tsv(root / "indexes" / "candidates.tsv")
        self.assertEqual("EPW-1", candidates[0]["id"])
        self.assertEqual("foo.cc:11,caller.cc:20,foo.cc:12", candidates[0]["citations"])
        self.assertEqual("replace by EPW-A1", candidates[0]["status"])
        verdicts = self.read_tsv(root / "indexes" / "verdicts.tsv")
        self.assertEqual("CONFIRMED", verdicts[0]["verdict"])
        reconciliation = self.read_tsv(root / "indexes" / "reconciliation.tsv")
        self.assertEqual("EPW-1", reconciliation[0]["row"])
        by_row = {row["row"]: row for row in reconciliation}
        self.assertEqual("EPW-A1:replace", by_row["EPW-1"]["effective_amendment"])
        self.assertEqual("pending", by_row["V001-1"]["disposition_state"])
        self.assertEqual("pending", by_row["RC001-1"]["disposition_state"])
        self.assertEqual("EPW-1,RC001-1", by_row["V001-1"]["links"])
        manifest = json.loads((root / "indexes" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(1, manifest["indexes"]["candidates.tsv"]["row_count"])
        self.assertEqual("ledger/EPW.md", manifest["indexes"]["candidates.tsv"]["sources"][0]["path"])
        self.assertEqual(64, len(manifest["indexes"]["candidates.tsv"]["output_sha256"]))
        self.assertIn("current:", run("python3", str(INDEXES), str(root), "--check").stdout)

    def test_duplicate_candidate_fails_without_replacing_existing_index(self) -> None:
        temporary, root = self.make_review()
        self.addCleanup(temporary.cleanup)
        run("python3", str(INDEXES), str(root))
        old = (root / "indexes" / "candidates.tsv").read_text(encoding="utf-8")
        write(root / "ledger" / "OTHER.md", (root / "ledger" / "EPW.md").read_text(encoding="utf-8"))
        result = run("python3", str(INDEXES), str(root), check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("duplicate candidate ID EPW-1", result.stderr)
        self.assertEqual(old, (root / "indexes" / "candidates.tsv").read_text(encoding="utf-8"))

    def test_escaped_pipe_is_preserved_in_candidate_index(self) -> None:
        temporary, root = self.make_review()
        self.addCleanup(temporary.cleanup)
        ledger = root / "ledger" / "EPW.md"
        write(
            ledger,
            ledger.read_text(encoding="utf-8").replace(
                "loses callback", r"loses callback A \| B"
            ),
        )
        run("python3", str(INDEXES), str(root))
        candidates = self.read_tsv(root / "indexes" / "candidates.tsv")
        self.assertEqual("loses callback A | B", candidates[0]["claim"])

    def test_malformed_table_row_is_fatal(self) -> None:
        temporary, root = self.make_review()
        self.addCleanup(temporary.cleanup)
        ledger = root / "ledger" / "EPW.md"
        write(
            ledger,
            ledger.read_text(encoding="utf-8").replace(
                "loses callback", "loses callback A | B"
            ),
        )
        result = run("python3", str(INDEXES), str(root), check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("ledger/EPW.md", result.stderr)
        self.assertIn("malformed Markdown table row", result.stderr)

    def test_merge_proposal_is_a_fingerprinted_bidirectional_closure_edge(self) -> None:
        temporary, root = self.make_review()
        self.addCleanup(temporary.cleanup)
        write(
            root / "ledger" / "AL.md",
            """# AL

## Candidate rows

| id | claim | location | evidence / hypothesis | origin | severity | status |
| --- | --- | --- | --- | --- | --- | --- |
| AL-1 | duplicate callback loss | foo.cc:11 | same trace at foo.cc:11 | CL-introduced | P1 | candidate |
""",
        )
        write(
            root / "verification" / "batches.md",
            """# Verification batches

## Merge proposals

| row | proposal |
| --- | --- |
| AL-1 | merge-into EPW-1: same trigger, invariant, and outcome |
""",
        )
        run("python3", str(INDEXES), str(root))
        rows = {
            row["row"]: row
            for row in self.read_tsv(root / "indexes" / "reconciliation.tsv")
        }
        self.assertIn("EPW-1", rows["AL-1"]["links"].split(","))
        self.assertIn("AL-1", rows["EPW-1"]["links"].split(","))
        manifest = json.loads((root / "indexes" / "manifest.json").read_text(encoding="utf-8"))
        sources = {
            source["path"]
            for source in manifest["indexes"]["reconciliation.tsv"]["sources"]
        }
        self.assertIn("verification/batches.md", sources)

    def test_clean_candidate_table_row_is_not_a_verification_candidate(self) -> None:
        temporary, root = self.make_review()
        self.addCleanup(temporary.cleanup)
        ledger = root / "ledger" / "EPW.md"
        ledger.write_text(
            ledger.read_text(encoding="utf-8").replace(
                "| CL-introduced | P1 | candidate |",
                "| CL-introduced | P1 | clean (cited) |",
            ),
            encoding="utf-8",
        )
        run("python3", str(INDEXES), str(root))
        self.assertEqual([], self.read_tsv(root / "indexes" / "candidates.tsv"))

    def test_duplicate_inventory_id_fails(self) -> None:
        temporary, root = self.make_review()
        self.addCleanup(temporary.cleanup)
        write(
            root / "inventory" / "I002.md",
            """# Inventory shard

## Trigger inventory

| scope ID | surface | discovery triggers | root-cause trigger | evidence |
| --- | --- | --- | --- | --- |
| T001 | duplicate | EPW | not required: none | foo.cc:12 |
""",
        )
        result = run("python3", str(INDEXES), str(root), check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("duplicate inventory ID T001", result.stderr)

    def test_sharded_trigger_id_is_preserved_in_compact_index(self) -> None:
        temporary, root = self.make_review()
        self.addCleanup(temporary.cleanup)
        inventory = root / "inventory.md"
        inventory.write_text(
            inventory.read_text(encoding="utf-8").replace("T002", "I2-T002"),
            encoding="utf-8",
        )
        run("python3", str(INDEXES), str(root))
        triggers = {
            row["id"] for row in self.read_tsv(root / "indexes" / "inventory.tsv")
            if row["kind"] == "trigger"
        }
        self.assertIn("I2-T002", triggers)

    def test_check_detects_changed_source_even_when_rows_are_unchanged(self) -> None:
        temporary, root = self.make_review()
        self.addCleanup(temporary.cleanup)
        run("python3", str(INDEXES), str(root))
        with (root / "ledger" / "EPW.md").open("a", encoding="utf-8") as output:
            output.write("\nnon-table note\n")
        result = run("python3", str(INDEXES), str(root), "--check", check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("manifest.json", result.stderr)


class RefreshDeliveryGateTest(unittest.TestCase):
    PINNED = "1" * 40
    CURRENT = "2" * 40

    def make_review(self, historical: bool = False) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        write(
            root / "pin.md",
            f"# CL 12345 — patchset 3 pin\n\n- Pinned patchset: 3\n- Revision SHA: {self.PINNED}\n",
        )
        write(root / "directives.md", f"- Mode: {'historical patchset' if historical else 'full review'}\n")
        write(root / "draft-review.md", f"- Draft revision: 2\n- Pinned: {self.PINNED}\n")
        write(root / "challenge.md", "- Current: challenge/round-2/index.md\n")
        write(
            root / "challenge" / "round-2" / "index.md",
            "- Draft revision: 2\n- Result: pass\n",
        )
        write(
            root / "reconciliation.md",
            "before\n2. **Freshness:** pending-delivery\nafter\n",
        )
        return temporary, root

    def detail(self, current: bool = True) -> bytes:
        current_sha = self.PINNED if current else self.CURRENT
        value = {
            "current_revision": current_sha,
            "revisions": {
                self.PINNED: {"_number": 3},
                self.CURRENT: {"_number": 4},
            },
        }
        return (")]}'\n" + json.dumps(value)).encode()

    def test_current_refresh_is_affirmative_and_changes_only_freshness(self) -> None:
        temporary, root = self.make_review()
        self.addCleanup(temporary.cleanup)
        (root / "detail-refresh.json").write_bytes(self.detail(current=True))
        before = (root / "reconciliation.md").read_text(encoding="utf-8")
        result = run(
            "python3", str(REFRESH), str(root), "--detail-json", str(root / "detail-refresh.json"),
            "--checked-at", "2026-07-21T12:00:00Z",
        )
        self.assertIn("current: yes", result.stdout)
        gate = (root / "delivery-gate.md").read_text(encoding="utf-8")
        self.assertIn("- Result: current", gate)
        self.assertIn("- Gate line: yes", gate)
        after = (root / "reconciliation.md").read_text(encoding="utf-8")
        self.assertEqual(before.splitlines()[0], after.splitlines()[0])
        self.assertEqual(before.splitlines()[2], after.splitlines()[2])
        self.assertIn("yes — current; delivery-gate.md", after)

    def test_historical_pin_mapping_is_accepted_without_chasing_current(self) -> None:
        temporary, root = self.make_review(historical=True)
        self.addCleanup(temporary.cleanup)
        (root / "detail-refresh.json").write_bytes(self.detail(current=False))
        result = run(
            "python3", str(REFRESH), str(root), "--detail-json", str(root / "detail-refresh.json"),
            "--checked-at", "2026-07-21T12:00:00Z",
        )
        self.assertIn("historical pin verified: yes", result.stdout)
        self.assertIn("- Gerrit current: PS4", (root / "delivery-gate.md").read_text(encoding="utf-8"))

    def test_newer_patchset_is_never_inferred_trivial(self) -> None:
        temporary, root = self.make_review()
        self.addCleanup(temporary.cleanup)
        (root / "detail-refresh.json").write_bytes(self.detail(current=False))
        before = (root / "reconciliation.md").read_text(encoding="utf-8")
        result = run(
            "python3", str(REFRESH), str(root), "--detail-json", str(root / "detail-refresh.json"),
            "--checked-at", "2026-07-21T12:00:00Z", check=False,
        )
        self.assertEqual(2, result.returncode)
        gate = (root / "delivery-gate.md").read_text(encoding="utf-8")
        self.assertIn("- Result: newer patchset", gate)
        self.assertIn("- Gate line: no", gate)
        self.assertNotIn("trivial delta verified", gate)
        self.assertEqual(before, (root / "reconciliation.md").read_text(encoding="utf-8"))

    def test_existing_revalidated_trivial_delta_requires_explicit_acceptance(self) -> None:
        temporary, root = self.make_review()
        self.addCleanup(temporary.cleanup)
        detail = root / "detail-refresh.json"
        detail.write_bytes(self.detail(current=False))
        write(
            root / "patchset-delta.md",
            f"- Reviewed pin: PS3 {self.PINNED}\n"
            f"- Inspected Gerrit current: PS4 {self.CURRENT}\n"
            "- Classification: trivial\n"
            "- Cited-line revalidation: every cited line is unchanged\n"
            "- Conclusion revalidation: all conclusions remain valid\n",
        )
        rejected = run(
            "python3", str(REFRESH), str(root), "--detail-json", str(detail),
            "--checked-at", "2026-07-21T12:00:00Z", check=False,
        )
        self.assertEqual(2, rejected.returncode)
        self.assertIn("newer patchset", rejected.stdout)
        write(
            root / "draft-review.md",
            f"- Draft revision: 2\n- Reviewed pin: {self.PINNED}\n"
            f"- Inspected Gerrit current: PS4 {self.CURRENT}\n",
        )
        accepted = run(
            "python3", str(REFRESH), str(root), "--detail-json", str(detail),
            "--checked-at", "2026-07-21T12:01:00Z", "--accept-proven-trivial-delta",
        )
        self.assertIn("trivial delta verified: yes", accepted.stdout)

    def test_invalid_refresh_writes_fetch_failed_without_reconciliation_change(self) -> None:
        temporary, root = self.make_review()
        self.addCleanup(temporary.cleanup)
        write(root / "detail-refresh.json", "not json\n")
        before = (root / "reconciliation.md").read_text(encoding="utf-8")
        result = run(
            "python3", str(REFRESH), str(root), "--detail-json", str(root / "detail-refresh.json"),
            "--checked-at", "2026-07-21T12:00:00Z", check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("- Result: fetch failed", (root / "delivery-gate.md").read_text(encoding="utf-8"))
        self.assertEqual(before, (root / "reconciliation.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
