from __future__ import annotations

from dataclasses import replace

from pg_reconcile_model import ColumnDiff, Risk, Severity, TableReport


def report_with_risks(report: TableReport) -> TableReport:
    risks: list[Risk] = []
    risks.extend(_presence_risks(report))
    risks.extend(_primary_key_risks(report))
    risks.extend(_column_detail_risks(report))
    risks.extend(_data_risks(report))
    return replace(report, risks=tuple(risks))


def summarize_risks(reports: tuple[TableReport, ...]) -> dict[Severity, int]:
    summary = {severity: 0 for severity in Severity}
    for report in reports:
        for risk in report.risks:
            summary[risk.severity] += 1
    return summary


def _presence_risks(report: TableReport) -> tuple[Risk, ...]:
    risks: list[Risk] = []
    for column in report.only_in_source:
        risks.append(
            Risk(
                severity=Severity.CRITICAL,
                table=report.table,
                message=f"Target is missing source column `{column}`.",
                recommendation="Add the column or confirm it is intentionally dropped with a mapping rule.",
            ),
        )
    for column in report.only_in_target:
        risks.append(
            Risk(
                severity=Severity.LOW,
                table=report.table,
                message=f"Target has extra column `{column}`.",
                recommendation="Confirm the column is nullable or has a safe default for migrated rows.",
            ),
        )
    return tuple(risks)


def _primary_key_risks(report: TableReport) -> tuple[Risk, ...]:
    if not report.source_pk and not report.target_pk:
        return (
            Risk(
                severity=Severity.HIGH,
                table=report.table,
                message="No primary key detected on either side.",
                recommendation="Provide a business key before running row-level or hash validation.",
            ),
        )
    if report.source_pk != report.target_pk:
        return (
            Risk(
                severity=Severity.CRITICAL,
                table=report.table,
                message=f"Primary key differs: source={report.source_pk}, target={report.target_pk}.",
                recommendation="Align primary keys or configure the validated business key.",
            ),
        )
    return ()


def _column_detail_risks(report: TableReport) -> tuple[Risk, ...]:
    risks: list[Risk] = []
    for diff in report.column_diffs:
        risks.append(_risk_for_column_diff(report.table, diff))
    return tuple(risks)


def _risk_for_column_diff(table: str, diff: ColumnDiff) -> Risk:
    match diff.field:
        case "data_type" | "udt_name":
            return Risk(Severity.CRITICAL, table, f"`{diff.column}` type differs: {diff.source} -> {diff.target}.", "Validate casting rules before migration.")
        case "character_maximum_length" | "numeric_precision" | "numeric_scale":
            return Risk(Severity.HIGH, table, f"`{diff.column}` size/precision differs on {diff.field}: {diff.source} -> {diff.target}.", "Check for truncation or rounding risk.")
        case "is_nullable":
            return Risk(Severity.MEDIUM, table, f"`{diff.column}` nullability differs: {diff.source} -> {diff.target}.", "Check source nulls before loading into stricter target columns.")
        case "column_default" | "datetime_precision":
            return Risk(Severity.MEDIUM, table, f"`{diff.column}` metadata differs on {diff.field}: {diff.source} -> {diff.target}.", "Confirm application behavior is unchanged.")
        case _:
            return Risk(Severity.LOW, table, f"`{diff.column}` metadata differs on {diff.field}: {diff.source} -> {diff.target}.", "Review the metadata difference before sign-off.")


def _data_risks(report: TableReport) -> tuple[Risk, ...]:
    risks: list[Risk] = []
    if report.source_rows != report.target_rows:
        risks.append(
            Risk(
                severity=Severity.HIGH,
                table=report.table,
                message=f"Row count differs: source={report.source_rows}, target={report.target_rows}.",
                recommendation="Investigate missing, filtered, duplicated, or failed migrated rows.",
            ),
        )
    if report.source_hash and report.target_hash and report.source_hash != report.target_hash:
        risks.append(
            Risk(
                severity=Severity.MEDIUM,
                table=report.table,
                message="Table hash signature differs.",
                recommendation="Run field-level diff on the table using the primary key.",
            ),
        )
    return tuple(risks)

