from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from pg_reconcile_compare import build_table_report, missing_target_report  # noqa: E402
from pg_reconcile_model import ColumnDef, TableName  # noqa: E402
from pg_reconcile_render import render_markdown  # noqa: E402


def column(
    name: str,
    data_type: str,
    nullable: str,
    default: str | None = None,
    length: int | None = None,
    precision: int | None = None,
    scale: int | None = None,
) -> ColumnDef:
    return ColumnDef(
        name=name,
        ordinal_position=1,
        data_type=data_type,
        udt_name=data_type,
        is_nullable=nullable,
        column_default=default,
        character_maximum_length=length,
        numeric_precision=precision,
        numeric_scale=scale,
        datetime_precision=None,
    )


class MarkdownRenderTests(unittest.TestCase):
    def test_existing_target_report_includes_both_table_structures(self) -> None:
        report = build_table_report(
            table=TableName(schema="public", name="auth_client"),
            source_columns=(
                column("id", "bigint", "NO", precision=64),
                column("client_id", "character varying", "NO", length=64),
            ),
            target_columns=(
                column("id", "bigint", "NO", precision=64),
                column("client_id", "character varying", "YES", length=128),
            ),
            stats=(17, 17, None, None),
            primary_keys=(("id",), ("id",)),
            table_label="public.auth_client (source: public.auth_client, target: public.edu_auth_client)",
        )

        markdown = render_markdown((report,))

        self.assertIn("### Source table structure", markdown)
        self.assertIn("| `client_id` | character varying | character varying | NO | - | 64 | - | - | - |", markdown)
        self.assertIn("### Target table structure", markdown)
        self.assertIn("| `client_id` | character varying | character varying | YES | - | 128 | - | - | - |", markdown)

    def test_missing_target_report_includes_source_and_target_table_structures(self) -> None:
        report = missing_target_report(
            table=TableName(schema="public", name="auth_client"),
            source_columns=(
                column("id", "bigint", "NO", default="nextval('auth_client_id_seq'::regclass)", precision=64),
                column("client_id", "character varying", "NO", length=64),
            ),
            source_rows=17,
            table_label="public.auth_client (source: public.auth_client, target: public.edu_auth_client)",
        )

        markdown = render_markdown((report,))

        self.assertIn("### Source table structure", markdown)
        self.assertIn("| Column | Type | UDT | Nullable | Default | Length | Precision | Scale | Datetime precision |", markdown)
        self.assertIn("| `id` | bigint | bigint | NO | nextval('auth_client_id_seq'::regclass) | - | 64 | - | - |", markdown)
        self.assertIn("| `client_id` | character varying | character varying | NO | - | 64 | - | - | - |", markdown)
        self.assertIn("### Target table structure", markdown)
        self.assertIn("_Target table is missing; no target structure is available._", markdown)


if __name__ == "__main__":
    unittest.main()
