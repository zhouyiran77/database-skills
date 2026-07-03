from __future__ import annotations

import os
from dataclasses import dataclass

import psycopg
from psycopg import sql

from pg_reconcile_compare import build_table_report, missing_target_report
from pg_reconcile_model import ColumnDef, DataCheck, TableMapping, TableName, TableReport, table_without_prefix


@dataclass(frozen=True, slots=True)
class RunConfig:
    source_dsn_env: str
    target_dsn_env: str
    table_spec: str
    data_check: DataCheck
    hash_row_limit: int
    source_table_prefix: str = ""
    target_table_prefix: str = ""


@dataclass(frozen=True, slots=True)
class PgRepository:
    conn: psycopg.Connection

    def resolve_tables(self, spec: str, source_table_prefix: str) -> tuple[TableName, ...]:
        tables: list[TableName] = []
        for raw in spec.split(","):
            item = TableName.parse(raw)
            if item.name == "*":
                tables.extend(table_without_prefix(table, source_table_prefix) for table in self._tables_in_schema(item.schema, source_table_prefix))
            else:
                tables.append(item)
        return tuple(tables)

    def table_exists(self, table: TableName) -> bool:
        query = """
        select exists (
          select 1 from information_schema.tables
          where table_schema = %s and table_name = %s and table_type = 'BASE TABLE'
        )
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (table.schema, table.name))
            row = cur.fetchone()
        return bool(row[0]) if row else False

    def columns(self, table: TableName) -> tuple[ColumnDef, ...]:
        query = """
        select column_name, ordinal_position, data_type, udt_name, is_nullable,
               column_default, character_maximum_length, numeric_precision,
               numeric_scale, datetime_precision
        from information_schema.columns
        where table_schema = %s and table_name = %s
        order by ordinal_position
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (table.schema, table.name))
            rows = cur.fetchall()
        return tuple(_column_from_row(row) for row in rows)

    def primary_key(self, table: TableName) -> tuple[str, ...]:
        query = """
        select kcu.column_name
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu
          on tc.constraint_name = kcu.constraint_name
         and tc.table_schema = kcu.table_schema
         and tc.table_name = kcu.table_name
        where tc.constraint_type = 'PRIMARY KEY'
          and tc.table_schema = %s
          and tc.table_name = %s
        order by kcu.ordinal_position
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (table.schema, table.name))
            rows = cur.fetchall()
        return tuple(row[0] for row in rows)

    def row_count(self, table: TableName) -> int:
        query = sql.SQL("select count(*) from {}").format(_qualified(table))
        with self.conn.cursor() as cur:
            cur.execute(query)
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def table_hash(self, table: TableName, columns: tuple[str, ...], limit: int) -> str | None:
        if not columns:
            return None
        ordered = sql.SQL(", ").join(sql.Identifier(col) for col in columns)
        query = sql.SQL(
            """
            select md5(coalesce(string_agg(row_sig, '' order by row_sig), ''))
            from (
              select md5(row_to_json(t)::text) as row_sig
              from (select {columns} from {table} order by {columns} limit %s) t
            ) s
            """,
        ).format(columns=ordered, table=_qualified(table))
        with self.conn.cursor() as cur:
            cur.execute(query, (limit,))
            row = cur.fetchone()
        return str(row[0]) if row and row[0] else None

    def _tables_in_schema(self, schema: str, source_table_prefix: str) -> tuple[TableName, ...]:
        query = """
        select table_name
        from information_schema.tables
        where table_schema = %s and table_type = 'BASE TABLE' and table_name like %s
        order by table_name
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (schema, f"{source_table_prefix}%"))
            rows = cur.fetchall()
        return tuple(TableName(schema=schema, name=row[0]) for row in rows)


@dataclass(frozen=True, slots=True)
class CompareContext:
    source: PgRepository
    target: PgRepository
    config: RunConfig


@dataclass(frozen=True, slots=True)
class MissingDsnError(Exception):
    env_name: str

    def __str__(self) -> str:
        return f"Environment variable {self.env_name} is not set."


def reconcile(config: RunConfig) -> tuple[TableReport, ...]:
    with connect_from_env(config.source_dsn_env) as source_conn, connect_from_env(config.target_dsn_env) as target_conn:
        context = CompareContext(PgRepository(source_conn), PgRepository(target_conn), config)
        reports: list[TableReport] = []
        for table in context.source.resolve_tables(config.table_spec, config.source_table_prefix):
            reports.append(_compare_one(context, table))
    return tuple(reports)


def connect_from_env(env_name: str) -> psycopg.Connection:
    dsn = os.environ.get(env_name)
    if not dsn:
        raise MissingDsnError(env_name=env_name)
    return psycopg.connect(dsn)


def _compare_one(context: CompareContext, table: TableName) -> TableReport:
    mapping = TableMapping.from_prefixes(table, context.config.source_table_prefix, context.config.target_table_prefix)
    source_columns = context.source.columns(mapping.source)
    source_rows = context.source.row_count(mapping.source) if context.config.data_check != DataCheck.NONE else None
    if not context.target.table_exists(mapping.target):
        return missing_target_report(table, source_columns, source_rows, mapping.report_label())
    target_columns = context.target.columns(mapping.target)
    source_pk = context.source.primary_key(mapping.source)
    target_pk = context.target.primary_key(mapping.target)
    target_rows = context.target.row_count(mapping.target) if context.config.data_check != DataCheck.NONE else None
    source_hash, target_hash = _hashes(context, mapping, source_columns, target_columns)
    return build_table_report(table, source_columns, target_columns, (source_rows, target_rows, source_hash, target_hash), (source_pk, target_pk), mapping.report_label())


def _hashes(
    context: CompareContext,
    mapping: TableMapping,
    source_columns: tuple[ColumnDef, ...],
    target_columns: tuple[ColumnDef, ...],
) -> tuple[str | None, str | None]:
    if context.config.data_check != DataCheck.HASH:
        return None, None
    target_names = {col.name for col in target_columns}
    names = tuple(col.name for col in source_columns if col.name in target_names)
    return (
        context.source.table_hash(mapping.source, names, context.config.hash_row_limit),
        context.target.table_hash(mapping.target, names, context.config.hash_row_limit),
    )


def _qualified(table: TableName) -> sql.Composed:
    return sql.Identifier(table.schema, table.name)


def _column_from_row(row: tuple[str, int, str, str, str, str | None, int | None, int | None, int | None, int | None]) -> ColumnDef:
    return ColumnDef(
        name=row[0],
        ordinal_position=row[1],
        data_type=row[2],
        udt_name=row[3],
        is_nullable=row[4],
        column_default=row[5],
        character_maximum_length=row[6],
        numeric_precision=row[7],
        numeric_scale=row[8],
        datetime_precision=row[9],
    )
