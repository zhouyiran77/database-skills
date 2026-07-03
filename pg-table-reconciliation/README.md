# pg-table-reconciliation README

`pg-table-reconciliation` is a Codex skill for comparing PostgreSQL tables between a source database and a target database. It is intended for migration validation, source/target drift checks, schema difference analysis, row-count validation, and migration risk assessment.

## What It Does

- Connects to two different PostgreSQL database instances.
- Supports different users, passwords, hosts, and database names for source and target.
- Supports a single table, multiple tables, or a wildcard range such as `schema.*`.
- Supports fixed table-name prefixes on either side, such as comparing source `public.user` to target `public.edu_user`.
- Compares table existence, missing columns, data types, length, precision, defaults, nullability, and primary keys.
- Supports three data check levels: `none`, `row-count`, and `hash`.
- Outputs Markdown or JSON reports.
- Summarizes migration risks by severity: `critical`, `high`, `medium`, and `low`.

## Directory Layout

```text
pg-table-reconciliation/
+-- SKILL.md
+-- README.md
+-- references/
|   +-- usage.md
+-- scripts/
|   +-- pg_reconcile.py
|   +-- pg_reconcile_core.py
|   +-- pg_reconcile_compare.py
|   +-- pg_reconcile_model.py
|   +-- pg_reconcile_pg.py
|   +-- pg_reconcile_render.py
|   +-- pg_reconcile_risk.py
+-- evals/
|   +-- evals.json
+-- tests/
    +-- test_pg_reconcile_core.py
```

## Requirements

- Python 3.12 or newer.
- PostgreSQL Python driver: `psycopg[binary]>=3.2`.
- `uv` is recommended because it can run the script and install inline dependencies automatically.

If `uv` is not available, install the dependency manually:

```powershell
python -m pip install "psycopg[binary]>=3.2"
```

## Credential Setup

Use environment variables for DSNs. Do not place usernames, passwords, or full connection strings in chat messages, CLI flags, reports, or saved logs.

PowerShell example:

```powershell
$env:PG_RECON_SOURCE_DSN = "postgresql://source_user:source_password@source-host:5432/source_db"
$env:PG_RECON_TARGET_DSN = "postgresql://target_user:target_password@target-host:5432/target_db"
```

Bash example:

```bash
export PG_RECON_SOURCE_DSN='postgresql://source_user:source_password@source-host:5432/source_db'
export PG_RECON_TARGET_DSN='postgresql://target_user:target_password@target-host:5432/target_db'
```

You can also use libpq key-value DSNs. This is often easier when passwords contain special characters:

```powershell
$env:PG_RECON_SOURCE_DSN = "host=source-host port=5432 dbname=source_db user=source_user password=source_password"
$env:PG_RECON_TARGET_DSN = "host=target-host port=5432 dbname=target_db user=target_user password=target_password"
```

Notes:

- Special characters in URI DSNs must be URL-encoded, including `%`, `@`, `#`, `:`, and `/`.
- Do not add unsupported URI query parameters such as `?schema=public`. Select schemas and tables with `--tables "public.*"` or `--tables "public.user"`.
- Prefer read-only database users for both source and target. The script only reads metadata and table data; it does not write to either database.

## Basic Usage

The script is stored under the skill directory at `scripts/pg_reconcile.py`. Avoid hardcoding an absolute path from one machine. Resolve the script path from the directory containing `SKILL.md`.

Detailed command templates, CLI options, prefix mapping examples, report-reading notes, and troubleshooting now live in `references/usage.md`. `SKILL.md` stays intentionally short so Claude Code loads the workflow first and opens the reference only when it needs runnable commands or edge-case guidance.

PowerShell:

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

Bash:

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

Show all CLI options:

```powershell
$skillDir = Split-Path -Parent "path\to\pg-table-reconciliation\SKILL.md"
uv run (Join-Path $skillDir "scripts\pg_reconcile.py") --help
```

## Common Scenarios

### 1. Source and target use identical table names

Compare source `public.user` to target `public.user`:

```powershell
$skillDir = Split-Path -Parent "path\to\pg-table-reconciliation\SKILL.md"
uv run (Join-Path $skillDir "scripts\pg_reconcile.py") `
  --source-dsn-env PG_RECON_SOURCE_DSN `
  --target-dsn-env PG_RECON_TARGET_DSN `
  --tables "public.user,public.school" `
  --data-check row-count `
  --output markdown `
  --output-file pg_reconciliation_report.md
```

### 2. Target tables use the `edu_` prefix

Pass logical table names in `--tables`. The script maps them to prefixed physical target tables:

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

Mapping:

| Logical table | Source physical table | Target physical table |
| --- | --- | --- |
| `public.user` | `public.user` | `public.edu_user` |
| `public.school` | `public.school` | `public.edu_school` |

### 3. Source tables use the `edu_` prefix

Pass logical table names in `--tables`. The script maps them to prefixed physical source tables:

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

### 4. Compare an entire schema

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

`schema.*` expansion is source-driven. The script first reads matching tables from the source database, then compares each resolved logical table to the target.

If `--target-table-prefix edu_` is set with `--tables "public.*"`, source `public.user` maps to target `public.edu_user`.

If `--source-table-prefix edu_` is set with `--tables "public.*"`, the script expands only source tables whose names start with `edu_`, strips that prefix from the logical name, and compares the resulting logical table to the target.

### 5. Output JSON

Use JSON for automation or downstream processing:

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

### 6. Hash check for small tables

`hash` reads table data and generates deterministic signatures. Use it for small tables, lookup tables, or a curated list of important tables. Avoid using it blindly on large tables.

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

## Reading the Report

Markdown reports typically include:

- Summary: number of compared tables, number of tables with differences, and risk distribution.
- Table mapping: logical table, source physical table, and target physical table.
- Schema differences: source-only columns, target-only columns, column metadata differences, and primary-key differences.
- Data checks: row-count differences or hash differences.
- Migration risks: severity, reason, and recommended follow-up action.

Risk levels:

| Level | Meaning |
| --- | --- |
| `critical` | Very likely to block migration or make data unusable, such as a missing target table, missing target column, primary-key mismatch, or incompatible type family. |
| `high` | May cause migration failure or data loss, such as row-count mismatch, a new required target column without a default, or narrowed string/numeric precision. |
| `medium` | Needs human review, such as default changes, nullability changes, datetime precision changes, or hash mismatch. |
| `low` | Usually does not block migration but should be recorded, such as extra nullable/defaulted target columns. |

## Calling the Skill from Codex

Example prompt:

```text
[$pg-table-reconciliation](path\to\pg-table-reconciliation\SKILL.md)
Use the pg-table-reconciliation skill.
Source DSN environment variable: PG_RECON_SOURCE_DSN
Target DSN environment variable: PG_RECON_TARGET_DSN
Target table prefix: edu_
Comparison scope: public.*
Check level: row-count
Output format: markdown
Report file: pg_reconciliation_report.md
```

If source and target tables use the same names, omit both the source and target table prefix lines.

## Troubleshooting

### Missing environment variable

The script will report that `PG_RECON_SOURCE_DSN` or `PG_RECON_TARGET_DSN` is missing. Set the environment variable in the same terminal or Codex runtime environment, then run the command again.

### URI DSN reports a percent-encoding error

If the password contains special characters such as `%`, `@`, `#`, `:`, or `/`, the URI DSN must be URL-encoded. You can also switch to a libpq key-value DSN:

```text
host=db-host port=5432 dbname=my_db user=my_user password=my_password
```

### Unsupported URI query parameters

Do not use connection strings such as `postgresql://.../db?schema=public`. Select schemas and tables with `--tables "public.*"`.

### Target table is missing

If the report says the target table is missing, check:

- Whether `--target-table-prefix edu_` should be set.
- Whether `--tables` contains logical table names instead of already-prefixed physical table names.
- Whether the schema is correct. For example, `public.user` and `edu.user` are different table scopes.

### `public.*` plus a prefix maps unwanted system or migration tables

For example, if the source has `_prisma_migrations` and the target prefix is `edu_`, it may map to `edu__prisma_migrations`. If these tables should not participate in migration validation, explicitly list business tables instead:

```powershell
--tables "public.user,public.school,public.course"
```

### Hash checks are slow

`hash` reads table data. Use `row-count` first for large tables, then enable `hash` only for selected important tables with a reasonable `--hash-row-limit`.

## Safety Guidance

- Use read-only database users.
- Do not expose real passwords in chat, command arguments, or report files.
- Before running a broad `public.*` comparison, confirm whether the schema contains temporary tables, migration metadata tables, or historical tables that should be excluded.
- Start with `row-count` for large tables, then use `hash` on a smaller table set if needed.
- Reports may contain sensitive metadata such as table names, column names, and row counts. Store and share them according to your internal security policy.

## Local Verification

After changing the skill or script, run:

```powershell
python -m unittest discover -s "path\to\pg-table-reconciliation\tests"
python "path\to\pg-table-reconciliation\scripts\pg_reconcile.py" --help
```
