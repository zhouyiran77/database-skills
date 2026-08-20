from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from types import TracebackType
from typing import Self

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


class ConflictStore:
    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.execute(
            "CREATE TABLE observations ("
            "scope_id TEXT NOT NULL, id_value TEXT NOT NULL, "
            "instance_id TEXT NOT NULL, role TEXT NOT NULL, "
            "PRIMARY KEY (scope_id, id_value, instance_id)) WITHOUT ROWID",
        )
        self._connection.execute(
            "CREATE INDEX observations_lookup ON observations(scope_id, role, id_value)",
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
            "INSERT OR IGNORE INTO observations(scope_id, id_value, instance_id, role) VALUES (?, ?, ?, ?)",
            (
                (batch.scope_id, id_value, batch.instance_id, batch.role.value)
                for id_value in batch.ids
            ),
        )
        self._connection.commit()

    def analyze(self, request: AnalysisRequest) -> ScopeResult:
        if request.detail_limit < 0:
            raise StoreError(message="detail_limit must be zero or greater")
        source_source_total = self._source_source_count(request.scope.scope_id)
        source_target_total = self._source_target_count(
            request.scope.scope_id,
            request.scope.target_instance,
        )
        source_source_records = self._source_source_records(request)
        source_target_records = self._source_target_records(request)
        return ScopeResult(
            scope_id=request.scope.scope_id,
            target_instance=request.scope.target_instance,
            source_source=ConflictDetails(
                total=source_source_total,
                records=source_source_records,
                truncated=_is_truncated(source_source_total, source_source_records),
            ),
            source_target=ConflictDetails(
                total=source_target_total,
                records=source_target_records,
                truncated=_is_truncated(source_target_total, source_target_records),
            ),
        )

    def _source_source_count(self, scope_id: str) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) FROM ("
            "SELECT id_value FROM observations "
            "WHERE scope_id = ? AND role = 'source' "
            "GROUP BY id_value HAVING COUNT(*) > 1)",
            (scope_id,),
        ).fetchone()
        return int(row[0]) if row is not None else 0

    def _source_target_count(self, scope_id: str, target_instance: InstanceId) -> int:
        row = self._connection.execute(
            "SELECT COUNT(DISTINCT source.id_value) "
            "FROM observations AS source "
            "JOIN observations AS target "
            "ON target.scope_id = source.scope_id AND target.id_value = source.id_value "
            "WHERE source.scope_id = ? AND source.role = 'source' "
            "AND target.role = 'target' AND target.instance_id = ?",
            (scope_id, target_instance),
        ).fetchone()
        return int(row[0]) if row is not None else 0

    def _source_source_records(self, request: AnalysisRequest) -> tuple[ConflictRecord, ...]:
        sql = (
            "SELECT id_value, GROUP_CONCAT(instance_id, ',') FROM ("
            "SELECT id_value, instance_id FROM observations "
            "WHERE scope_id = ? AND role = 'source' ORDER BY id_value, instance_id) "
            "GROUP BY id_value HAVING COUNT(*) > 1 "
            "ORDER BY LENGTH(id_value), id_value"
        )
        return self._records(sql, (request.scope.scope_id,), request)

    def _source_target_records(self, request: AnalysisRequest) -> tuple[ConflictRecord, ...]:
        sql = (
            "SELECT source.id_value, GROUP_CONCAT(source.instance_id, ',') "
            "FROM observations AS source "
            "JOIN observations AS target "
            "ON target.scope_id = source.scope_id AND target.id_value = source.id_value "
            "WHERE source.scope_id = ? AND source.role = 'source' "
            "AND target.role = 'target' AND target.instance_id = ? "
            "GROUP BY source.id_value ORDER BY LENGTH(source.id_value), source.id_value"
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
        return tuple(
            ConflictRecord(
                id_value=IdValue(str(row[0])),
                source_instances=tuple(
                    sorted(
                        (InstanceId(item) for item in str(row[1]).split(",")),
                        key=source_order.__getitem__,
                    ),
                ),
            )
            for row in rows
        )


@dataclass(frozen=True, slots=True)
class StoreError(PkConflictError):
    message: str

    def __str__(self) -> str:
        return self.message


def _is_truncated(total: int, records: tuple[ConflictRecord, ...]) -> bool:
    return total > len(records)
