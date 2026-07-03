#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "psycopg[binary]>=3.2",
# ]
# ///
# ---- How to run ------------------------------------------------------------
# uv run path/to/pg-table-reconciliation/scripts/pg_reconcile.py --help

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from pg_reconcile_model import parse_data_check
from pg_reconcile_render import OutputConfig, write_output


@dataclass(frozen=True, slots=True)
class CliArgs:
    source_dsn_env: str
    target_dsn_env: str
    tables: str
    data_check: str
    hash_row_limit: int
    source_table_prefix: str
    target_table_prefix: str
    output: str
    output_file: Path | None


def main() -> None:
    args = parse_args()
    from pg_reconcile_pg import RunConfig, reconcile

    run_config = RunConfig(
        source_dsn_env=args.source_dsn_env,
        target_dsn_env=args.target_dsn_env,
        table_spec=args.tables,
        data_check=parse_data_check(args.data_check),
        hash_row_limit=args.hash_row_limit,
        source_table_prefix=args.source_table_prefix,
        target_table_prefix=args.target_table_prefix,
    )
    reports = reconcile(run_config)
    write_output(reports, OutputConfig(output=args.output, output_file=args.output_file))


def parse_args() -> CliArgs:
    parser = argparse.ArgumentParser(description="Compare PostgreSQL source and target table state.")
    parser.add_argument("--source-dsn-env", default="PG_RECON_SOURCE_DSN")
    parser.add_argument("--target-dsn-env", default="PG_RECON_TARGET_DSN")
    parser.add_argument("--tables", default="public.*")
    parser.add_argument("--data-check", default="row-count", choices=["none", "row-count", "hash"])
    parser.add_argument("--hash-row-limit", type=int, default=200_000)
    parser.add_argument("--source-table-prefix", default="")
    parser.add_argument("--target-table-prefix", default="")
    parser.add_argument("--output", default="markdown", choices=["markdown", "json"])
    parser.add_argument("--output-file", type=Path)
    namespace = parser.parse_args()
    return CliArgs(
        source_dsn_env=namespace.source_dsn_env,
        target_dsn_env=namespace.target_dsn_env,
        tables=namespace.tables,
        data_check=namespace.data_check,
        hash_row_limit=namespace.hash_row_limit,
        source_table_prefix=namespace.source_table_prefix,
        target_table_prefix=namespace.target_table_prefix,
        output=namespace.output,
        output_file=namespace.output_file,
    )


if __name__ == "__main__":
    main()
