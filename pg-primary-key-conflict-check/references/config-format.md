# Markdown Configuration Format

The input is one Markdown file with two required sections. Heading names and column names are stable parser contracts.

## Database Instances

Use the heading `## 数据库实例` and these columns:

| Column | Required value |
|---|---|
| `instance_id` | Unique alias beginning with a letter and containing only letters, digits, or underscores. |
| `role` | `source` for a 2.0 database or `target` for a 3.0 database. |
| `school` | Human-readable school or target label used in reports. |
| `db_type` | `postgresql` in v1. |
| `host` | PostgreSQL host name or IP address. |
| `port` | Integer from 1 to 65535. |
| `database` | Database name. |
| `username` | Prefer a read-only migration-audit user. |
| `password_env` | Environment variable name containing the password. |
| `sslmode` | `disable`, `allow`, `prefer`, `require`, `verify-ca`, or `verify-full`. |

The parser rejects columns named `password`, `dsn`, or `connection_string` because configuration files are likely to be committed or shared.

## Comparison Scopes

Use the heading `## 表比对范围` and these columns:

| Column | Required value |
|---|---|
| `scope_id` | Logical table identifier used to group mappings and report results. |
| `enabled` | `true` or `false`. Disabled rows are ignored. |
| `source_instances` | `*` for every source, or comma-separated source instance aliases. |
| `source_table` | Source physical table in `schema.table` format. |
| `target_instance` | Alias of a database row whose role is `target`. |
| `target_table` | Target physical table in `schema.table` format. |
| `primary_key` | Must be `id` in v1. The field name is retained for compatibility, but `id` is treated as the comparison column and does not need to be independently unique. |

## Different Source Table Names

Repeat a `scope_id` when one source uses a different physical table:

```markdown
| scope_id | enabled | source_instances | source_table | target_instance | target_table | primary_key |
|---|---|---|---|---|---|---|
| activity_nodes | true | v2_huashi,v2_wut | public.activity_nodes | v3_main | teaching.activity_node | id |
| activity_nodes | true | v2_gdei | legacy.activity_node | v3_main | teaching.activity_node | id |
```

Rows in the same scope must use the same `target_instance`, `target_table`, and `primary_key`. A source instance may appear only once in a scope.

## Environment Variables

PowerShell:

```powershell
$env:DB_V2_HUASHI_PASSWORD = "set-locally"
$env:DB_V2_WUT_PASSWORD = "set-locally"
$env:DB_V2_GDEI_PASSWORD = "set-locally"
$env:DB_V3_MAIN_PASSWORD = "set-locally"
```

Bash:

```bash
export DB_V2_HUASHI_PASSWORD='set-locally'
export DB_V2_WUT_PASSWORD='set-locally'
export DB_V2_GDEI_PASSWORD='set-locally'
export DB_V3_MAIN_PASSWORD='set-locally'
```

Set variables in the same process environment that runs the Skill. On Windows, variables set in a separate PowerShell window after Codex or Claude Code started may not be visible to the already-running process.

## Validation and Execution

```powershell
uv run scripts/pg_pk_conflict.py migration-check.md --validate-only
uv run scripts/pg_pk_conflict.py migration-check.md --output-file pg_pk_conflict_report.md
```

Optional controls:

| Option | Default | Meaning |
|---|---:|---|
| `--batch-size` | `10000` | IDs fetched from PostgreSQL per server-side cursor batch. |
| `--detail-limit` | `1000` | Maximum detail rows per conflict type and scope; `0` means unlimited. |
| `--output-file` | `pg_pk_conflict_report.md` | Markdown report path. |
| `--validate-only` | off | Parse and validate configuration without reading passwords or connecting. |

## Database Contract Checks

Before scanning data, the script verifies each mapped physical table:

- The table exists as a PostgreSQL base table.
- The configured `id` comparison column exists.

The actual PostgreSQL primary key may be composite, such as `(id, group_id)`. Repeated `id` values inside one instance are deduplicated before conflict analysis. They become `2.0来源库之间` conflicts only when the same value appears in at least two source instances configured under the same `scope_id`.

Any failure stops the run with exit code `2`. This prevents missing tables or incorrect mappings from being reported as conflict-free.
