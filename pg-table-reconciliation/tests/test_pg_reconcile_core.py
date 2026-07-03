from pathlib import Path
import sys
import unittest


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from pg_reconcile_core import (  # noqa: E402
    ColumnDef,
    Severity,
    TableMapping,
    TableName,
    build_table_report,
    missing_target_report,
    table_without_prefix,
)


def column(name: str, data_type: str = "integer", nullable: str = "NO") -> ColumnDef:
    return ColumnDef(
        name=name,
        ordinal_position=1,
        data_type=data_type,
        udt_name=data_type,
        is_nullable=nullable,
        column_default=None,
        character_maximum_length=None,
        numeric_precision=None,
        numeric_scale=None,
        datetime_precision=None,
    )


class CoreComparisonTests(unittest.TestCase):
    def test_reports_critical_risk_when_target_column_missing(self) -> None:
        table = TableName(schema="public", name="student")

        report = build_table_report(
            table=table,
            source_columns=(column("id"), column("name", data_type="text")),
            target_columns=(column("id"),),
            stats=(10, 10, None, None),
            primary_keys=(("id",), ("id",)),
        )

        self.assertEqual(report.only_in_source, ("name",))
        self.assertEqual(report.risks[0].severity, Severity.CRITICAL)

    def test_reports_primary_key_and_row_count_risks(self) -> None:
        table = TableName(schema="public", name="course")

        report = build_table_report(
            table=table,
            source_columns=(column("id"),),
            target_columns=(column("id"),),
            stats=(20, 19, None, None),
            primary_keys=(("id",), ("course_id",)),
        )

        self.assertEqual(
            [risk.severity for risk in report.risks],
            [Severity.CRITICAL, Severity.HIGH],
        )

    def test_missing_target_report_is_critical(self) -> None:
        table = TableName(schema="public", name="teacher")

        report = missing_target_report(table, (column("id"),), 3)

        self.assertFalse(report.target_exists)
        self.assertEqual(report.only_in_source, ("id",))
        self.assertEqual(report.risks[0].severity, Severity.CRITICAL)

    def test_target_prefix_maps_logical_name_to_physical_target_table(self) -> None:
        mapping = TableMapping.from_prefixes(
            logical=TableName(schema="public", name="user"),
            source_prefix="",
            target_prefix="edu_",
        )

        self.assertEqual(mapping.source.label(), "public.user")
        self.assertEqual(mapping.target.label(), "public.edu_user")
        self.assertEqual(mapping.report_label(), "public.user (source: public.user, target: public.edu_user)")

    def test_source_prefix_maps_logical_name_to_physical_source_table(self) -> None:
        mapping = TableMapping.from_prefixes(
            logical=TableName(schema="public", name="user"),
            source_prefix="edu_",
            target_prefix="",
        )

        self.assertEqual(mapping.source.label(), "public.edu_user")
        self.assertEqual(mapping.target.label(), "public.user")

    def test_table_without_prefix_strips_source_prefix_for_wildcard_logical_name(self) -> None:
        logical = table_without_prefix(TableName(schema="public", name="edu_user"), "edu_")

        self.assertEqual(logical.label(), "public.user")


if __name__ == "__main__":
    unittest.main()
