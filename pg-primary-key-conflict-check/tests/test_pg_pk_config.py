from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from pg_pk_config import ConfigError, parse_markdown_config  # noqa: E402
from pg_pk_model import CheckConfig, ConflictDetails, Role, ScopeId, ScopeResult  # noqa: E402


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

TARGET_INSTANCE_ROW = (
    "| v3_main | target | 3.0合并库 | postgresql | pg-v3 | 5432 | teaching_v3 | audit | "
    "DB_V3_MAIN_PASSWORD | require |\n"
)
PRIMARY_SCOPE_ROW = (
    "| activity_nodes | true | v2_huashi,v2_wut | public.activity_nodes | v3_main | "
    "teaching.activity_node | id |"
)
SECONDARY_SCOPE_ROW = (
    "| activity_nodes | true | v2_gdei | legacy.activity_node | v3_main | "
    "teaching.activity_node | id |"
)


def _parse_valid_config(markdown: str) -> CheckConfig:
    try:
        config = parse_markdown_config(markdown)
    except ConfigError as exc:
        message = str(exc)
    else:
        return config
    raise AssertionError(f"expected valid config, got ConfigError: {message}")


def _config_error_message(markdown: str) -> str:
    try:
        parse_markdown_config(markdown)
    except ConfigError as exc:
        return str(exc)
    raise AssertionError("expected ConfigError")


class MarkdownConfigTests(unittest.TestCase):
    def test_parse_markdown_config_merges_rows_for_same_logical_table(self) -> None:
        # Given a Markdown config whose source table differs for one school.
        markdown = VALID_CONFIG

        # When the configuration is parsed.
        config = _parse_valid_config(markdown)

        # Then enabled rows with the same scope are merged without losing mappings.
        self.assertEqual(len(config.instances), 4)
        self.assertEqual(len(config.scopes), 1)
        scope = config.scopes[0]
        self.assertEqual(scope.scope_id, "activity_nodes")
        self.assertEqual(scope.target_instance, "v3_main")
        self.assertEqual(scope.target_table.label(), "teaching.activity_node")
        self.assertEqual(scope.primary_key, ("id",))
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

    def test_parse_markdown_config_normalizes_canonical_composite_key_in_order(self) -> None:
        # Given repeated scope rows with the same canonical composite key.
        markdown = VALID_CONFIG.replace(
            "teaching.activity_node | id |",
            "teaching.activity_node | id,group_id |",
        )

        # When the configuration is parsed.
        config = _parse_valid_config(markdown)

        # Then the comparison columns are an ordered tuple.
        self.assertEqual(config.scopes[0].primary_key, ("id", "group_id"))

    def test_parse_markdown_config_allows_source_only_parenthesized_composite_key(self) -> None:
        # Given two source bindings, no target instance row, and blank target cells.
        markdown = (
            VALID_CONFIG.replace(TARGET_INSTANCE_ROW, "")
            .replace(
                PRIMARY_SCOPE_ROW,
                "| activity_nodes | true | v2_huashi,v2_wut | public.activity_nodes |  |  | "
                "( id, group_id ) |",
            )
            .replace(
                SECONDARY_SCOPE_ROW,
                "| activity_nodes | true | v2_gdei | legacy.activity_node |  |  | "
                "( id, group_id ) |",
            )
        )

        # When the configuration is parsed.
        config = _parse_valid_config(markdown)

        # Then target omission and normalized key order are represented explicitly.
        scope = config.scopes[0]
        self.assertIsNone(scope.target_instance)
        self.assertIsNone(scope.target_table)
        self.assertEqual(scope.primary_key, ("id", "group_id"))

    def test_parse_markdown_config_rejects_half_empty_target_pair(self) -> None:
        # Given scopes with exactly one target cell populated.
        markdown_cases = (
            VALID_CONFIG.replace(
                PRIMARY_SCOPE_ROW,
                "| activity_nodes | true | v2_huashi,v2_wut | public.activity_nodes |  | "
                "teaching.activity_node | id |",
            ),
            VALID_CONFIG.replace(
                PRIMARY_SCOPE_ROW,
                "| activity_nodes | true | v2_huashi,v2_wut | public.activity_nodes | v3_main |  | id |",
            ),
        )

        # When each configuration crosses the parser boundary, then the pair contract is rejected.
        for markdown in markdown_cases:
            with self.subTest(markdown=markdown):
                self.assertRegex(
                    _config_error_message(markdown),
                    "target_instance.*target_table.*both.*empty",
                )

    def test_parse_markdown_config_rejects_one_source_source_only_scope(self) -> None:
        # Given a source-only scope with only one source binding.
        markdown = (
            VALID_CONFIG.replace(TARGET_INSTANCE_ROW, "")
            .replace(
                PRIMARY_SCOPE_ROW,
                "| activity_nodes | true | v2_huashi | public.activity_nodes |  |  | id |",
            )
            .replace(f"{SECONDARY_SCOPE_ROW}\n", "")
        )

        # When parsing crosses the trust boundary, then the source-only cardinality is rejected.
        self.assertRegex(
            _config_error_message(markdown),
            "source-only.*at least two source bindings",
        )

    def test_parse_markdown_config_allows_mixed_source_only_and_target_scopes(self) -> None:
        # Given one source-only scope and one legacy target scope.
        markdown = VALID_CONFIG.replace(
            PRIMARY_SCOPE_ROW,
            "| activity_nodes | true | v2_huashi,v2_wut | public.activity_nodes |  |  | id,group_id |",
        ).replace(
            SECONDARY_SCOPE_ROW,
            "| course_target | true | v2_gdei | legacy.activity_node | v3_main | "
            "teaching.activity_node | id |",
        )

        # When the mixed configuration is parsed.
        config = _parse_valid_config(markdown)

        # Then each scope retains its independently selected target mode.
        scopes = {scope.scope_id: scope for scope in config.scopes}
        self.assertIsNone(scopes["activity_nodes"].target_instance)
        self.assertEqual(scopes["activity_nodes"].primary_key, ("id", "group_id"))
        self.assertEqual(scopes["course_target"].target_instance, "v3_main")
        self.assertEqual(scopes["course_target"].primary_key, ("id",))

    def test_parse_markdown_config_rejects_invalid_primary_key_identifiers(self) -> None:
        # Given empty, duplicate, unsafe, and malformed comparison-key syntax.
        invalid_keys = (
            ("", "at least one identifier"),
            ("id,,group_id", "empty identifier"),
            ("id,id", "duplicate identifier"),
            ("id;drop", "identifier.*letters"),
            ("id group_id", "identifier.*letters"),
            ("(id,group_id", "parentheses"),
            ("((id,group_id))", "parentheses"),
        )

        # When each key crosses the parser boundary, then its precise contract violation is reported.
        for raw_key, message in invalid_keys:
            with self.subTest(raw_key=raw_key):
                markdown = VALID_CONFIG.replace("| id |", f"| {raw_key} |", 1)
                self.assertRegex(_config_error_message(markdown), message)

    def test_parse_markdown_config_rejects_inconsistent_repeated_scope_keys(self) -> None:
        # Given repeated rows for one scope with different valid comparison keys.
        markdown = VALID_CONFIG.replace(
            "teaching.activity_node | id |",
            "teaching.activity_node | id,group_id |",
            1,
        )

        # When parsing crosses the trust boundary, then repeated-scope consistency is enforced.
        self.assertRegex(
            _config_error_message(markdown),
            "same target table and primary key",
        )

    def test_scope_result_uses_source_conflicts_when_target_was_not_checked(self) -> None:
        # Given a source-only result with one source conflict and no target result.
        result = ScopeResult(
            scope_id=ScopeId("activity_nodes"),
            target_instance=None,
            source_source=ConflictDetails(total=1, records=(), truncated=False),
            source_target=None,
        )

        # When conflict status is evaluated, then the checked source result determines the outcome.
        try:
            has_conflicts = result.has_conflicts()
        except AttributeError:
            has_conflicts = False
        self.assertTrue(has_conflicts)


if __name__ == "__main__":
    unittest.main()
