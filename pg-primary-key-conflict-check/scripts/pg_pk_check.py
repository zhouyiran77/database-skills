from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol

from pg_pk_model import (
    AnalysisRequest,
    CheckConfig,
    CheckReport,
    ComparisonValue,
    ObservationBatch,
    PkConflictError,
    Role,
    RunOptions,
    ScanCount,
    ScanRequest,
)
from pg_pk_store import ConflictStore


class IdReader(Protocol):
    def read_batches(self, request: ScanRequest) -> Iterator[tuple[ComparisonValue, ...]]: ...


def execute_check(config: CheckConfig, reader: IdReader, options: RunOptions) -> CheckReport:
    if options.batch_size <= 0:
        raise CheckOptionsError(message="batch_size must be greater than zero")
    if options.detail_limit < 0:
        raise CheckOptionsError(message="detail_limit must be zero or greater")
    results = []
    scan_counts = []
    with TemporaryDirectory(prefix="pg-pk-conflict-") as directory:
        with ConflictStore(Path(directory) / "observations.sqlite3") as store:
            for scope in config.scopes:
                for binding in scope.sources:
                    request = ScanRequest(
                        instance=config.instance(binding.instance_id),
                        table=binding.table,
                        primary_key=scope.primary_key,
                        batch_size=options.batch_size,
                    )
                    rows = 0
                    for batch in reader.read_batches(request):
                        store.add(
                            ObservationBatch(
                                scope_id=scope.scope_id,
                                instance_id=binding.instance_id,
                                role=Role.SOURCE,
                                ids=batch,
                            ),
                        )
                        rows += len(batch)
                    scan_counts.append(ScanCount(scope.scope_id, binding.instance_id, rows))
                target_instance_id = scope.target_instance
                target_table = scope.target_table
                if target_instance_id is not None and target_table is not None:
                    target_request = ScanRequest(
                        instance=config.instance(target_instance_id),
                        table=target_table,
                        primary_key=scope.primary_key,
                        batch_size=options.batch_size,
                    )
                    target_rows = 0
                    for batch in reader.read_batches(target_request):
                        store.add(
                            ObservationBatch(
                                scope_id=scope.scope_id,
                                instance_id=target_instance_id,
                                role=Role.TARGET,
                                ids=batch,
                            ),
                        )
                        target_rows += len(batch)
                    scan_counts.append(ScanCount(scope.scope_id, target_instance_id, target_rows))
                results.append(
                    store.analyze(
                        AnalysisRequest(scope=scope, detail_limit=options.detail_limit),
                    ),
                )
    return CheckReport(results=tuple(results), scan_counts=tuple(scan_counts))


@dataclass(frozen=True, slots=True)
class CheckOptionsError(PkConflictError):
    message: str

    def __str__(self) -> str:
        return self.message
