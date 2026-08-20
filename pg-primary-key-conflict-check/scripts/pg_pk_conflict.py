#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "psycopg[binary]>=3.2",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv or pip install needed):
#      uv run pg_pk_conflict.py CONFIG.md --output-file REPORT.md
# 3. Validate configuration without connecting:
#      uv run pg_pk_conflict.py CONFIG.md --validate-only
# ──────────────────

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import sys

from pg_pk_check import execute_check
from pg_pk_config import parse_markdown_config
from pg_pk_model import PkConflictError, RunOptions
from pg_pk_postgres import PgIdReader
from pg_pk_render import render_markdown


@dataclass(frozen=True, slots=True)
class CliArgs:
    config: Path
    output_file: Path
    batch_size: int
    detail_limit: int
    validate_only: bool


def main() -> int:
    args = _parse_args()
    try:
        markdown = args.config.read_text(encoding="utf-8")
        config = parse_markdown_config(markdown)
        if args.validate_only:
            print(f"配置有效：{len(config.instances)} 个数据库实例，{len(config.scopes)} 个逻辑表。")
            return 0
        report = execute_check(
            config,
            PgIdReader(environ=os.environ),
            RunOptions(batch_size=args.batch_size, detail_limit=args.detail_limit),
        )
        rendered = render_markdown(config, report)
        args.output_file.write_text(rendered, encoding="utf-8")
        print(f"报告已写入：{args.output_file}")
        return 1 if report.has_conflicts() else 0
    except PkConflictError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError) as exc:
        print(f"错误：无法读取或写入文件：{exc}", file=sys.stderr)
        return 2


def _parse_args() -> CliArgs:
    parser = argparse.ArgumentParser(
        description="检测多个 PostgreSQL 2.0 来源实例之间及其与 3.0 目标实例之间的主键 ID 冲突。",
    )
    parser.add_argument("config", type=Path, help="Markdown 配置文件")
    parser.add_argument(
        "--output-file",
        type=Path,
        default=Path("pg_pk_conflict_report.md"),
        help="Markdown 报告路径",
    )
    parser.add_argument("--batch-size", type=int, default=10_000, help="PostgreSQL 每批读取的 ID 数量")
    parser.add_argument(
        "--detail-limit",
        type=int,
        default=1_000,
        help="每类冲突最多展示的明细数；0 表示不限制",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="仅验证 Markdown 结构，不连接数据库",
    )
    namespace = parser.parse_args()
    return CliArgs(
        config=namespace.config,
        output_file=namespace.output_file,
        batch_size=namespace.batch_size,
        detail_limit=namespace.detail_limit,
        validate_only=namespace.validate_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())
