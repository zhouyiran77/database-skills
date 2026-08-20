from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "pg_pk_conflict.py"
CONFIG = """
## 数据库实例

| instance_id | role | school | db_type | host | port | database | username | password_env | sslmode |
|---|---|---|---|---|---:|---|---|---|---|
| v2_huashi | source | 华师 | postgresql | 127.0.0.1 | 5432 | teaching_v2 | audit | DB_V2_HUASHI_PASSWORD | disable |
| v2_wut | source | 武汉理工 | postgresql | 127.0.0.1 | 5432 | teaching_v2 | audit | DB_V2_WUT_PASSWORD | disable |
| v3_main | target | 3.0合并库 | postgresql | 127.0.0.1 | 5432 | teaching_v3 | audit | DB_V3_MAIN_PASSWORD | disable |

## 表比对范围

| scope_id | enabled | source_instances | source_table | target_instance | target_table | primary_key |
|---|---|---|---|---|---|---|
| activity_nodes | true | * | public.activity_nodes | v3_main | teaching.activity_node | id |
"""


class CliTests(unittest.TestCase):
    def test_validate_only_parses_config_without_reading_passwords(self) -> None:
        # Given a valid config file whose password environment variables are unset.
        with TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.md"
            config_path.write_text(CONFIG, encoding="utf-8")
            env = _without_passwords()

            # When the CLI runs in validation-only mode.
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(config_path), "--validate-only"],
                check=False,
                capture_output=True,
                env=env,
                text=True,
            )

        # Then structural validation succeeds without opening a database connection.
        self.assertEqual(result.returncode, 0)
        self.assertIn("配置有效", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_scan_reports_missing_password_environment_variable_safely(self) -> None:
        # Given a valid config file whose first source password variable is unset.
        with TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.md"
            report_path = Path(directory) / "report.md"
            config_path.write_text(CONFIG, encoding="utf-8")
            env = _without_passwords()

            # When the CLI starts a real scan.
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(config_path), "--output-file", str(report_path)],
                check=False,
                capture_output=True,
                env=env,
                text=True,
            )

        # Then it exits as an operational error without leaking a traceback or secret value.
        self.assertEqual(result.returncode, 2)
        self.assertIn("DB_V2_HUASHI_PASSWORD", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("postgresql://", result.stderr)


def _without_passwords() -> dict[str, str]:
    env = os.environ.copy()
    for name in ("DB_V2_HUASHI_PASSWORD", "DB_V2_WUT_PASSWORD", "DB_V3_MAIN_PASSWORD"):
        env.pop(name, None)
    return env


if __name__ == "__main__":
    unittest.main()
