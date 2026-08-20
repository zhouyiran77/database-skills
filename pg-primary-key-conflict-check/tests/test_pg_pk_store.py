from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from pg_pk_model import (  # noqa: E402
    AnalysisRequest,
    ColumnName,
    ComparisonScope,
    IdValue,
    InstanceId,
    ObservationBatch,
    Role,
    ScopeId,
    SourceBinding,
    TableName,
)
from pg_pk_store import ConflictStore, StoreError, _decode_tuple_key  # noqa: E402


SCOPE = ComparisonScope(
    scope_id=ScopeId("activity_nodes"),
    sources=(
        SourceBinding(InstanceId("v2_huashi"), TableName("public", "activity_nodes")),
        SourceBinding(InstanceId("v2_wut"), TableName("public", "activity_nodes")),
        SourceBinding(InstanceId("v2_gdei"), TableName("legacy", "activity_node")),
    ),
    target_instance=InstanceId("v3_main"),
    target_table=TableName("teaching", "activity_node"),
    primary_key=(ColumnName("id"),),
)

COMPOSITE_SOURCE_ONLY_SCOPE = ComparisonScope(
    scope_id=ScopeId("activity_nodes"),
    sources=SCOPE.sources,
    target_instance=None,
    target_table=None,
    primary_key=(ColumnName("id"), ColumnName("group_id")),
)


class ConflictStoreTests(unittest.TestCase):
    def test_analyze_reports_scalar_source_source_and_source_target_conflicts(self) -> None:
        # Given three source key sets and one target key set persisted in the local index.
        with TemporaryDirectory() as directory, ConflictStore(Path(directory) / "conflicts.sqlite3") as store:
            _add_fixture_keys(store)

            # When the logical-table scope is analyzed.
            result = store.analyze(AnalysisRequest(scope=SCOPE, detail_limit=100))

        # Then each conflict type has an exact unique-key count and deterministic details.
        self.assertEqual(result.source_source.total, 2)
        self.assertEqual(
            tuple((record.id_value, record.source_instances) for record in result.source_source.records),
            (
                (IdValue("2"), (InstanceId("v2_huashi"), InstanceId("v2_wut"))),
                (IdValue("5"), (InstanceId("v2_huashi"), InstanceId("v2_gdei"))),
            ),
        )
        self.assertIsNotNone(result.source_target)
        assert result.source_target is not None
        self.assertEqual(result.source_target.total, 2)
        self.assertEqual(
            tuple((record.id_value, record.source_instances) for record in result.source_target.records),
            (
                (IdValue("3"), (InstanceId("v2_wut"),)),
                (IdValue("5"), (InstanceId("v2_huashi"), InstanceId("v2_gdei"))),
            ),
        )

    def test_analyze_keeps_exact_counts_when_details_are_truncated(self) -> None:
        # Given a scope with two cross-source conflict keys.
        with TemporaryDirectory() as directory, ConflictStore(Path(directory) / "conflicts.sqlite3") as store:
            _add_fixture_keys(store)

            # When details are limited to one row per conflict type.
            result = store.analyze(AnalysisRequest(scope=SCOPE, detail_limit=1))

        # Then the exact count remains two while the detail set is marked truncated.
        self.assertEqual(result.source_source.total, 2)
        self.assertEqual(len(result.source_source.records), 1)
        self.assertTrue(result.source_source.truncated)
        self.assertIsNotNone(result.source_target)
        assert result.source_target is not None
        self.assertEqual(result.source_target.total, 2)
        self.assertEqual(len(result.source_target.records), 1)
        self.assertTrue(result.source_target.truncated)

    def test_analyze_keeps_full_tuple_identity_without_partial_matches(self) -> None:
        # Given keys that collide if concatenated and keys sharing only one component.
        with TemporaryDirectory() as directory, ConflictStore(Path(directory) / "conflicts.sqlite3") as store:
            _add_keys(
                store,
                InstanceId("v2_huashi"),
                Role.SOURCE,
                ("1", "23"),
                ("shared", "whole"),
                ("partial", "left"),
            )
            _add_keys(
                store,
                InstanceId("v2_wut"),
                Role.SOURCE,
                ("12", "3"),
                ("shared", "whole"),
                ("partial", "right"),
            )

            # When the source-only composite scope is analyzed.
            result = store.analyze(
                AnalysisRequest(scope=COMPOSITE_SOURCE_ONLY_SCOPE, detail_limit=100),
            )

        # Then only the identical complete tuple conflicts.
        self.assertEqual(result.source_source.total, 1)
        self.assertEqual(
            tuple(record.id_value for record in result.source_source.records),
            ((IdValue("shared"), IdValue("whole")),),
        )

    def test_analyze_round_trips_delimiter_heavy_tuple_keys(self) -> None:
        # Given equal tuple keys containing every unsafe delimiter class and Unicode.
        special_keys = (("", "雪"), ("comma,value", "(paren)|pipe"))
        with TemporaryDirectory() as directory, ConflictStore(Path(directory) / "conflicts.sqlite3") as store:
            _add_keys(store, InstanceId("v2_huashi"), Role.SOURCE, *special_keys)
            _add_keys(store, InstanceId("v2_wut"), Role.SOURCE, *special_keys)

            # When the source-only composite scope is analyzed through real SQLite.
            result = store.analyze(
                AnalysisRequest(scope=COMPOSITE_SOURCE_ONLY_SCOPE, detail_limit=100),
            )

        # Then decoded detail keys preserve every component exactly.
        self.assertEqual(
            tuple(record.id_value for record in result.source_source.records),
            _keys(*special_keys),
        )

    def test_source_source_conflicts_deduplicate_repeats_within_instance(self) -> None:
        # Given one complete tuple repeated in one source and present in a second source.
        repeated_key = ("same", "tuple")
        with TemporaryDirectory() as directory, ConflictStore(Path(directory) / "conflicts.sqlite3") as store:
            _add_keys(
                store,
                InstanceId("v2_huashi"),
                Role.SOURCE,
                repeated_key,
                repeated_key,
                repeated_key,
            )
            _add_keys(store, InstanceId("v2_wut"), Role.SOURCE, repeated_key)

            # When the source-only scope is analyzed.
            result = store.analyze(
                AnalysisRequest(scope=COMPOSITE_SOURCE_ONLY_SCOPE, detail_limit=100),
            )

        # Then the tuple is counted once and source ordering follows the scope.
        self.assertEqual(result.source_source.total, 1)
        self.assertEqual(
            result.source_source.records[0].source_instances,
            (InstanceId("v2_huashi"), InstanceId("v2_wut")),
        )

    def test_analyze_returns_absent_target_without_target_sql(self) -> None:
        # Given a source-only scope and a trace of statements executed during analysis.
        statements: list[str] = []
        with TemporaryDirectory() as directory, ConflictStore(Path(directory) / "conflicts.sqlite3") as store:
            store._connection.set_trace_callback(statements.append)

            # When the source-only scope is analyzed.
            result = store.analyze(
                AnalysisRequest(scope=COMPOSITE_SOURCE_ONLY_SCOPE, detail_limit=100),
            )

        # Then target analysis is absent and no source-target join was executed.
        self.assertIsNone(result.target_instance)
        self.assertIsNone(result.source_target)
        self.assertFalse(
            any("JOIN observations AS target" in statement for statement in statements),
        )

    def test_analyze_rejects_too_few_composite_components_from_internal_storage(self) -> None:
        # Given a two-column scope whose stored key has only one encoded component.
        with TemporaryDirectory() as directory, ConflictStore(Path(directory) / "conflicts.sqlite3") as store:
            _insert_encoded_source_key(store, '["only-one"]')

            # When the corrupted key reaches conflict analysis.
            with self.assertRaises(StoreError) as captured:
                store.analyze(
                    AnalysisRequest(scope=COMPOSITE_SOURCE_ONLY_SCOPE, detail_limit=100),
                )

        # Then corruption is reported through the typed store boundary without payload data.
        self.assertEqual(str(captured.exception), "stored comparison key is malformed")

    def test_analyze_rejects_too_many_scalar_components_from_internal_storage(self) -> None:
        # Given a one-column scope whose stored key has two encoded components.
        with TemporaryDirectory() as directory, ConflictStore(Path(directory) / "conflicts.sqlite3") as store:
            _insert_encoded_source_key(store, '["first","discarded"]')

            # When the corrupted key reaches conflict analysis.
            with self.assertRaises(StoreError) as captured:
                store.analyze(AnalysisRequest(scope=SCOPE, detail_limit=100))

        # Then surplus data cannot be discarded and the payload is not exposed.
        self.assertEqual(str(captured.exception), "stored comparison key is malformed")

    def test_decode_key_rejects_malformed_internal_json_arrays(self) -> None:
        # Given malformed internal payloads covering syntax, shape, and component types.
        malformed_payloads = (
            "not-json",
            "{}",
            "[]",
            '"scalar"',
            '["ok",1]',
            "[null]",
            "[[]]",
        )

        # When each payload crosses the SQLite decoding boundary.
        for payload in malformed_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(StoreError) as captured:
                    _decode_tuple_key(payload, expected_arity=1)

                # Then corruption is reported as a typed store error without echoing payload data.
                self.assertEqual(str(captured.exception), "stored comparison key is malformed")


def _add_fixture_keys(store: ConflictStore) -> None:
    _add_keys(store, InstanceId("v2_huashi"), Role.SOURCE, ("1",), ("2",), ("2",), ("5",))
    _add_keys(store, InstanceId("v2_wut"), Role.SOURCE, ("2",), ("3",), ("6",))
    _add_keys(store, InstanceId("v2_gdei"), Role.SOURCE, ("5",), ("7",))
    _add_keys(store, InstanceId("v3_main"), Role.TARGET, ("3",), ("5",), ("5",), ("8",))


def _insert_encoded_source_key(store: ConflictStore, encoded: str) -> None:
    store._connection.executemany(
        "INSERT INTO observations(scope_id, key_json, instance_id, role) VALUES (?, ?, ?, ?)",
        (
            (SCOPE.scope_id, encoded, binding.instance_id, Role.SOURCE.value)
            for binding in SCOPE.sources[:2]
        ),
    )
    store._connection.commit()


def _add_keys(
    store: ConflictStore,
    instance_id: InstanceId,
    role: Role,
    *keys: tuple[str, ...],
) -> None:
    store.add(
        ObservationBatch(
            ScopeId("activity_nodes"),
            instance_id,
            role,
            _keys(*keys),
        ),
    )


def _keys(*keys: tuple[str, ...]) -> tuple[tuple[IdValue, ...], ...]:
    return tuple(tuple(IdValue(component) for component in key) for key in keys)


if __name__ == "__main__":
    unittest.main()
