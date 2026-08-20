from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
import sys
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from pg_pk_check import execute_check  # noqa: E402
from pg_pk_config import parse_markdown_config  # noqa: E402
from pg_pk_model import ComparisonValue, IdValue, Role, RunOptions, ScanRequest  # noqa: E402
from pg_pk_render import render_markdown  # noqa: E402


CONFIG = """
## 数据库实例

| instance_id | role | school | db_type | host | port | database | username | password_env | sslmode |
|---|---|---|---|---|---:|---|---|---|---|
| v2_huashi | source | 华师 | postgresql | pg-v2-1 | 5432 | teaching_v2 | audit | DB_V2_HUASHI_PASSWORD | require |
| v2_wut | source | 武汉理工 | postgresql | pg-v2-2 | 5432 | teaching_v2 | audit | DB_V2_WUT_PASSWORD | require |
| v3_main | target | 3.0合并库 | postgresql | pg-v3 | 5432 | teaching_v3 | audit | DB_V3_MAIN_PASSWORD | require |

## 表比对范围

| scope_id | enabled | source_instances | source_table | target_instance | target_table | primary_key |
|---|---|---|---|---|---|---|
| activity_nodes | true | * | public.activity_nodes | v3_main | teaching.activity_node | id |
"""


@dataclass(frozen=True, slots=True)
class FakeReader:
    batches: dict[tuple[str, str], tuple[tuple[ComparisonValue, ...], ...]]

    def read_batches(self, request: ScanRequest) -> Iterator[tuple[ComparisonValue, ...]]:
        return iter(self.batches[(request.instance.instance_id, request.table.label())])


@dataclass(frozen=True, slots=True)
class RecordingReader:
    batches: dict[
        tuple[str, str],
        tuple[tuple[ComparisonValue, ...], ...],
    ]
    calls: list[ScanRequest]
    reject_target: bool = False

    def read_batches(
        self,
        request: ScanRequest,
    ) -> Iterator[tuple[ComparisonValue, ...]]:
        self.calls.append(request)
        if self.reject_target and request.instance.role is Role.TARGET:
            raise AssertionError("source-only workflow requested a target")
        return iter(self.batches[(request.instance.instance_id, request.table.label())])


class CheckWorkflowTests(unittest.TestCase):
    def test_execute_check_drives_reader_store_and_markdown_report(self) -> None:
        # Given a parsed multi-instance scope and deterministic streamed ID batches.
        config = parse_markdown_config(CONFIG)
        reader = FakeReader(
            batches={
                ("v2_huashi", "public.activity_nodes"): ((_ids("1", "2")), (_ids("5"))),
                ("v2_wut", "public.activity_nodes"): ((_ids("2", "3")),),
                ("v3_main", "teaching.activity_node"): ((_ids("3", "5", "8")),),
            },
        )

        # When the complete check workflow runs and renders its user-facing report.
        report = execute_check(config, reader, RunOptions(batch_size=2, detail_limit=100))
        markdown = render_markdown(config, report)

        # Then both conflict dimensions and the physical table mappings are observable.
        self.assertTrue(report.has_conflicts())
        self.assertIn("| activity_nodes | 1 | 2 | 冲突 |", markdown)
        self.assertIn("| 2.0来源库之间 | 2 | v2_huashi, v2_wut | - |", markdown)
        self.assertIn("| 2.0与3.0 | 3 | v2_wut | v3_main |", markdown)
        self.assertIn("| v2_huashi | 华师 | source |", markdown)
        self.assertIn("teaching.activity_node", markdown)

    def test_execute_check_source_only_scans_only_configured_sources(self) -> None:
        # Given a source-only scope and a reader that rejects every target request.
        config = parse_markdown_config(SOURCE_ONLY_CONFIG)
        reader = RecordingReader(
            batches={
                ("v2_huashi", "public.activity_nodes"): ((_key("1"),),),
                ("v2_wut", "public.activity_nodes"): ((_key("1"),),),
            },
            calls=[],
            reject_target=True,
        )

        # When the source-only workflow runs.
        report = execute_check(config, reader, RunOptions(batch_size=10, detail_limit=10))

        # Then exactly the configured source aliases are requested and target output is absent.
        self.assertEqual(
            tuple((call.instance.instance_id, call.table.label()) for call in reader.calls),
            (("v2_huashi", "public.activity_nodes"), ("v2_wut", "public.activity_nodes")),
        )
        self.assertEqual(len(report.scan_counts), 2)
        self.assertIsNone(report.result("activity_nodes").target_instance)
        self.assertIsNone(report.result("activity_nodes").source_target)

    def test_render_source_only_report_marks_target_unchecked_and_formats_composite_keys(self) -> None:
        # Given a source-only composite-key report with Markdown-sensitive key components.
        config = parse_markdown_config(SOURCE_ONLY_COMPOSITE_CONFIG)
        reader = RecordingReader(
            batches={
                ("v2_huashi", "public.activity_nodes"): ((_key("a|b", "line\nvalue"),),),
                ("v2_wut", "public.activity_nodes"): ((_key("a|b", "line\nvalue"),),),
            },
            calls=[],
            reject_target=True,
        )
        report = execute_check(config, reader, RunOptions(batch_size=10, detail_limit=10))

        # When the source-only report is rendered.
        markdown = render_markdown(config, report)

        # Then unchecked target work is explicit and composite values stay readable and escaped.
        self.assertIn("| activity_nodes | 1 | 未检查 | 冲突 |", markdown)
        self.assertIn("(id=a\\|b, group_id=line value)", markdown)
        self.assertNotIn("| target |", markdown)
        detail_section = markdown.split("### 冲突明细", 1)[1]
        self.assertNotIn("| 2.0与3.0 |", detail_section)
        self.assertNotIn('["a|b","line\\nvalue"]', markdown)

    def test_render_source_only_report_marks_target_unchecked_and_formats_composite_keys(self) -> None:
        # Given a source-only composite-key report with Markdown-sensitive key components.
        config = parse_markdown_config(SOURCE_ONLY_COMPOSITE_CONFIG)
        reader = RecordingReader(
            batches={
                ("v2_huashi", "public.activity_nodes"): ((_key("a|b", "line\nvalue"),),),
                ("v2_wut", "public.activity_nodes"): ((_key("a|b", "line\nvalue"),),),
            },
            calls=[],
            reject_target=True,
        )
        report = execute_check(config, reader, RunOptions(batch_size=10, detail_limit=10))

        # When the source-only report is rendered.
        markdown = render_markdown(config, report)

        # Then unchecked target work is explicit and composite values stay readable and escaped.
        self.assertIn("| activity_nodes | 1 | 未检查 | 冲突 |", markdown)
        self.assertIn("(id=a\\|b, group_id=line value)", markdown)
        self.assertNotIn("| target |", markdown)
        detail_section = markdown.split("### 冲突明细", 1)[1]
        self.assertNotIn("| 2.0与3.0 |", detail_section)
        self.assertNotIn('["a|b","line\\nvalue"]', markdown)

    def test_execute_check_mixed_scopes_processes_source_only_and_target_modes(self) -> None:
        # Given one source-only scope and one legacy target scope in the same config.
        config = parse_markdown_config(MIXED_CONFIG)
        reader = RecordingReader(
            batches={
                ("v2_huashi", "public.activity_nodes"): ((_key("1", "a"),),),
                ("v2_wut", "public.activity_nodes"): ((_key("1", "a"),),),
                ("v2_huashi", "legacy.activity_nodes"): ((_key("9"),),),
                ("v3_main", "teaching.activity_node"): ((_key("9"),),),
            },
            calls=[],
        )

        # When both scopes are executed.
        report = execute_check(config, reader, RunOptions(batch_size=10, detail_limit=10))

        # Then source-only has no target result and target mode still reports its conflict.
        self.assertEqual(len(report.results), 2)
        self.assertIsNone(report.result("source_only").source_target)
        target_result = report.result("legacy_target")
        self.assertIsNotNone(target_result.source_target)
        assert target_result.source_target is not None
        self.assertEqual(target_result.source_target.total, 1)

    def test_execute_check_carries_ordered_tuple_keys_to_reader_and_store(self) -> None:
        # Given a source-only composite-key scope with a collision-safe tuple conflict.
        config = parse_markdown_config(SOURCE_ONLY_COMPOSITE_CONFIG)
        reader = RecordingReader(
            batches={
                ("v2_huashi", "public.activity_nodes"): (
                    (_key("1", "23"), _key("12", "3")),
                ),
                ("v2_wut", "public.activity_nodes"): ((_key("1", "23"),),),
            },
            calls=[],
            reject_target=True,
        )

        # When the composite-key workflow runs.
        report = execute_check(config, reader, RunOptions(batch_size=10, detail_limit=10))

        # Then key order reaches the reader and the full tuple reaches the conflict record.
        self.assertEqual(reader.calls[0].primary_key, ("id", "group_id"))
        result = report.result("activity_nodes")
        self.assertEqual(result.source_source.total, 1)
        self.assertEqual(result.source_source.records[0].id_value, ("1", "23"))

    def test_execute_check_target_mode_preserves_request_order_and_scan_counts(self) -> None:
        # Given the existing scalar target-mode scope and streamed row batches.
        config = parse_markdown_config(CONFIG)
        reader = RecordingReader(
            batches={
                ("v2_huashi", "public.activity_nodes"): ((_key("1"), _key("2")), (_key("5"),)),
                ("v2_wut", "public.activity_nodes"): ((_key("2"), _key("3")),),
                ("v3_main", "teaching.activity_node"): ((_key("3"), _key("5"), _key("8")),),
            },
            calls=[],
        )

        # When the legacy target-mode workflow runs.
        report = execute_check(config, reader, RunOptions(batch_size=2, detail_limit=100))

        # Then source requests precede the target request and row counts remain exact.
        self.assertEqual(
            tuple((call.instance.instance_id, call.table.label()) for call in reader.calls),
            (
                ("v2_huashi", "public.activity_nodes"),
                ("v2_wut", "public.activity_nodes"),
                ("v3_main", "teaching.activity_node"),
            ),
        )
        self.assertEqual(
            tuple((count.instance_id, count.rows) for count in report.scan_counts),
            (("v2_huashi", 3), ("v2_wut", 2), ("v3_main", 3)),
        )


def _ids(*values: str) -> tuple[IdValue, ...]:
    return tuple(IdValue(value) for value in values)


def _key(*values: str) -> tuple[IdValue, ...]:
    return tuple(IdValue(value) for value in values)


SOURCE_ONLY_CONFIG = CONFIG.replace(
    "| v3_main | target | 3.0合并库 | postgresql | pg-v3 | 5432 | teaching_v3 | audit | "
    "DB_V3_MAIN_PASSWORD | require |\n",
    "",
).replace(
    "| activity_nodes | true | * | public.activity_nodes | v3_main | teaching.activity_node | id |",
    "| activity_nodes | true | v2_huashi,v2_wut | public.activity_nodes |  |  | id |",
)
SOURCE_ONLY_COMPOSITE_CONFIG = SOURCE_ONLY_CONFIG.replace(
    "| activity_nodes | true | v2_huashi,v2_wut | public.activity_nodes |  |  | id |",
    "| activity_nodes | true | v2_huashi,v2_wut | public.activity_nodes |  |  | ( id, group_id ) |",
)
MIXED_CONFIG = CONFIG.replace(
    "| activity_nodes | true | * | public.activity_nodes | v3_main | teaching.activity_node | id |",
    "| source_only | true | v2_huashi,v2_wut | public.activity_nodes |  |  | ( id, group_id ) |\n"
    "| legacy_target | true | v2_huashi | legacy.activity_nodes | v3_main | teaching.activity_node | id |",
)


if __name__ == "__main__":
    unittest.main()
