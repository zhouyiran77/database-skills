# pg-primary-key-conflict-check

`pg-primary-key-conflict-check` is a migration pre-check Skill for detecting primary-key collisions when multiple PostgreSQL school or tenant databases are consolidated into one target database.

It detects two independent conflict dimensions for every logical table:

- The same `id` exists in two or more 2.0 source instances.
- A 2.0 source `id` already exists in the 3.0 target table.

Source and target physical table names may differ. Multiple source mappings can be grouped under the same logical `scope_id`.

## Files

```text
pg-primary-key-conflict-check/
+-- SKILL.md
+-- README.md
+-- assets/
|   +-- config-template.md
+-- references/
|   +-- config-format.md
+-- scripts/
|   +-- pg_pk_conflict.py
|   +-- pg_pk_check.py
|   +-- pg_pk_config.py
|   +-- pg_pk_model.py
|   +-- pg_pk_postgres.py
|   +-- pg_pk_render.py
|   +-- pg_pk_store.py
+-- tests/
+-- evals/
```

## Requirements

- Python 3.12 or newer.
- `uv` for self-contained script execution.
- Network access to every configured PostgreSQL instance.
- Read-only users that can inspect table metadata and select the `id` column.

The entry script declares `psycopg[binary]>=3.2` through PEP 723 metadata, so no project virtual environment or requirements file is needed.

## Quick Start

1. Copy `assets/config-template.md` and fill in the database and table mappings.
2. Set each `password_env` variable in the same runtime that executes the command.
3. Validate the file:

   ```powershell
   uv run scripts/pg_pk_conflict.py migration-check.md --validate-only
   ```

4. Run the check:

   ```powershell
   uv run scripts/pg_pk_conflict.py migration-check.md `
     --output-file pg_pk_conflict_report.md
   ```

Exit code `1` means the scan completed successfully and found conflicts. Exit code `2` means the scan was incomplete because of configuration, connection, or table-contract errors.

## How It Scales

Each PostgreSQL table is read through a server-side cursor in configurable batches. IDs are inserted into a temporary SQLite index on the machine running the Skill. Conflict counts are computed in SQLite, so the process does not keep all source and target IDs in Python memory.

The report contains exact counts and bounded detail rows. Set `--detail-limit 0` to include all conflict IDs.

## Security

- Put only environment variable names in `password_env`; never store passwords or DSNs in Markdown.
- Use read-only PostgreSQL accounts.
- The program performs metadata queries and `SELECT id`; it does not write to PostgreSQL.
- Treat generated reports as sensitive migration artifacts.

## Verification

```powershell
python -m unittest discover -s pg-primary-key-conflict-check/tests
python pg-primary-key-conflict-check/scripts/pg_pk_conflict.py --help
python -m json.tool pg-primary-key-conflict-check/evals/evals.json
```
