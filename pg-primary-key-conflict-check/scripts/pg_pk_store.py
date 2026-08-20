from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from types import TracebackType
from typing import Self, TypeAlias, assert_never

from pg_pk_model import (
    AnalysisRequest,
    ConflictDetails,
    ConflictRecord,
    IdValue,
    InstanceId,
    ObservationBatch,
    PkConflictError,
    ScopeResult,
)


TupleKey: TypeAlias = tuple[IdValue, ...]
TupleKeyInput: TypeAlias = IdValue | TupleKey


class ConflictStore:
    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.execute(
            "CREATE TABLE observations ("
            "scope_id TEXT NOT NULL, key_json TEXT NOT NULL, "
            "instance_id TEXT NOT NULL, role TEXT NOT NULL, "
            "PRIMARY KEY (scope_id, key_json, instance_id)) WITHOUT ROWID",
        )
        self._connection.execute(
            "CREATE INDEX observations_lookup ON observations(scope_id, role, key_json)",
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self._connection.close()
        return False

    def add(self, batch: ObservationBatch) -> None:
        self._connection.executemany(
            "INSERT OR IGNORE INTO observations(scope_id, key_json, instance_id, role) VALUES (?, ?, ?, ?)",
            (
                (batch.scope_id, _encode_tuple_key(key), batch.instance_id, batch.role.value)
                for key in batch.ids
            ),
        )
        self._connection.commit()

    def analyze(self, request: AnalysisRequest) -> ScopeResult:
        if request.detail_limit < 0:
            raise StoreError(message="detail_limit must be zero or greater")
        source_source_total = self._source_source_count(request.scope.scope_id)
        source_source_records = self._source_source_records(request)
        source_target: ConflictDetails | None = None
        if request.scope.target_instance is not None:
            source_target_total = self._source_target_count(
                request.scope.scope_id,
                request.scope.target_instance,
            )
            source_target_records = self._source_target_records(request)
            source_target = ConflictDetails(
                total=source_target_total,
                records=source_target_records,
                truncated=_is_truncated(source_target_total, source_target_records),
            )
        return ScopeResult(
            scope_id=request.scope.scope_id,
            target_instance=request.scope.target_instance,
            source_source=ConflictDetails(
                total=source_source_total,
                records=source_source_records,
                truncated=_is_truncated(source_source_total, source_source_records),
            ),
            source_target=source_target,
        )

    def _source_source_count(self, scope_id: str) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) FROM ("
            "SELECT key_json FROM observations "
            "WHERE scope_id = ? AND role = 'source' "
            "GROUP BY key_json HAVING COUNT(*) > 1)",
            (scope_id,),
        ).fetchone()
        return int(row[0]) if row is not None else 0

    def _source_target_count(self, scope_id: str, target_instance: InstanceId) -> int:
        row = self._connection.execute(
            "SELECT COUNT(DISTINCT source.key_json) "
            "FROM observations AS source "
            "JOIN observations AS target "
            "ON target.scope_id = source.scope_id AND target.key_json = source.key_json "
            "WHERE source.scope_id = ? AND source.role = 'source' "
            "AND target.role = 'target' AND target.instance_id = ?",
            (scope_id, target_instance),
        ).fetchone()
        return int(row[0]) if row is not None else 0

    def _source_source_records(self, request: AnalysisRequest) -> tuple[ConflictRecord, ...]:
        sql = (
            "SELECT key_json, GROUP_CONCAT(instance_id, ',') FROM ("
            "SELECT key_json, instance_id FROM observations "
            "WHERE scope_id = ? AND role = 'source' ORDER BY key_json, instance_id) "
            "GROUP BY key_json HAVING COUNT(*) > 1 "
            "ORDER BY LENGTH(key_json), key_json"
        )
        return self._records(sql, (request.scope.scope_id,), request)

    def _source_target_records(self, request: AnalysisRequest) -> tuple[ConflictRecord, ...]:
        sql = (
            "SELECT source.key_json, GROUP_CONCAT(source.instance_id, ',') "
            "FROM observations AS source "
            "JOIN observations AS target "
            "ON target.scope_id = source.scope_id AND target.key_json = source.key_json "
            "WHERE source.scope_id = ? AND source.role = 'source' "
            "AND target.role = 'target' AND target.instance_id = ? "
            "GROUP BY source.key_json ORDER BY LENGTH(source.key_json), source.key_json"
        )
        return self._records(
            sql,
            (request.scope.scope_id, request.scope.target_instance),
            request,
        )

    def _records(
        self,
        sql: str,
        parameters: tuple[str, ...],
        request: AnalysisRequest,
    ) -> tuple[ConflictRecord, ...]:
        query = sql
        query_parameters: tuple[str | int, ...] = parameters
        if request.detail_limit > 0:
            query = f"{sql} LIMIT ?"
            query_parameters = (*parameters, request.detail_limit)
        rows = self._connection.execute(query, query_parameters).fetchall()
        source_order = {
            binding.instance_id: index
            for index, binding in enumerate(request.scope.sources)
        }
        records: list[ConflictRecord] = []
        for row in rows:
            key = _decode_tuple_key(str(row[0]), len(request.scope.primary_key))
            record_key = key[0] if len(request.scope.primary_key) == 1 else key
            records.append(
                ConflictRecord(
                    id_value=record_key,
                    source_instances=tuple(
                        sorted(
                            (InstanceId(item) for item in str(row[1]).split(",")),
                            key=source_order.__getitem__,
                        ),
                    ),
                ),
            )
        return tuple(records)


@dataclass(frozen=True, slots=True)
class StoreError(PkConflictError):
    message: str

    def __str__(self) -> str:
        return self.message


def _encode_tuple_key(key: TupleKeyInput) -> str:
    match key:
        case str() as scalar:
            components = (IdValue(scalar),)
        case tuple() as components:
            pass
        case unreachable:
            assert_never(unreachable)
    return json.dumps(components, ensure_ascii=False, separators=(",", ":"))


def _decode_tuple_key(encoded: str, expected_arity: int) -> TupleKey:
    try:
        components = json.loads(encoded)
    except json.JSONDecodeError as error:
        raise StoreError(message="stored comparison key is malformed") from error
    if (
        not isinstance(components, list)
        or not components
        or not all(isinstance(component, str) for component in components)
        or len(components) != expected_arity
    ):
        raise StoreError(message="stored comparison key is malformed")
    return tuple(IdValue(component) for component in components)


def _is_truncated(total: int, records: tuple[ConflictRecord, ...]) -> bool:
    return total > len(records)
