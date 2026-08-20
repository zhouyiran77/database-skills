from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from pg_pk_config import ConfigError, parse_markdown_config  # noqa: E402
from pg_pk_model import Role  # noqa: E402


VALID_CONFIG = """
# 数据库主键冲突检测配置

## 数据库实例

| instance_id | role | school | db_type | host | port | database | username | password_env | sslmode |
|---|---|---|---|---|---:|---|---|---|---|
| v2_huashi | source | 华师 | postgresql | pg-v2-1 | 5432 | teaching_v2 | audit | DB_V2_HUASHI_PASSWORD | require |
| v2_wut | source | 武汉理工 | postgresql | pg-v2-2 | 5432 | teaching_v2 | audit | DB_V2_WUT_PASSWORD | require |
| v2_gdei | source | 广东二师 | postgresql | pg-v2-3 | 5432 | teaching_v2 | audit | DB_V2_GDEI_PASSWORD | require |
| v3_main | target | 3.0合并库 | postgresql | pg-v3 | 5432 | teaching_v3 | audit | DB_V3_MAIN_PASSWORD | require |

## 表比对范围

| scope_id | enabled | source_instances | source_table | target_instance | target_table | primary_key |
|---|---|---|---|---|---|---|
| activity_nodes | true | v2_huashi,v2_wut | public.activity_nodes | v3_main | teaching.activity_node | id |
| activity_nodes | true | v2_gdei | legacy.activity_node | v3_main | teaching.activity_node | id |
| course | false | * | public.course | v3_main | teaching.courses | id |
"""


class MarkdownConfigTests(unittest.TestCase):
    def test_parse_markdown_config_merges_rows_for_same_logical_table(self) -> None:
        # Given a Markdown config whose source table differs for one school.
        markdown = VALID_CONFIG

        # When the configuration is parsed.
        config = parse_markdown_config(markdown)

        # Then enabled rows with the same scope are merged without losing mappings.
        self.assertEqual(len(config.instances), 4)
        self.assertEqual(len(config.scopes), 1)
        scope = config.scopes[0]
        self.assertEqual(scope.scope_id, "activity_nodes")
        self.assertEqual(scope.target_table.label(), "teaching.activity_node")
        self.assertEqual(
            tuple((binding.instance_id, binding.table.label()) for binding in scope.sources),
            (
                ("v2_huashi", "public.activity_nodes"),
                ("v2_wut", "public.activity_nodes"),
                ("v2_gdei", "legacy.activity_node"),
            ),
        )
        self.assertEqual(config.instance("v3_main").role, Role.TARGET)

    def test_parse_markdown_config_rejects_plaintext_password_column(self) -> None:
        # Given a database table that includes a plaintext password column.
        markdown = VALID_CONFIG.replace(
            "| instance_id | role | school | db_type | host | port | database | username | password_env | sslmode |",
            "| instance_id | role | school | db_type | host | port | database | username | password_env | sslmode | password |",
        ).replace(
            "|---|---|---|---|---|---:|---|---|---|---|",
            "|---|---|---|---|---|---:|---|---|---|---|---|",
        )

        # When parsing crosses the trust boundary, then plaintext secret columns are rejected.
        with self.assertRaisesRegex(ConfigError, "password_env"):
            parse_markdown_config(markdown)

    def test_parse_markdown_config_rejects_non_id_primary_key(self) -> None:
        # Given a scope that requests an unsupported primary-key column.
        markdown = VALID_CONFIG.replace("| id |", "| node_id |", 1)

        # When parsing crosses the trust boundary, then v1 rejects the unsupported key.
        with self.assertRaisesRegex(ConfigError, "primary_key.*id"):
            parse_markdown_config(markdown)


if __name__ == "__main__":
    unittest.main()
