from __future__ import annotations

from pg_reconcile_model import COMPARE_FIELDS, ColumnDef, ColumnDiff, Risk, Severity, TableName, TableReport
from pg_reconcile_risk import report_with_risks


def compare_columns(source: tuple[ColumnDef, ...], target: tuple[ColumnDef, ...]) -> tuple[tuple[str, ...], tuple[str, ...], tuple[ColumnDiff, ...]]:
    source_map = {col.name: col for col in source}
    target_map = {col.name: col for col in target}
    only_source = tuple(sorted(source_map.keys() - target_map.keys()))
    only_target = tuple(sorted(target_map.keys() - source_map.keys()))
    diffs: list[ColumnDiff] = []

    for name in sorted(source_map.keys() & target_map.keys()):
        source_col = source_map[name]
        target_col = target_map[name]
        for field in COMPARE_FIELDS:
            source_value = getattr(source_col, field)
            target_value = getattr(target_col, field)
            if source_value != target_value:
                diffs.append(
                    ColumnDiff(
                        column=name,
                        field=field,
                        source=source_value,
                        target=target_value,
                    ),
                )
    return only_source, only_target, tuple(diffs)


def build_table_report(
    table: TableName,
    source_columns: tuple[ColumnDef, ...],
    target_columns: tuple[ColumnDef, ...],
    stats: tuple[int | None, int | None, str | None, str | None],
    primary_keys: tuple[tuple[str, ...], tuple[str, ...]],
    table_label: str | None = None,
) -> TableReport:
    only_source, only_target, column_diffs = compare_columns(source_columns, target_columns)
    source_pk, target_pk = primary_keys
    source_rows, target_rows, source_hash, target_hash = stats
    report = TableReport(
        table=table_label or table.label(),
        target_exists=True,
        source_columns=len(source_columns),
        target_columns=len(target_columns),
        only_in_source=only_source,
        only_in_target=only_target,
        column_diffs=column_diffs,
        source_pk=source_pk,
        target_pk=target_pk,
        source_rows=source_rows,
        target_rows=target_rows,
        source_hash=source_hash,
        target_hash=target_hash,
        risks=(),
    )
    return report_with_risks(report)


def missing_target_report(table: TableName, source_columns: tuple[ColumnDef, ...], source_rows: int | None, table_label: str | None = None) -> TableReport:
    return TableReport(
        table=table_label or table.label(),
        target_exists=False,
        source_columns=len(source_columns),
        target_columns=0,
        only_in_source=tuple(col.name for col in source_columns),
        only_in_target=(),
        column_diffs=(),
        source_pk=(),
        target_pk=(),
        source_rows=source_rows,
        target_rows=None,
        source_hash=None,
        target_hash=None,
        risks=(
            Risk(
                severity=Severity.CRITICAL,
                table=table.label(),
                message="Target table is missing.",
                recommendation="Create or map the target table before migration validation.",
            ),
        ),
    )
