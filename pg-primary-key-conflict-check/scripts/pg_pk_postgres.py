from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from pg_pk_model import IdValue, InstanceId, PkConflictError, ScanRequest


@dataclass(frozen=True, slots=True)
class MissingSecretError(PkConflictError):
    instance_id: InstanceId
    env_name: str

    def __str__(self) -> str:
        return f"instance {self.instance_id} requires password environment variable {self.env_name}"


@dataclass(frozen=True, slots=True)
class TableContractError(PkConflictError):
    instance_id: InstanceId
    table: str
    reason: str

    def __str__(self) -> str:
        return f"instance {self.instance_id} table {self.table}: {self.reason}"


@dataclass(frozen=True, slots=True)
class DatabaseScanError(PkConflictError):
    instance_id: InstanceId
    reason: str

    def __str__(self) -> str:
        return f"instance {self.instance_id} database scan failed: {self.reason}"


@dataclass(frozen=True, slots=True)
class PgIdReader:
    environ: Mapping[str, str]

    def read_batches(self, request: ScanRequest) -> Iterator[tuple[tuple[IdValue, ...], ...]]:
        password = self.environ.get(request.instance.password_env)
        if not password:
            raise MissingSecretError(
                instance_id=request.instance.instance_id,
                env_name=request.instance.password_env,
            )
        conninfo = make_conninfo(
            "",
            host=request.instance.host,
            port=request.instance.port,
            dbname=request.instance.database,
            user=request.instance.username,
            password=password,
            sslmode=request.instance.sslmode,
            connect_timeout=10,
            application_name="pg-primary-key-conflict-check",
            options="-c default_transaction_read_only=on",
        )
        try:
            with psycopg.connect(conninfo) as connection:
                _validate_table_contract(connection, request)
                query = sql.SQL("SELECT {} FROM {}").format(
                    sql.SQL(", ").join(
                        sql.SQL("{}::text").format(sql.Identifier(column))
                        for column in request.primary_key
                    ),
                    sql.Identifier(request.table.schema, request.table.name),
                )
                with connection.cursor(name="pk_conflict_scan") as cursor:
                    cursor.execute(query)
                    while rows := cursor.fetchmany(request.batch_size):
                        keys: list[tuple[IdValue, ...]] = []
                        for row in rows:
                            key: list[IdValue] = []
                            for index, component in enumerate(row):
                                if component is None:
                                    raise TableContractError(
                                        instance_id=request.instance.instance_id,
                                        table=request.table.label(),
                                        reason=(
                                            "query returned null for comparison column "
                                            f"{request.primary_key[index]}"
                                        ),
                                    )
                                key.append(IdValue(str(component)))
                            keys.append(tuple(key))
                        yield tuple(keys)
        except psycopg.Error as exc:
            raise DatabaseScanError(
                instance_id=request.instance.instance_id,
                reason=database_error_reason(exc),
            ) from exc


def database_error_reason(error: psycopg.Error) -> str:
    return type(error).__name__


def _validate_table_contract(connection: psycopg.Connection, request: ScanRequest) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS ("
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = %s AND table_type = 'BASE TABLE')",
            (request.table.schema, request.table.name),
        )
        existence = cursor.fetchone()
        if existence is None or not bool(existence[0]):
            raise TableContractError(
                instance_id=request.instance.instance_id,
                table=request.table.label(),
                reason="table does not exist",
            )
        cursor.execute(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s AND column_name = ANY(%s)",
            (request.table.schema, request.table.name, list(request.primary_key)),
        )
        nullability = {str(row[0]): str(row[1]) for row in cursor.fetchall()}
        missing = tuple(column for column in request.primary_key if column not in nullability)
        if missing:
            reason = (
                f"comparison column {missing[0]} does not exist"
                if len(missing) == 1
                else f"comparison columns do not exist: {', '.join(missing)}"
            )
            raise TableContractError(
                instance_id=request.instance.instance_id,
                table=request.table.label(),
                reason=reason,
            )
        nullable = tuple(column for column in request.primary_key if nullability[column] != "NO")
        if nullable:
            reason = (
                f"comparison column {nullable[0]} is nullable"
                if len(nullable) == 1
                else f"comparison columns are nullable: {', '.join(nullable)}"
            )
            raise TableContractError(
                instance_id=request.instance.instance_id,
                table=request.table.label(),
                reason=reason,
            )
