from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Final

from pg_pk_model import (
    CheckConfig,
    ComparisonScope,
    ConfigError,
    DatabaseInstance,
    InstanceId,
    Role,
    ScopeId,
    SourceBinding,
    TableName,
)


INSTANCE_HEADING: Final = "数据库实例"
SCOPE_HEADING: Final = "表比对范围"
INSTANCE_COLUMNS: Final = (
    "instance_id",
    "role",
    "school",
    "db_type",
    "host",
    "port",
    "database",
    "username",
    "password_env",
    "sslmode",
)
SCOPE_COLUMNS: Final = (
    "scope_id",
    "enabled",
    "source_instances",
    "source_table",
    "target_instance",
    "target_table",
    "primary_key",
)
FORBIDDEN_SECRET_COLUMNS: Final = frozenset({"password", "dsn", "connection_string"})
SSL_MODES: Final = frozenset({"disable", "allow", "prefer", "require", "verify-ca", "verify-full"})
SAFE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")


@dataclass(frozen=True, slots=True)
class MarkdownRow:
    headers: tuple[str, ...]
    cells: tuple[str, ...]

    def value(self, name: str) -> str:
        return self.cells[self.headers.index(name)]


@dataclass(frozen=True, slots=True)
class MarkdownTable:
    headers: tuple[str, ...]
    rows: tuple[MarkdownRow, ...]


@dataclass(frozen=True, slots=True)
class ScopeRow:
    scope_id: ScopeId
    source_instances: str
    source_table: TableName
    target_instance: InstanceId
    target_table: TableName
    primary_key: str


def parse_markdown_config(markdown: str) -> CheckConfig:
    instance_table = _extract_table(markdown, INSTANCE_HEADING, INSTANCE_COLUMNS)
    scope_table = _extract_table(markdown, SCOPE_HEADING, SCOPE_COLUMNS)
    instances = _parse_instances(instance_table)
    scopes = _parse_scopes(scope_table, instances)
    if not scopes:
        raise ConfigError(message="表比对范围 must contain at least one enabled row")
    return CheckConfig(instances=instances, scopes=scopes)


def _extract_table(markdown: str, heading: str, required: tuple[str, ...]) -> MarkdownTable:
    lines = markdown.splitlines()
    heading_index = next(
        (index for index, line in enumerate(lines) if line.strip().lstrip("#").strip() == heading),
        None,
    )
    if heading_index is None:
        raise ConfigError(message=f"missing Markdown section: ## {heading}")
    table_lines = tuple(line for line in lines[heading_index + 1 :] if line.strip())
    if len(table_lines) < 2 or not table_lines[0].lstrip().startswith("|"):
        raise ConfigError(message=f"section {heading} must contain a Markdown table")
    headers = _split_row(table_lines[0])
    secret_columns = FORBIDDEN_SECRET_COLUMNS.intersection(headers)
    if secret_columns:
        raise ConfigError(message="store secrets through password_env; plaintext password/DSN columns are forbidden")
    missing = tuple(column for column in required if column not in headers)
    if missing:
        raise ConfigError(message=f"section {heading} missing columns: {', '.join(missing)}")
    if len(headers) != len(set(headers)):
        raise ConfigError(message=f"section {heading} contains duplicate columns")
    separator = _split_row(table_lines[1])
    if len(separator) != len(headers):
        raise ConfigError(message=f"section {heading} has an invalid separator row")
    rows: list[MarkdownRow] = []
    for line in table_lines[2:]:
        if line.lstrip().startswith("#"):
            break
        if not line.lstrip().startswith("|"):
            break
        cells = _split_row(line)
        if len(cells) != len(headers):
            raise ConfigError(message=f"section {heading} contains a row with {len(cells)} cells; expected {len(headers)}")
        rows.append(MarkdownRow(headers=headers, cells=cells))
    return MarkdownTable(headers=headers, rows=tuple(rows))


def _split_row(line: str) -> tuple[str, ...]:
    return tuple(cell.strip() for cell in line.strip().strip("|").split("|"))


def _parse_instances(table: MarkdownTable) -> tuple[DatabaseInstance, ...]:
    instances = tuple(_parse_instance(row) for row in table.rows)
    identifiers = tuple(instance.instance_id for instance in instances)
    if len(identifiers) != len(set(identifiers)):
        raise ConfigError(message="instance_id values must be unique")
    if not any(instance.role is Role.SOURCE for instance in instances):
        raise ConfigError(message="数据库实例 must contain at least one source")
    if not any(instance.role is Role.TARGET for instance in instances):
        raise ConfigError(message="数据库实例 must contain at least one target")
    return instances


def _parse_instance(row: MarkdownRow) -> DatabaseInstance:
    instance_id = _parse_safe_id(row.value("instance_id"), "instance_id")
    try:
        role = Role(row.value("role"))
    except ValueError as exc:
        raise ConfigError(message=f"instance {instance_id} role must be source or target") from exc
    if row.value("db_type") != "postgresql":
        raise ConfigError(message=f"instance {instance_id} db_type must be postgresql")
    try:
        port = int(row.value("port"))
    except ValueError as exc:
        raise ConfigError(message=f"instance {instance_id} port must be an integer") from exc
    if not 1 <= port <= 65_535:
        raise ConfigError(message=f"instance {instance_id} port must be between 1 and 65535")
    password_env = row.value("password_env")
    if ENV_NAME.fullmatch(password_env) is None:
        raise ConfigError(message=f"instance {instance_id} password_env must be an environment variable name")
    sslmode = row.value("sslmode")
    if sslmode not in SSL_MODES:
        raise ConfigError(message=f"instance {instance_id} has unsupported sslmode: {sslmode}")
    text_fields = ("school", "host", "database", "username")
    if any(not row.value(field) for field in text_fields):
        raise ConfigError(message=f"instance {instance_id} contains an empty required field")
    return DatabaseInstance(
        instance_id=InstanceId(instance_id),
        role=role,
        school=row.value("school"),
        host=row.value("host"),
        port=port,
        database=row.value("database"),
        username=row.value("username"),
        password_env=password_env,
        sslmode=sslmode,
    )


def _parse_scopes(table: MarkdownTable, instances: tuple[DatabaseInstance, ...]) -> tuple[ComparisonScope, ...]:
    enabled_rows = tuple(_parse_scope_row(row) for row in table.rows if _parse_enabled(row.value("enabled")))
    ordered_ids = tuple(dict.fromkeys(row.scope_id for row in enabled_rows))
    return tuple(_merge_scope(scope_id, enabled_rows, instances) for scope_id in ordered_ids)


def _parse_scope_row(row: MarkdownRow) -> ScopeRow:
    scope_id = ScopeId(_parse_safe_id(row.value("scope_id"), "scope_id"))
    primary_key = row.value("primary_key")
    if primary_key != "id":
        raise ConfigError(message=f"scope {scope_id} primary_key must be id in v1")
    return ScopeRow(
        scope_id=scope_id,
        source_instances=row.value("source_instances"),
        source_table=TableName.parse(row.value("source_table")),
        target_instance=InstanceId(row.value("target_instance")),
        target_table=TableName.parse(row.value("target_table")),
        primary_key=primary_key,
    )


def _merge_scope(
    scope_id: ScopeId,
    rows: tuple[ScopeRow, ...],
    instances: tuple[DatabaseInstance, ...],
) -> ComparisonScope:
    grouped = tuple(row for row in rows if row.scope_id == scope_id)
    first = grouped[0]
    if any(
        row.target_instance != first.target_instance
        or row.target_table != first.target_table
        or row.primary_key != first.primary_key
        for row in grouped[1:]
    ):
        raise ConfigError(message=f"scope {scope_id} rows must use the same target table and primary key")
    target = _find_instance(first.target_instance, instances)
    if target.role is not Role.TARGET:
        raise ConfigError(message=f"scope {scope_id} target_instance must reference a target role")
    source_bindings: list[SourceBinding] = []
    seen: set[InstanceId] = set()
    for row in grouped:
        aliases = _expand_sources(row.source_instances, instances)
        for alias in aliases:
            source = _find_instance(alias, instances)
            if source.role is not Role.SOURCE:
                raise ConfigError(message=f"scope {scope_id} source_instances must reference source roles")
            if alias in seen:
                raise ConfigError(message=f"scope {scope_id} maps source instance {alias} more than once")
            seen.add(alias)
            source_bindings.append(SourceBinding(instance_id=alias, table=row.source_table))
    return ComparisonScope(
        scope_id=scope_id,
        sources=tuple(source_bindings),
        target_instance=first.target_instance,
        target_table=first.target_table,
        primary_key=first.primary_key,
    )


def _expand_sources(raw: str, instances: tuple[DatabaseInstance, ...]) -> tuple[InstanceId, ...]:
    if raw == "*":
        return tuple(instance.instance_id for instance in instances if instance.role is Role.SOURCE)
    aliases = tuple(InstanceId(item.strip()) for item in raw.split(",") if item.strip())
    if not aliases:
        raise ConfigError(message="source_instances must be * or a comma-separated instance list")
    return aliases


def _find_instance(instance_id: InstanceId, instances: tuple[DatabaseInstance, ...]) -> DatabaseInstance:
    for instance in instances:
        if instance.instance_id == instance_id:
            return instance
    raise ConfigError(message=f"unknown instance_id: {instance_id}")


def _parse_safe_id(raw: str, field: str) -> str:
    if SAFE_ID.fullmatch(raw) is None:
        raise ConfigError(message=f"{field} must start with a letter and contain only letters, digits, or underscores")
    return raw


def _parse_enabled(raw: str) -> bool:
    values: Final = {"true": True, "false": False}
    try:
        return values[raw.lower()]
    except KeyError as exc:
        raise ConfigError(message=f"enabled must be true or false, got: {raw}") from exc


__all__ = ["ConfigError", "parse_markdown_config"]
