import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from journai import db, migrations


SCHEMA = Path(__file__).resolve().parents[1] / "journai" / "migrations"


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "test.db"
        self.scripts = self.root / "scripts"
        self.scripts.mkdir()
        self.connection = db.connect(self.database)
        self.addCleanup(self.close)

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def reopen(self):
        self.close()
        self.connection = db.connect(self.database)

    def script(self, name, sql):
        path = self.scripts / name
        path.write_text(sql, encoding="utf-8")
        return path

    def test_real_migrations_are_verified_and_idempotent(self):
        versions = [f"{number:04}" for number in range(1, 11)]
        self.assertEqual(migrations.migrate(self.connection, SCHEMA), versions)
        self.assertEqual(migrations.applied_versions(self.connection), versions)
        rows = self.connection.execute(
            "SELECT version, applique_le, fichier, empreinte_sha256 FROM schema_migration ORDER BY version"
        ).fetchall()
        for row, (version, path) in zip(rows, migrations.discover(SCHEMA)):
            self.assertEqual(row[0], version)
            self.assertTrue(row[1])
            self.assertEqual(row[2], path.name)
            self.assertEqual(row[3], hashlib.sha256(path.read_bytes()).hexdigest())
        before = list(self.connection.iterdump())
        self.reopen()
        self.assertEqual(migrations.migrate(self.connection, SCHEMA), [])
        self.assertEqual(list(self.connection.iterdump()), before)

    def test_changed_or_missing_applied_migration_blocks_new_version(self):
        first = self.script("0001_first.sql", "CREATE TABLE original (id INTEGER);\n")
        migrations.migrate(self.connection, self.scripts)
        self.script("0002_next.sql", "CREATE TABLE next_table (id INTEGER);\n")
        first.write_text("CREATE TABLE changed (id INTEGER);\n", encoding="utf-8")
        with self.assertRaisesRegex(migrations.MigrationError, "empreinte.*0001"):
            migrations.migrate(self.connection, self.scripts)
        first.unlink()
        with self.assertRaisesRegex(migrations.MigrationError, "empreinte.*0001"):
            migrations.migrate(self.connection, self.scripts)
        self.reopen()
        self.assertEqual(migrations.applied_versions(self.connection), ["0001"])
        self.assertNotIn("next_table", db.table_names(self.connection))

    def test_legacy_journal_is_refused_without_modification(self):
        self.connection.execute("CREATE TABLE schema_migration (version TEXT PRIMARY KEY, "
                                "applique_le TEXT, fichier TEXT)")
        self.connection.execute("INSERT INTO schema_migration VALUES ('0001', 'old', 'old.sql')")
        self.connection.commit()
        self.script("0002_next.sql", "CREATE TABLE next_table (id INTEGER);")
        with self.assertRaisesRegex(migrations.MigrationError, "hérité.*empreinte"):
            migrations.migrate(self.connection, self.scripts)
        self.reopen()
        self.assertEqual(tuple(self.connection.execute("SELECT * FROM schema_migration").fetchone()),
                         ("0001", "old", "old.sql"))
        self.assertNotIn("next_table", db.table_names(self.connection))

    def test_missing_digest_is_unverifiable(self):
        self.connection.execute("CREATE TABLE schema_migration (version TEXT PRIMARY KEY, "
                                "applique_le TEXT, fichier TEXT, empreinte_sha256 TEXT)")
        self.connection.execute("INSERT INTO schema_migration VALUES ('0001', 'old', 'first.sql', NULL)")
        self.connection.commit()
        self.script("0001_first.sql", "SELECT 1;")
        with self.assertRaisesRegex(migrations.MigrationError, "empreinte.*0001"):
            migrations.migrate(self.connection, self.scripts)
        self.reopen()
        self.assertIsNone(self.connection.execute("SELECT empreinte_sha256 FROM schema_migration").fetchone()[0])

    def test_sql_failure_rolls_back_ddl_data_and_journal(self):
        self.script("0001_first.sql", "CREATE TABLE saved (id INTEGER); INSERT INTO saved VALUES (1);")
        self.script("0002_bad.sql", "CREATE TABLE discarded (id INTEGER);\n"
                    "INSERT INTO saved VALUES (2);\nINSERT INTO absent VALUES (3);")
        with self.assertRaisesRegex(migrations.MigrationError, "0002_bad"):
            migrations.migrate(self.connection, self.scripts)
        self.assert_rolled_back()

    def assert_rolled_back(self):
        self.reopen()
        self.assertEqual(migrations.applied_versions(self.connection), ["0001"])
        self.assertEqual([tuple(row) for row in self.connection.execute("SELECT * FROM saved")], [(1,)])
        self.assertNotIn("discarded", db.table_names(self.connection))

    def test_foreign_key_failure_rolls_back(self):
        self.script("0001_first.sql", "CREATE TABLE saved (id INTEGER PRIMARY KEY); "
                    "INSERT INTO saved VALUES (1);")
        self.script("0002_bad.sql", "PRAGMA defer_foreign_keys = ON;\n"
                    "CREATE TABLE discarded (id INTEGER REFERENCES saved(id));\n"
                    "INSERT INTO saved VALUES (2);\nINSERT INTO discarded VALUES (999);")
        with self.assertRaisesRegex(migrations.MigrationError, "intégrité refusée"):
            migrations.migrate(self.connection, self.scripts)
        self.assert_rolled_back()

    def test_integrity_check_failure_rolls_back(self):
        self.script("0001_first.sql", "CREATE TABLE saved (id INTEGER); INSERT INTO saved VALUES (1);")
        migrations.migrate(self.connection, self.scripts)
        self.script("0002_bad.sql", "CREATE TABLE discarded (id INTEGER); INSERT INTO saved VALUES (2);")
        with patch.object(db, "integrity_problems", return_value=[("bad integrity",)]):
            with self.assertRaisesRegex(migrations.MigrationError, "intégrité refusée"):
                migrations.migrate(self.connection, self.scripts)
        self.assert_rolled_back()

    def test_invalid_scripts_and_duplicate_versions(self):
        with self.assertRaisesRegex(migrations.MigrationError, "aucune migration"):
            migrations.discover(self.scripts)
        path = self.script("0001_first.sql", "-- rien\n")
        with self.assertRaisesRegex(migrations.MigrationError, "aucune instruction"):
            migrations.migrate(self.connection, self.scripts)
        path.write_text("/* rien */; -- rien non plus\n", encoding="utf-8")
        with self.assertRaisesRegex(migrations.MigrationError, "aucune instruction"):
            migrations.migrate(self.connection, self.scripts)
        path.write_text("CREATE TABLE missing (id INTEGER)", encoding="utf-8")
        with self.assertRaisesRegex(migrations.MigrationError, "incomplet"):
            migrations.migrate(self.connection, self.scripts)
        self.script("0001_duplicate.sql", "SELECT 1;")
        with self.assertRaisesRegex(migrations.MigrationError, "dupliqués"):
            migrations.migrate(self.connection, self.scripts)
        self.reopen()
        self.assertEqual(migrations.applied_versions(self.connection), [])
        self.assertNotIn("missing", db.table_names(self.connection))

    def test_explicit_transaction_cannot_escape_rollback(self):
        self.script("0001_first.sql", "CREATE TABLE saved (id INTEGER); INSERT INTO saved VALUES (1);")
        migrations.migrate(self.connection, self.scripts)
        for command in ("BEGIN", "COMMIT", "END", "ROLLBACK", "SAVEPOINT test", "RELEASE test"):
            with self.subTest(command=command):
                self.script("0002_bad.sql", "CREATE TABLE discarded (id INTEGER);\n"
                            f"INSERT INTO saved VALUES (2);\n/* comment */ {command};\nINSERT INTO absent VALUES (3);")
                with self.assertRaisesRegex(migrations.MigrationError, "transaction interdite"):
                    migrations.migrate(self.connection, self.scripts)
                self.assert_rolled_back()

    def test_statement_splitting_preserves_strings_comments_and_triggers(self):
        sql = "CREATE TABLE x (s TEXT); INSERT INTO x VALUES ('a; -- b');\n" \
              "CREATE TRIGGER t AFTER INSERT ON x BEGIN\n" \
              "INSERT INTO x VALUES ('inside;');\nEND; -- trailing comment\n"
        instructions = migrations.statements(sql)
        self.assertEqual(len(instructions), 3)
        for instruction in instructions:
            self.connection.execute(instruction)
        self.assertEqual(self.connection.execute("SELECT s FROM x").fetchone()[0], "a; -- b")


if __name__ == "__main__":
    unittest.main()
