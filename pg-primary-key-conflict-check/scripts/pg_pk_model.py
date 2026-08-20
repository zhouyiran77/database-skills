from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NewType, Self, TypeAlias


InstanceId = NewType("InstanceId", str)
ScopeId = NewType("ScopeId", str)
ColumnName = NewType("ColumnName", str)
IdValue = NewType("IdValue", str)
ComparisonKey: TypeAlias = tuple[ColumnName, ...]
ComparisonValue: TypeAlias = IdValue | tuple[IdValue, ...]


class Role(StrEnum):
    SOURCE = "source"
    TARGET = "target"


class PkConflictError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ConfigError(PkConflictError):
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class TableName:
    schema: str
    name: str

    @classmethod
    def parse(cls, raw: str) -> Self:
        parts = tuple(part.strip() for part in raw.split("."))
        if len(parts) != 2 or not all(parts) or any("\x00" in part for part in parts):
            raise ConfigError(message=f"table must use schema.table format: {raw}")
        return cls(schema=parts[0], name=parts[1])

    def label(self) -> str:
        return f"{self.schema}.{self.name}"


@dataclass(frozen=True, slots=True)
class DatabaseInstance:
    instance_id: InstanceId
    role: Role
    school: str
    host: str
    port: int
    database: str
    username: str
    password_env: str
    sslmode: str


@dataclass(frozen=True, slots=True)
class SourceBinding:
    instance_id: InstanceId
    table: TableName


@dataclass(frozen=True, slots=True)
class ComparisonScope:
    scope_id: ScopeId
    sources: tuple[SourceBinding, ...]
    target_instance: InstanceId | None
    target_table: TableName | None
    primary_key: ComparisonKey


@dataclass(frozen=True, slots=True)
class CheckConfig:
    instances: tuple[DatabaseInstance, ...]
    scopes: tuple[ComparisonScope, ...]

    def instance(self, instance_id: str) -> DatabaseInstance:
        for instance in self.instances:
            if instance.instance_id == instance_id:
                return instance
        raise ConfigError(message=f"unknown instance_id: {instance_id}")


@dataclass(frozen=True, slots=True)
class ObservationBatch:
    scope_id: ScopeId
    instance_id: InstanceId
    role: Role
    ids: tuple[ComparisonValue, ...]


@dataclass(frozen=True, slots=True)
class ConflictRecord:
    id_value: ComparisonValue
    source_instances: tuple[InstanceId, ...]


@dataclass(frozen=True, slots=True)
class ConflictDetails:
    total: int
    records: tuple[ConflictRecord, ...]
    truncated: bool


@dataclass(frozen=True, slots=True)
class ScopeResult:
    scope_id: ScopeId
    target_instance: InstanceId | None
    source_source: ConflictDetails
    source_target: ConflictDetails | None

    def has_conflicts(self) -> bool:
        return self.source_source.total > 0 or (
            self.source_target is not None and self.source_target.total > 0
        )


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    scope: ComparisonScope
    detail_limit: int


@dataclass(frozen=True, slots=True)
class ScanRequest:
    instance: DatabaseInstance
    table: TableName
    primary_key: ComparisonKey
    batch_size: int


@dataclass(frozen=True, slots=True)
class RunOptions:
    batch_size: int
    detail_limit: int


@dataclass(frozen=True, slots=True)
class ScanCount:
    scope_id: ScopeId
    instance_id: InstanceId
    rows: int


@dataclass(frozen=True, slots=True)
class CheckReport:
    results: tuple[ScopeResult, ...]
    scan_counts: tuple[ScanCount, ...]

    def has_conflicts(self) -> bool:
        return any(result.has_conflicts() for result in self.results)

    def result(self, scope_id: ScopeId) -> ScopeResult:
        for result in self.results:
            if result.scope_id == scope_id:
                return result
        raise ConfigError(message=f"missing result for scope: {scope_id}")

    def scanned_rows(self, scope_id: ScopeId, instance_id: InstanceId) -> int:
        for count in self.scan_counts:
            if count.scope_id == scope_id and count.instance_id == instance_id:
                return count.rows
        raise ConfigError(message=f"missing scan count for {scope_id}/{instance_id}")
