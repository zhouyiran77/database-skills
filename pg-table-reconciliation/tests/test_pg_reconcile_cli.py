from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pg_reconcile.py"


class CliTests(unittest.TestCase):
    def test_missing_dsn_env_reports_actionable_error_without_traceback(self) -> None:
        env = os.environ.copy()
        env.pop("PG_RECON_SOURCE_DSN", None)
        env.pop("PG_RECON_TARGET_DSN", None)

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--source-dsn-env",
                "PG_RECON_SOURCE_DSN",
                "--target-dsn-env",
                "PG_RECON_TARGET_DSN",
                "--tables",
                "public.*",
            ],
            check=False,
            capture_output=True,
            env=env,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("Missing required environment variable: PG_RECON_SOURCE_DSN", result.stderr)
        self.assertIn("$env:PG_RECON_SOURCE_DSN", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
