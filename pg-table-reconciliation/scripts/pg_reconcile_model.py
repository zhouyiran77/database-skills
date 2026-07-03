from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Final, Self


COMPARE_FIELDS: Final[tuple[str, ...]] = (
    "data_type",
    "udt_name",
    "is_nullable",
    "column_default",
    "character_maximum_length",
    "numeric_precision",
    "numeric_scale",
    "datetime_precision",
)


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DataCheck(StrEnum):
    NONE = "none"
    ROW_COUNT = "row-count"
    HASH = "hash"


@dataclass(frozen=True, slots=True)
class TableName:
    schema: str
    name: str

    @classmethod
    def parse(cls, raw: str) -> Self:
        parts = raw.strip().split(".")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise TableSpecError(raw=raw)
        return cls(schema=parts[0], name=parts[1])

    def label(self) -> str:
        return f"{self.schema}.{self.name}"

    def with_prefix(self, prefix: str) -> Self:
        if not prefix:
            return self
        return type(self)(schema=self.schema, name=f"{prefix}{self.name}")


@dataclass(frozen=True, slots=True)
class TableMapping:
    logical: TableName
    source: TableName
    target: TableName

    @classmethod
    def from_prefixes(cls, logical: TableName, source_prefix: str, target_prefix: str) -> Self:
        return cls(
            logical=logical,
            source=logical.with_prefix(source_prefix),
            target=logical.with_prefix(target_prefix),
        )

    def report_label(self) -> str:
        if self.logical == self.source and self.logical == self.target:
            return self.logical.label()
        return f"{self.logical.label()} (source: {self.source.label()}, target: {self.target.label()})"


@dataclass(frozen=True, slots=True)
class TableSpecError(Exception):
    raw: str

    def __str__(self) -> str:
        return f"Table spec must be schema.table or schema.*, got: {self.raw}"


def table_without_prefix(table: TableName, prefix: str) -> TableName:
    if prefix and table.name.startswith(prefix):
        return TableName(schema=table.schema, name=table.name[len(prefix):])
    return table


@dataclass(frozen=True, slots=True)
class ColumnDef:
    name: str
    ordinal_position: int
    data_type: str
    udt_name: str
    is_nullable: str
    column_default: str | None
    character_maximum_length: int | None
    numeric_precision: int | None
    numeric_scale: int | None
    datetime_precision: int | None


@dataclass(frozen=True, slots=True)
class ColumnDiff:
    column: str
    field: str
    source: str | int | None
    target: str | int | None


@dataclass(frozen=True, slots=True)
class Risk:
    severity: Severity
    table: str
    message: str
    recommendation: str


@dataclass(frozen=True, slots=True)
class TableReport:
    table: str
    target_exists: bool
    source_columns: int
    target_columns: int
    only_in_source: tuple[str, ...]
    only_in_target: tuple[str, ...]
    column_diffs: tuple[ColumnDiff, ...]
    source_pk: tuple[str, ...]
    target_pk: tuple[str, ...]
    source_rows: int | None
    target_rows: int | None
    source_hash: str | None
    target_hash: str | None
    risks: tuple[Risk, ...]

    def to_jsonable(self) -> dict[str, str | bool | int | None | list[str] | list[dict[str, str | int | None]] | list[dict[str, str]]]:
        return {
            "table": self.table,
            "target_exists": self.target_exists,
            "source_columns": self.source_columns,
            "target_columns": self.target_columns,
            "only_in_source": list(self.only_in_source),
            "only_in_target": list(self.only_in_target),
            "column_diffs": [asdict(item) for item in self.column_diffs],
            "source_pk": list(self.source_pk),
            "target_pk": list(self.target_pk),
            "source_rows": self.source_rows,
            "target_rows": self.target_rows,
            "source_hash": self.source_hash,
            "target_hash": self.target_hash,
            "risks": [asdict(item) for item in self.risks],
        }


@dataclass(frozen=True, slots=True)
class DataCheckError(Exception):
    raw: str
    allowed: str

    def __str__(self) -> str:
        return f"Unsupported data check {self.raw}; expected one of: {self.allowed}"


def parse_data_check(raw: str) -> DataCheck:
    try:
        return DataCheck(raw)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in DataCheck)
        raise DataCheckError(raw=raw, allowed=allowed) from exc
