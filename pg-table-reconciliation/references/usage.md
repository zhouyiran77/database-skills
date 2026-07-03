# PostgreSQL Reconciliation Usage

This reference contains detailed command templates and troubleshooting for the `pg-table-reconciliation` skill. Read it after `SKILL.md` when the user needs a concrete command or asks about edge cases.

## Requirements

- Python 3.12 or newer when using `uv run` with the script metadata.
- `psycopg[binary]>=3.2`.
- Read-only PostgreSQL users for source and target databases.

If `uv` is not available:

```powershell
python -m pip install "psycopg[binary]>=3.2"
```

## Credential Setup

Use environment variables for DSNs. Ask the user to set them in their own terminal/runtime. Do not ask them to paste passwords into chat.

PowerShell:

```powershell
$env:PG_RECON_SOURCE_DSN = "postgresql://source_user:source_password@source-host:5432/source_db"
$env:PG_RECON_TARGET_DSN = "postgresql://target_user:target_password@target-host:5432/target_db"
```

Bash:

```bash
export PG_RECON_SOURCE_DSN='postgresql://source_user:source_password@source-host:5432/source_db'
export PG_RECON_TARGET_DSN='postgresql://target_user:target_password@target-host:5432/target_db'
```

When passwords contain special characters, libpq key-value DSNs are often easier:

```text
host=source-host port=5432 dbname=source_db user=source_user password=source_password
```

Special characters in URI DSNs must be URL-encoded, including `%`, `@`, `#`, `:`, and `/`.

## Locate The Script

PowerShell:

```powershell
$skillDir = Split-Path -Parent "path\to\pg-table-reconciliation\SKILL.md"
uv run (Join-Path $skillDir "scripts\pg_reconcile.py") --help
```

Bash:

```bash
SKILL_DIR="$(dirname /path/to/pg-table-reconciliation/SKILL.md)"
uv run "$SKILL_DIR/scripts/pg_reconcile.py" --help
```

## Standard Commands

Schema and row-count validation:

```powershell
$skillDir = Split-Path -Parent "path\to\pg-table-reconciliation\SKILL.md"
uv run (Join-Path $skillDir "scripts\pg_reconcile.py") `
  --source-dsn-env PG_RECON_SOURCE_DSN `
  --target-dsn-env PG_RECON_TARGET_DSN `
  --tables "public.student,public.course" `
  --data-check row-count `
  --output markdown `
  --output-file pg_reconciliation_report.md
```

Entire schema:

```powershell
$skillDir = Split-Path -Parent "path\to\pg-table-reconciliation\SKILL.md"
uv run (Join-Path $skillDir "scripts\pg_reconcile.py") `
  --source-dsn-env PG_RECON_SOURCE_DSN `
  --target-dsn-env PG_RECON_TARGET_DSN `
  --tables "public.*" `
  --data-check row-count `
  --output markdown `
  --output-file pg_reconciliation_report.md
```

Target tables use a prefix:

```powershell
$skillDir = Split-Path -Parent "path\to\pg-table-reconciliation\SKILL.md"
uv run (Join-Path $skillDir "scripts\pg_reconcile.py") `
  --source-dsn-env PG_RECON_SOURCE_DSN `
  --target-dsn-env PG_RECON_TARGET_DSN `
  --tables "public.user,public.school" `
  --target-table-prefix edu_ `
  --data-check row-count `
  --output markdown `
  --output-file pg_reconciliation_report.md
```

Source tables use a prefix:

```powershell
$skillDir = Split-Path -Parent "path\to\pg-table-reconciliation\SKILL.md"
uv run (Join-Path $skillDir "scripts\pg_reconcile.py") `
  --source-dsn-env PG_RECON_SOURCE_DSN `
  --target-dsn-env PG_RECON_TARGET_DSN `
  --tables "public.user,public.school" `
  --source-table-prefix edu_ `
  --data-check row-count `
  --output markdown `
  --output-file pg_reconciliation_report.md
```

Automation-friendly JSON:

```powershell
$skillDir = Split-Path -Parent "path\to\pg-table-reconciliation\SKILL.md"
uv run (Join-Path $skillDir "scripts\pg_reconcile.py") `
  --source-dsn-env PG_RECON_SOURCE_DSN `
  --target-dsn-env PG_RECON_TARGET_DSN `
  --tables "public.*" `
  --data-check row-count `
  --output json `
  --output-file pg_reconciliation_report.json
```

Hash check for small or selected tables:

```powershell
$skillDir = Split-Path -Parent "path\to\pg-table-reconciliation\SKILL.md"
uv run (Join-Path $skillDir "scripts\pg_reconcile.py") `
  --source-dsn-env PG_RECON_SOURCE_DSN `
  --target-dsn-env PG_RECON_TARGET_DSN `
  --tables "public.lookup_codes" `
  --data-check hash `
  --hash-row-limit 200000 `
  --output markdown `
  --output-file pg_reconciliation_report.md
```

## Bash Form

```bash
SKILL_DIR="$(dirname /path/to/pg-table-reconciliation/SKILL.md)"
uv run "$SKILL_DIR/scripts/pg_reconcile.py" \
  --source-dsn-env PG_RECON_SOURCE_DSN \
  --target-dsn-env PG_RECON_TARGET_DSN \
  --tables "public.*" \
  --data-check row-count \
  --output markdown \
  --output-file pg_reconciliation_report.md
```

## CLI Options

| Option | Default | Description |
| --- | --- | --- |
| `--source-dsn-env` | `PG_RECON_SOURCE_DSN` | Environment variable containing the source database DSN. |
| `--target-dsn-env` | `PG_RECON_TARGET_DSN` | Environment variable containing the target database DSN. |
| `--tables` | `public.*` | Comparison scope. Supports `schema.table`, comma-separated table lists, and `schema.*`. |
| `--data-check` | `row-count` | Data check level: `none`, `row-count`, or `hash`. |
| `--hash-row-limit` | `200000` | Maximum number of rows to read for hash checks. |
| `--source-table-prefix` | empty | Physical table-name prefix on the source side, such as `edu_`. |
| `--target-table-prefix` | empty | Physical table-name prefix on the target side, such as `edu_`. |
| `--output` | `markdown` | Output format: `markdown` or `json`. |
| `--output-file` | empty | Report file path. If omitted, the report is printed to stdout. |

## Table Prefix Mapping

Pass logical table names in `--tables`. The script applies prefixes to physical table access.

| Logical table | Source prefix | Target prefix | Source physical table | Target physical table |
| --- | --- | --- | --- | --- |
| `public.user` | empty | `edu_` | `public.user` | `public.edu_user` |
| `public.user` | `edu_` | empty | `public.edu_user` | `public.user` |
| `public.user` | `old_` | `new_` | `public.old_user` | `public.new_user` |

For `schema.*`, expansion is source-driven. If `--source-table-prefix edu_` is set, the script expands only source tables whose names start with `edu_`, then strips that prefix from the logical report name.

## Reading The Report

Markdown reports include:

- Summary counts for checked tables and risks by severity.
- Per-table mapping from logical name to source and target physical names.
- Schema differences: source-only columns, target-only columns, metadata differences, and primary-key differences.
- Data checks: row-count differences or hash differences.
- Migration risks with severity, reason, and recommended follow-up.

Prioritize `critical` and `high` findings. `medium` findings usually need human review. `low` findings are usually acceptable but should be recorded.

## Troubleshooting

Missing environment variable:

Set `PG_RECON_SOURCE_DSN` or `PG_RECON_TARGET_DSN` in the same terminal or runtime environment that runs the command.

URI DSN percent-encoding errors:

URL-encode special characters in URI DSNs, or switch to libpq key-value DSNs.

Unsupported URI query parameters:

Do not use `postgresql://.../db?schema=public`. Select schemas and tables with `--tables "public.*"` or `--tables "public.user"`.

Target table is missing:

- Check whether `--target-table-prefix` should be set.
- Check whether `--tables` contains logical names instead of already-prefixed physical names.
- Check whether the schema is correct.

Wildcard scope includes unwanted tables:

Use an explicit table list when `schema.*` would include migration metadata, temporary, audit, historical, or otherwise irrelevant tables.

Hash checks are slow:

Start with `row-count` for large tables. Use `hash` only for selected important tables with a reasonable `--hash-row-limit`.

## Local Verification

After changing the skill or script:

```powershell
python -m unittest discover -s "path\to\pg-table-reconciliation\tests"
python "path\to\pg-table-reconciliation\scripts\pg_reconcile.py" --help
```
