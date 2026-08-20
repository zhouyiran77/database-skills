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
from pg_pk_model import IdValue, RunOptions, ScanRequest  # noqa: E402
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
    batches: dict[tuple[str, str], tuple[tuple[IdValue, ...], ...]]

    def read_batches(self, request: ScanRequest) -> Iterator[tuple[IdValue, ...]]:
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


def _ids(*values: str) -> tuple[IdValue, ...]:
    return tuple(IdValue(value) for value in values)


if __name__ == "__main__":
    unittest.main()
