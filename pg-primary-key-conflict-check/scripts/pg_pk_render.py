from __future__ import annotations

from pg_pk_model import CheckConfig, CheckReport, ConflictDetails, ScopeResult


def render_markdown(config: CheckConfig, report: CheckReport) -> str:
    status = "冲突" if report.has_conflicts() else "通过"
    lines = [
        "# PostgreSQL 主键 ID 冲突检测报告",
        "",
        "## 结论",
        "",
        f"**{status}**",
        "",
        "## 汇总",
        "",
        "| 逻辑表 | 2.0来源库之间 | 2.0与3.0 | 状态 |",
        "|---|---:|---:|---|",
    ]
    for result in report.results:
        result_status = "冲突" if result.has_conflicts() else "通过"
        lines.append(
            f"| {_escape(result.scope_id)} | {result.source_source.total} | "
            f"{result.source_target.total} | {result_status} |",
        )
    for scope in config.scopes:
        result = report.result(scope.scope_id)
        lines.extend(_scope_section(config, report, result))
    return "\n".join(lines) + "\n"


def _scope_section(config: CheckConfig, report: CheckReport, result: ScopeResult) -> list[str]:
    scope = next(scope for scope in config.scopes if scope.scope_id == result.scope_id)
    lines = [
        "",
        f"## {_escape(scope.scope_id)}",
        "",
        "### 表映射",
        "",
        "| 实例 | 学校 | 角色 | 物理表 | 扫描行数 |",
        "|---|---|---|---|---:|",
    ]
    for binding in scope.sources:
        instance = config.instance(binding.instance_id)
        lines.append(
            f"| {_escape(instance.instance_id)} | "
            f"{_escape(instance.school)} | source | {_escape(binding.table.label())} | "
            f"{report.scanned_rows(scope.scope_id, binding.instance_id)} |",
        )
    target = config.instance(scope.target_instance)
    lines.append(
        f"| {_escape(target.instance_id)} | "
        f"{_escape(target.school)} | target | {_escape(scope.target_table.label())} | "
        f"{report.scanned_rows(scope.scope_id, scope.target_instance)} |",
    )
    lines.extend(
        [
            "",
            "### 冲突明细",
            "",
            "| 冲突类型 | ID | 来源实例 | 目标实例 |",
            "|---|---|---|---|",
        ],
    )
    lines.extend(_detail_rows("2.0来源库之间", result.source_source, "-"))
    lines.extend(_detail_rows("2.0与3.0", result.source_target, result.target_instance))
    if result.source_source.total == 0 and result.source_target.total == 0:
        lines.append("| - | - | - | - |")
    if result.source_source.truncated:
        lines.append(f"\n> 2.0 来源库之间仅展示前 {len(result.source_source.records)} 条，汇总数量为精确值。")
    if result.source_target.truncated:
        lines.append(f"\n> 2.0 与 3.0 仅展示前 {len(result.source_target.records)} 条，汇总数量为精确值。")
    return lines


def _detail_rows(label: str, details: ConflictDetails, target: str) -> list[str]:
    return [
        f"| {label} | {_escape(record.id_value)} | "
        f"{_escape(', '.join(record.source_instances))} | {_escape(target)} |"
        for record in details.records
    ]


def _escape(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
