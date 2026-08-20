---
name: pg-primary-key-conflict-check
description: "Use this skill whenever a PostgreSQL migration consolidates multiple school, tenant, regional, sharded, or legacy database instances into one target instance and primary-key IDs may collide. It parses a Markdown instance/table-mapping configuration, connects automatically with passwords supplied through environment variables, detects duplicate `id` values across 2.0 source instances, and detects source IDs that already exist in the 3.0 target. Prefer this skill for pre-migration PK collision checks, multi-instance merge validation, id_generator collision analysis, school-database consolidation, and source-to-target primary-key conflict reports, even when physical table names differ."
compatibility: "Python 3.12+, uv, network access to PostgreSQL, and read-only database credentials"
---

# PostgreSQL Primary-Key Conflict Check

Use this skill before merging independently generated PostgreSQL IDs from multiple source instances into a shared target instance.

## Core Rule

Run the bundled deterministic script instead of composing ad hoc cross-database SQL:

```text
scripts/pg_pk_conflict.py
```

Resolve the script relative to this `SKILL.md`. Use `uv run` so the PEP 723 dependency metadata installs the PostgreSQL driver automatically.

## Required Input

Ask the user for one Markdown configuration file. It must contain:

1. `## 数据库实例`: source and target connection metadata.
2. `## 表比对范围`: logical-table scopes and source-to-target physical table mappings.

Use `assets/config-template.md` as the starting template. Read `references/config-format.md` for exact fields, repeated `scope_id` behavior, and validation rules.

Passwords must stay outside the Markdown file. Each database row contains a `password_env` name, and the user sets the corresponding environment variable locally. Never ask the user to paste a password or full DSN into chat.

## Workflow

1. Confirm the databases are PostgreSQL and the supplied accounts are read-only.
2. Inspect the Markdown file for plaintext password or DSN columns. The script rejects them; direct the user to `password_env` instead.
3. Validate the structure without connecting:

   ```powershell
   uv run scripts/pg_pk_conflict.py path\to\config.md --validate-only
   ```

4. Confirm every configured password environment variable is visible to the same runtime that will execute the script. Check presence only; never print values.
5. Run the complete check:

   ```powershell
   uv run scripts/pg_pk_conflict.py path\to\config.md `
     --output-file pg_pk_conflict_report.md
   ```

6. Read the generated report and summarize findings by `scope_id`. Lead with tables that have conflicts.
7. Explain both dimensions separately:
   - `2.0来源库之间`: the same ID exists in at least two source instances.
   - `2.0与3.0`: a source ID already exists in the configured target table.

## Exit Codes

| Code | Meaning | Agent action |
|---:|---|---|
| `0` | Check completed with no conflicts | Report the migration pre-check as passed. |
| `1` | Check completed and conflicts were found | Treat this as an expected finding, not a script failure; open and summarize the report. |
| `2` | Configuration, secret, connection, table, or query error | Do not claim the table is conflict-free. Resolve the error and rerun. |

## Table and ID Rules

- The v1 implementation supports PostgreSQL only.
- The physical source and target table names may differ and must use `schema.table` format.
- The v1 primary key must be the single column `id`.
- The script verifies that each physical table exists and that its actual PostgreSQL primary key is exactly `(id)` before reading rows.
- Repeated rows with the same `scope_id` are merged. This supports one school using a different 2.0 physical table name.
- `source_instances: *` expands to every database row whose role is `source`.

## Scale and Reporting

The script streams IDs with a PostgreSQL server-side cursor and stores observations in a temporary local SQLite index. It does not retain every ID in Python memory. The temporary index is removed at the end of the run.

The report always contains exact conflict counts. Detail rows default to 1,000 per conflict type and logical table. Use `--detail-limit 0` only when the user explicitly needs every conflicting ID and accepts a potentially large report.

Tune `--batch-size` only when needed. The default of 10,000 balances round trips and memory use for typical bigint primary keys.

## Safety

- Use read-only PostgreSQL users. The reader also requests a read-only transaction mode.
- The script never updates source or target databases and never remaps IDs.
- Do not save plaintext passwords, full DSNs, or secret values in Markdown, commands, logs, reports, or chat.
- Reports expose school names, instance aliases, physical table names, row counts, and conflicting IDs; handle them as migration-sensitive data.
- A connection or table-contract error invalidates the check. Never interpret an incomplete run as “no conflicts.”

## Detailed Reference

Read `references/config-format.md` when creating or troubleshooting the Markdown configuration.
