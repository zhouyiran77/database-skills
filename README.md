# Database Skills

This repository collects reusable Codex/Claude Code skills for database operations, migration validation, and data quality workflows.

Each skill lives in its own directory and includes a required `SKILL.md`. Larger skills can include scripts, references, tests, assets, and eval prompts.

## Skills

| Skill | Status | Use When | Entry Point |
| --- | --- | --- | --- |
| `pg-table-reconciliation` | Ready | Compare PostgreSQL tables across source and target databases, validate migrations, inspect schema drift, compare row counts or hashes, and assess migration risks. | [`pg-table-reconciliation/SKILL.md`](pg-table-reconciliation/SKILL.md) |

## Install With npx

Install a skill from this repository with the `skills` CLI through `npx`:

```text
https://github.com/zhouyiran77/database-skills
```

Install into Claude Code globally:

```bash
npx skills add zhouyiran77/database-skills --skill pg-table-reconciliation --agent claude-code --global
```

Install into the current project instead of globally:

```bash
npx skills add zhouyiran77/database-skills --skill pg-table-reconciliation --agent claude-code
```

Install from the full GitHub URL if your CLI version expects a URL:

```bash
npx skills add https://github.com/zhouyiran77/database-skills --skill pg-table-reconciliation --agent claude-code --global
```

The installed Claude Code skill should end up under one of these locations:

```text
~/.claude/skills/pg-table-reconciliation/
<project>/.claude/skills/pg-table-reconciliation/
```

If the `skills` CLI changes or is unavailable, install manually by copying the skill directory to the Claude Code skills directory:

```bash
mkdir -p ~/.claude/skills
cp -R pg-table-reconciliation ~/.claude/skills/
```

## Repository Layout

```text
database-skills/
+-- README.md
+-- <skill-name>/
    +-- SKILL.md
    +-- README.md
    +-- references/
    +-- scripts/
    +-- tests/
    +-- evals/
```

Recommended skill directory contents:

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Required skill metadata and concise operating instructions. Keep this focused so it loads quickly. |
| `README.md` | Human-facing documentation for the skill. |
| `references/` | Detailed usage notes, command templates, troubleshooting, or domain references loaded only when needed. |
| `scripts/` | Deterministic helper scripts used by the skill. |
| `tests/` | Unit tests or smoke tests for bundled scripts. |
| `evals/` | Skill test prompts and expected behavior for future iteration. |
| `assets/` | Optional templates or static files used by the skill. |

## Adding A Skill

1. Create a new directory using a stable, lowercase, hyphenated name.
2. Add `SKILL.md` with `name` and `description` frontmatter.
3. Keep `SKILL.md` concise. Move long examples, command catalogs, schemas, and troubleshooting into `references/`.
4. Add deterministic scripts under `scripts/` when the workflow should not rely on ad hoc agent behavior.
5. Add focused tests for scripts and data transforms.
6. Add 2-3 realistic prompts under `evals/evals.json` when the skill has repeatable expected behavior.
7. Update the `Skills` table in this root README.

## Publishing Checklist

Before pushing a skill:

- `SKILL.md` has clear trigger language in the `description`.
- The skill does not contain hardcoded machine-specific absolute paths.
- Secrets are referenced through environment variables or secure local setup, not examples with real credentials.
- Scripts can print `--help` or otherwise expose basic usage.
- Tests and JSON eval files pass validation.
- Generated files such as `__pycache__`, logs, temporary reports, and local database artifacts are not included.

## Current Verification

For the current PostgreSQL reconciliation skill:

```powershell
python -m unittest discover -s pg-table-reconciliation/tests
python pg-table-reconciliation/scripts/pg_reconcile.py --help
python -m json.tool pg-table-reconciliation/evals/evals.json
```
