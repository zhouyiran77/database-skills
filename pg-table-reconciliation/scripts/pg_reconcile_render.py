from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pg_reconcile_model import TableReport
from pg_reconcile_risk import summarize_risks


@dataclass(frozen=True, slots=True)
class OutputConfig:
    output: str
    output_file: Path | None


@dataclass(frozen=True, slots=True)
class UnsupportedOutputError(Exception):
    output: str

    def __str__(self) -> str:
        return f"Unsupported output format: {self.output}"


def write_output(reports: tuple[TableReport, ...], config: OutputConfig) -> None:
    match config.output:
        case "json":
            content = json.dumps([report.to_jsonable() for report in reports], ensure_ascii=False, indent=2)
        case "markdown":
            content = render_markdown(reports)
        case unreachable:
            raise UnsupportedOutputError(output=unreachable)
    if config.output_file:
        config.output_file.write_text(content, encoding="utf-8")
        print(f"Report written to {config.output_file}")
    else:
        print(content)


def render_markdown(reports: tuple[TableReport, ...]) -> str:
    risk_counts = summarize_risks(reports)
    lines = [
        "# PostgreSQL Reconciliation Report",
        "",
        "## Summary",
        "",
        f"- Tables checked: {len(reports)}",
    ]
    for severity, count in risk_counts.items():
        lines.append(f"- {severity.value.title()} risks: {count}")
    for report in reports:
        lines.extend(_table_markdown(report))
    return "\n".join(lines) + "\n"


def _table_markdown(report: TableReport) -> list[str]:
    lines = [
        "",
        f"## {report.table}",
        "",
        f"- Target exists: {report.target_exists}",
        f"- Columns: source={report.source_columns}, target={report.target_columns}",
        f"- Rows: source={report.source_rows}, target={report.target_rows}",
        f"- Primary key: source={list(report.source_pk)}, target={list(report.target_pk)}",
    ]
    if report.only_in_source:
        lines.append(f"- Columns only in source: {', '.join(report.only_in_source)}")
    if report.only_in_target:
        lines.append(f"- Columns only in target: {', '.join(report.only_in_target)}")
    if report.column_diffs:
        lines.append("- Column metadata differences:")
        for diff in report.column_diffs:
            lines.append(f"  - `{diff.column}` {diff.field}: {diff.source} -> {diff.target}")
    if report.risks:
        lines.append("- Risks:")
        for risk in report.risks:
            lines.append(f"  - [{risk.severity.value}] {risk.message} {risk.recommendation}")
    return lines
