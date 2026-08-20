from __future__ import annotations

from pathlib import Path
import sys
from types import TracebackType
from typing import Final, Self, TypeAlias, assert_never
import unittest
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import pg_pk_postgres  # noqa: E402
from pg_pk_model import (  # noqa: E402
    ColumnName, DatabaseInstance, IdValue, InstanceId,
    PkConflictError, Role, ScanRequest, TableName,
)


MetadataParameter: TypeAlias = str | tuple[ColumnName, ...] | list[ColumnName]
DatabaseRow: TypeAlias = tuple[str | None, ...]
DatabaseBatch: TypeAlias = tuple[DatabaseRow, ...]
TABLE_ERROR_PREFIX: Final = "instance v2_huashi table public.activity_nodes: "


class DatabaseErrorTests(unittest.TestCase):
    def test_database_error_reason_is_ascii_when_driver_message_is_localized(self) -> None:
        # Given a libpq error containing a character that a Windows GBK stream cannot encode.
        error = psycopg.OperationalError("authentication failed: \ufffd")

        # When the adapter converts the driver error for user-facing output.
        reason = pg_pk_postgres.database_error_reason(error)

        # Then the stable summary is printable without carrying localized driver text.
        self.assertEqual(reason, "OperationalError")
        self.assertTrue(reason.isascii())


class TableContractTests(unittest.TestCase):
    def test_accepts_id_column_when_actual_primary_key_is_composite(self) -> None:
        # Given a table whose primary key is (id, group_id) and whose id column exists.
        connection = TableContractConnection(columns={"id": "NO"})

        # When the table contract is checked for comparison column id.
        result = pg_pk_postgres._validate_table_contract(connection, _scan_request())

        # Then no contract error is raised even though id is not independently unique.
        self.assertIsNone(result)

    def test_rejects_table_when_id_comparison_column_is_missing(self) -> None:
        # Given a table that exists but has no id column.
        connection = TableContractConnection(columns={})

        # When the table contract is checked for comparison column id.
        message = _table_contract_error(connection, _scan_request())

        # Then the error identifies the missing comparison column.
        self.assertEqual(message, TABLE_ERROR_PREFIX + "comparison column id does not exist")

    def test_reports_every_missing_comparison_column_in_requested_order(self) -> None:
        # Given a table missing three configured comparison columns.
        connection = TableContractConnection(columns={"unrelated": "NO"})
        request = _scan_request(
            primary_key=(ColumnName("group_id"), ColumnName("id"), ColumnName("tenant_id"))
        )

        # When the table contract is checked.
        message = _table_contract_error(connection, request)

        # Then all missing columns are reported in configured order.
        self.assertEqual(
            message,
            TABLE_ERROR_PREFIX + "comparison columns do not exist: group_id, id, tenant_id",
        )

    def test_rejects_missing_component_from_composite_key(self) -> None:
        # Given a table with id but without the configured group_id component.
        connection = TableContractConnection(columns={"id": "NO"})
        request = _scan_request(primary_key=(ColumnName("id"), ColumnName("group_id")))

        # When the table contract is checked.
        message = _table_contract_error(connection, request)

        # Then the missing component is identified without changing requested order.
        self.assertEqual(
            message,
            TABLE_ERROR_PREFIX + "comparison column group_id does not exist",
        )

    def test_rejects_nullable_comparison_columns_in_requested_order(self) -> None:
        # Given configured columns whose metadata is returned in a different order.
        connection = TableContractConnection(
            columns={"id": "YES", "group_id": "NO", "tenant_id": "YES"}
        )
        request = _scan_request(
            primary_key=(ColumnName("tenant_id"), ColumnName("group_id"), ColumnName("id"))
        )

        # When the table contract is checked.
        message = _table_contract_error(connection, request)

        # Then every nullable column is reported in configured order.
        self.assertEqual(
            message,
            TABLE_ERROR_PREFIX + "comparison columns are nullable: tenant_id, id",
        )

    def test_rejects_nullable_component_from_composite_key(self) -> None:
        # Given a composite key whose group_id component is nullable.
        connection = TableContractConnection(columns={"id": "NO", "group_id": "YES"})
        request = _scan_request(primary_key=(ColumnName("id"), ColumnName("group_id")))

        # When the table contract is checked.
        message = _table_contract_error(connection, request)

        # Then the nullable component is identified as a table-contract violation.
        self.assertEqual(message, TABLE_ERROR_PREFIX + "comparison column group_id is nullable")


class PgIdReaderTests(unittest.TestCase):
    def test_streams_composite_components_in_requested_order_without_coercion(self) -> None:
        # Given composite rows containing delimiters, an empty string, and Unicode.
        connection = TableContractConnection(
            columns={"id": "NO", "group_id": "NO"},
            batches=(
                (("1,|()", "教学组"), ("", "Ω|组,号")),
                (("3", "最终组"),),
            ),
        )
        request = _scan_request(primary_key=(ColumnName("id"), ColumnName("group_id")))

        # When the real reader streams all batches through the fake server cursor.
        batches = _read_batches(connection, request)

        # Then each key is an ordered tuple and every component is preserved exactly.
        self.assertEqual(
            batches,
            (
                (
                    (IdValue("1,|()"), IdValue("教学组")),
                    (IdValue(""), IdValue("Ω|组,号")),
                ),
                ((IdValue("3"), IdValue("最终组")),),
            ),
        )

    def test_streams_scalar_key_as_one_component_tuple(self) -> None:
        # Given a legacy scalar id request and one database row.
        connection = TableContractConnection(columns={"id": "NO"}, batches=((('42',),),))

        # When the real reader streams the scalar request.
        batches = _read_batches(connection, _scan_request())

        # Then the scalar value retains the canonical one-component tuple shape.
        self.assertEqual(batches, (((IdValue("42"),),),))

    def test_composes_every_column_and_table_name_as_identifier(self) -> None:
        # Given an adversarial key name that bypasses the upstream parser in this fixture.
        unsafe_column = ColumnName('id"; DROP TABLE audit_log; --')
        connection = TableContractConnection(
            columns={unsafe_column: "NO", "group_id": "NO"},
        )
        request = _scan_request(primary_key=(unsafe_column, ColumnName("group_id")))

        # When the real reader composes and executes its SELECT.
        _read_batches(connection, request)

        # Then psycopg Identifier quoting contains the payload as data and preserves order.
        server_cursor = connection.server_cursor
        self.assertIsNotNone(server_cursor)
        assert server_cursor is not None
        self.assertIsInstance(server_cursor.query, sql.Composed)
        assert server_cursor.query is not None
        self.assertEqual(
            server_cursor.query.as_string(),
            'SELECT "id""; DROP TABLE audit_log; --"::text, "group_id"::text '
            'FROM "public"."activity_nodes"',
        )

    def test_preserves_server_cursor_batching_and_read_only_connection_options(self) -> None:
        # Given two server-side batches and a requested fetch size of two.
        connection = TableContractConnection(
            columns={"id": "NO"},
            batches=((("1",), ("2",)), (("3",),)),
        )

        # When the real reader consumes the cursor.
        _read_batches(connection, _scan_request(batch_size=2))

        # Then it uses the named cursor, requested batch size, and read-only transaction option.
        self.assertEqual(connection.cursor_names, [None, "pk_conflict_scan"])
        server_cursor = connection.server_cursor
        self.assertIsNotNone(server_cursor)
        assert server_cursor is not None
        self.assertEqual(server_cursor.fetch_sizes, [2, 2, 2])
        self.assertIsNotNone(connection.conninfo)
        assert connection.conninfo is not None
        self.assertEqual(
            conninfo_to_dict(connection.conninfo)["options"],
            "-c default_transaction_read_only=on",
        )

    def test_rejects_null_component_without_exposing_row_or_secret(self) -> None:
        # Given a runtime row that violates verified non-null column metadata.
        sensitive_row_value = "row-value-密码|,()"
        secret = "reader-password-secret"
        connection = TableContractConnection(
            columns={"id": "NO", "group_id": "NO"},
            batches=(((sensitive_row_value, None),),),
        )
        request = _scan_request(primary_key=(ColumnName("id"), ColumnName("group_id")))

        # When the real reader encounters the null component.
        with self.assertRaises(pg_pk_postgres.TableContractError) as captured:
            _read_batches(connection, request, secret)

        # Then the typed exit-code-2-compatible error contains contract context only.
        self.assertIsInstance(captured.exception, PkConflictError)
        message = str(captured.exception)
        self.assertEqual(
            message,
            TABLE_ERROR_PREFIX + "query returned null for comparison column group_id",
        )
        self.assertNotIn(sensitive_row_value, message)
        self.assertNotIn(secret, message)


class ContextFake:
    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None) -> bool:
        return False


class TableContractConnection(ContextFake):
    def __init__(self, columns: dict[str, str], batches: tuple[DatabaseBatch, ...] = ()) -> None:
        self._columns = columns
        self._batches = batches
        self.cursor_names: list[str | None] = []
        self.server_cursor: ServerCursor | None = None
        self.conninfo: str | None = None

    def connect(self, conninfo: str) -> Self:
        self.conninfo = conninfo
        return self

    def cursor(self, name: str | None = None) -> TableContractCursor | ServerCursor:
        self.cursor_names.append(name)
        match name:
            case None:
                return TableContractCursor(self._columns)
            case str():
                self.server_cursor = ServerCursor(self._batches)
                return self.server_cursor
            case unreachable:
                assert_never(unreachable)


class TableContractCursor(ContextFake):
    def __init__(self, columns: dict[str, str]) -> None:
        self._columns = columns
        self._query = ""
        self._parameters: tuple[MetadataParameter, ...] = ()

    def execute(self, query: str, parameters: tuple[MetadataParameter, ...]) -> None:
        self._query = query
        self._parameters = parameters

    def fetchone(self) -> tuple[bool] | None:
        if "information_schema.tables" in self._query:
            return (True,)
        if "information_schema.columns" in self._query:
            return (all(column in self._columns for column in self._requested_columns()),)
        return None

    def fetchall(self) -> list[tuple[str, str]]:
        requested = self._requested_columns()
        return [
            (column, nullable)
            for column, nullable in reversed(tuple(self._columns.items()))
            if column in requested
        ]

    def _requested_columns(self) -> tuple[str, ...]:
        raw = self._parameters[-1]
        match raw:
            case str() as column:
                return (column,)
            case tuple() as columns:
                return tuple(columns)
            case list() as columns:
                return tuple(columns)
            case unreachable:
                assert_never(unreachable)


class ServerCursor(ContextFake):
    def __init__(self, batches: tuple[DatabaseBatch, ...]) -> None:
        self._batches = list(batches)
        self.query: sql.Composable | None = None
        self.fetch_sizes: list[int] = []

    def execute(self, query: sql.Composable) -> None:
        self.query = query

    def fetchmany(self, size: int) -> DatabaseBatch:
        self.fetch_sizes.append(size)
        if self._batches:
            return self._batches.pop(0)
        return ()


def _scan_request(primary_key: tuple[ColumnName, ...] = (ColumnName("id"),), batch_size: int = 100) -> ScanRequest:
    return ScanRequest(
        instance=DatabaseInstance(
            instance_id=InstanceId("v2_huashi"),
            role=Role.SOURCE,
            school="华师",
            host="127.0.0.1",
            port=5432,
            database="teaching_v2",
            username="audit",
            password_env="DB_V2_HUASHI_PASSWORD",
            sslmode="disable",
        ),
        table=TableName("public", "activity_nodes"),
        primary_key=primary_key,
        batch_size=batch_size,
    )


def _read_batches(connection: TableContractConnection, request: ScanRequest, secret: str = "reader-secret") -> tuple[tuple[tuple[IdValue, ...], ...], ...]:
    reader = pg_pk_postgres.PgIdReader(environ={"DB_V2_HUASHI_PASSWORD": secret})
    with patch.object(pg_pk_postgres.psycopg, "connect", side_effect=connection.connect):
        return tuple(reader.read_batches(request))


def _table_contract_error(connection: TableContractConnection, request: ScanRequest) -> str:
    try:
        pg_pk_postgres._validate_table_contract(connection, request)
    except pg_pk_postgres.TableContractError as error:
        return str(error)
    raise AssertionError


if __name__ == "__main__":
    unittest.main()
