import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "data.db"
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("JOURNAI_")}
        self.env.update(PYTHONPATH=str(ROOT), PYTHONUTF8="1", JOURNAI_DB=str(self.database),
                        JOURNAI_JETON_DEV="secret-ne-pas-afficher")

    def run_cli(self, *args, success=True, env=None):
        result = subprocess.run([sys.executable, "-m", "journai", *args], cwd=self.root,
                                env=env or self.env, capture_output=True, text=True, encoding="utf-8")
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ERREUR", result.stderr)
        self.assertNotIn("secret-ne-pas-afficher", result.stdout + result.stderr)
        return result

    def snapshot(self):
        with sqlite3.connect(self.database) as connection:
            return list(connection.iterdump())

    def test_init_seed_status_and_refusal(self):
        self.assertIn("init", self.run_cli("--help").stdout)
        self.run_cli("init")
        before = self.snapshot()
        self.run_cli("init")
        self.assertEqual(self.snapshot(), before)
        self.run_cli("seed")
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM espace").fetchone()[0], 2)
        before = self.snapshot()
        status = self.run_cli("status").stdout
        self.assertIn("0001, 0002, 0003, 0004, 0005, 0006, 0007", status)
        self.assertIn("espace: 2", status)
        self.assertIn("schema_migration: 7", status)
        self.assertEqual(self.snapshot(), before)
        self.assertIn("non vide", self.run_cli("seed", success=False).stderr)
        self.assertEqual(self.snapshot(), before)
        self.run_cli(success=False)
        self.assertEqual(self.snapshot(), before)

    def test_default_startup_and_logging_configuration(self):
        config = self.root / "config.json"
        config.write_text(json.dumps({"env": "test", "db": str(self.database), "log_level": "WARNING"}),
                          encoding="utf-8")
        env = {key: value for key, value in self.env.items() if key != "JOURNAI_DB"}
        self.assertEqual(self.run_cli("--config", str(config), env=env).stdout, "")
        self.assertIn("espace: 2", self.run_cli("--config", str(config), "status", env=env).stdout)

    def test_errors_do_not_create_or_modify_data(self):
        self.run_cli("status", success=False)
        self.assertFalse(self.database.exists())
        config = self.root / "invalid.json"
        config.write_text("{", encoding="utf-8")
        self.run_cli("--config", str(config), "init", success=False)
        self.assertFalse(self.database.exists())
        self.run_cli("seed", success=False)
        schema = self.root / "bad-schema"
        schema.mkdir()
        (schema / "0001_bad.sql").write_text("INVALID SQL;", encoding="utf-8")
        self.run_cli("init", env={**self.env, "JOURNAI_SCHEMA_DIR": str(schema)}, success=False)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
