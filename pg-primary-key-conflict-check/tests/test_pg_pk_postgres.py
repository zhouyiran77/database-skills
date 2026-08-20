from __future__ import annotations

from pathlib import Path
import sys
import unittest

import psycopg


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import pg_pk_postgres  # noqa: E402


class DatabaseErrorTests(unittest.TestCase):
    def test_database_error_reason_is_ascii_when_driver_message_is_localized(self) -> None:
        # Given a libpq error containing a character that a Windows GBK stream cannot encode.
        error = psycopg.OperationalError("authentication failed: \ufffd")

        # When the adapter converts the driver error for user-facing output.
        reason = pg_pk_postgres.database_error_reason(error)

        # Then the stable summary is printable without carrying localized driver text.
        self.assertEqual(reason, "OperationalError")
        self.assertTrue(reason.isascii())


if __name__ == "__main__":
    unittest.main()
