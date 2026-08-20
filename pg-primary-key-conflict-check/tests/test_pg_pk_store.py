from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from pg_pk_model import (  # noqa: E402
    AnalysisRequest,
    ComparisonScope,
    IdValue,
    InstanceId,
    ObservationBatch,
    Role,
    ScopeId,
    SourceBinding,
    TableName,
)
from pg_pk_store import ConflictStore  # noqa: E402


SCOPE = ComparisonScope(
    scope_id=ScopeId("activity_nodes"),
    sources=(
        SourceBinding(InstanceId("v2_huashi"), TableName("public", "activity_nodes")),
        SourceBinding(InstanceId("v2_wut"), TableName("public", "activity_nodes")),
        SourceBinding(InstanceId("v2_gdei"), TableName("legacy", "activity_node")),
    ),
    target_instance=InstanceId("v3_main"),
    target_table=TableName("teaching", "activity_node"),
    primary_key="id",
)


class ConflictStoreTests(unittest.TestCase):
    def test_analyze_reports_source_source_and_source_target_conflicts(self) -> None:
        # Given three source ID sets and one target ID set persisted in the local index.
        with TemporaryDirectory() as directory, ConflictStore(Path(directory) / "conflicts.sqlite3") as store:
            _add_fixture_ids(store)

            # When the logical-table scope is analyzed.
            result = store.analyze(AnalysisRequest(scope=SCOPE, detail_limit=100))

        # Then each conflict type has an exact unique-ID count and deterministic details.
        self.assertEqual(result.source_source.total, 2)
        self.assertEqual(
            tuple((record.id_value, record.source_instances) for record in result.source_source.records),
            (
                (IdValue("2"), (InstanceId("v2_huashi"), InstanceId("v2_wut"))),
                (IdValue("5"), (InstanceId("v2_huashi"), InstanceId("v2_gdei"))),
            ),
        )
        self.assertEqual(result.source_target.total, 2)
        self.assertEqual(
            tuple((record.id_value, record.source_instances) for record in result.source_target.records),
            (
                (IdValue("3"), (InstanceId("v2_wut"),)),
                (IdValue("5"), (InstanceId("v2_huashi"), InstanceId("v2_gdei"))),
            ),
        )

    def test_analyze_keeps_exact_counts_when_details_are_truncated(self) -> None:
        # Given a scope with two cross-source conflict IDs.
        with TemporaryDirectory() as directory, ConflictStore(Path(directory) / "conflicts.sqlite3") as store:
            _add_fixture_ids(store)

            # When details are limited to one row per conflict type.
            result = store.analyze(AnalysisRequest(scope=SCOPE, detail_limit=1))

        # Then the exact count remains two while the detail set is marked truncated.
        self.assertEqual(result.source_source.total, 2)
        self.assertEqual(len(result.source_source.records), 1)
        self.assertTrue(result.source_source.truncated)
        self.assertEqual(result.source_target.total, 2)
        self.assertEqual(len(result.source_target.records), 1)
        self.assertTrue(result.source_target.truncated)


def _add_fixture_ids(store: ConflictStore) -> None:
    store.add(ObservationBatch(ScopeId("activity_nodes"), InstanceId("v2_huashi"), Role.SOURCE, _ids("1", "2", "5")))
    store.add(ObservationBatch(ScopeId("activity_nodes"), InstanceId("v2_wut"), Role.SOURCE, _ids("2", "3", "6")))
    store.add(ObservationBatch(ScopeId("activity_nodes"), InstanceId("v2_gdei"), Role.SOURCE, _ids("5", "7")))
    store.add(ObservationBatch(ScopeId("activity_nodes"), InstanceId("v3_main"), Role.TARGET, _ids("3", "5", "8")))


def _ids(*values: str) -> tuple[IdValue, ...]:
    return tuple(IdValue(value) for value in values)


if __name__ == "__main__":
    unittest.main()
