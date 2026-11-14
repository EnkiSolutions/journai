import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from journai import db, migrations, seed


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "data.db"

    def test_pragmas_foreign_keys_commit_and_rollback_persist(self):
        connection = db.connect(self.path)
        try:
            self.assertIs(connection.autocommit, False)
            for name, expected in (("foreign_keys", 1), ("recursive_triggers", 1), ("journal_mode", "wal")):
                self.assertEqual(connection.execute(f"PRAGMA {name}").fetchone()[0], expected)
            connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
            connection.execute("CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))")
            connection.execute("INSERT INTO parent VALUES (1)")
            connection.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO child VALUES (999)")
            connection.execute("INSERT INTO parent VALUES (2)")
            connection.rollback()
        finally:
            connection.close()
        connection = db.connect(self.path)
        try:
            self.assertEqual([row[0] for row in connection.execute("SELECT id FROM parent")], [1])
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM child").fetchone()[0], 0)
        finally:
            connection.close()

    def test_refuses_bad_or_missing_pragma_values_and_closes(self):
        values = {"foreign_keys": 1, "recursive_triggers": 1, "journal_mode": "wal"}
        for bad_name in values:
            for bad_value in (None, ("wrong",)):
                with self.subTest(pragma=bad_name, value=bad_value):
                    connection = MagicMock()
                    def execute(sql):
                        cursor = MagicMock()
                        name = sql.split()[1]
                        cursor.fetchone.return_value = (bad_value if name == bad_name else (values[name],))
                        return cursor
                    connection.execute.side_effect = execute
                    with patch.object(db.sqlite3, "connect", return_value=connection) as connect:
                        with self.assertRaisesRegex(RuntimeError, bad_name):
                            db.connect(self.path)
                    connect.assert_called_once_with(self.path, autocommit=True)
                    connection.close.assert_called_once_with()
                    self.assertIsNot(connection.autocommit, False)

    def test_initialization_error_closes_connection(self):
        connection = MagicMock()
        connection.execute.side_effect = sqlite3.OperationalError("pragma error")
        with patch.object(db.sqlite3, "connect", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "pragma error"):
                db.connect(self.path)
        connection.close.assert_called_once_with()

    def test_memory_database_is_refused_and_closed(self):
        real_connect = sqlite3.connect
        opened = []
        def connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            opened.append(connection)
            return connection
        with patch.object(db.sqlite3, "connect", side_effect=connect):
            with self.assertRaisesRegex(RuntimeError, "journal_mode"):
                db.connect(":memory:")
        with self.assertRaises(sqlite3.ProgrammingError):
            opened[0].execute("SELECT 1")

    def test_migrate_and_seed_commit_and_failed_replace_rolls_back(self):
        schema = self.root / "schema"
        schema.mkdir()
        (schema / "0001_test.sql").write_text(
            "CREATE TABLE parent (id INTEGER PRIMARY KEY);"
            "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id));",
            encoding="utf-8",
        )
        fixtures = self.root / "fixtures"
        fixtures.mkdir()
        fixture = fixtures / "synthetic.json"
        def write_fixture(parent, child):
            fixture.write_text(json.dumps({"tables": [
                {"table": "parent", "rows": [{"id": parent}]},
                {"table": "child", "rows": [{"id": 1, "parent_id": child}]},
            ]}), encoding="utf-8")
        write_fixture(1, 1)
        connection = db.connect(self.path)
        try:
            self.assertEqual(migrations.migrate(connection, schema), ["0001"])
            self.assertEqual(seed.seeded(connection, fixtures), {"parent": 1, "child": 1})
        finally:
            connection.close()
        connection = db.connect(self.path)
        try:
            self.assertEqual(migrations.applied_versions(connection), ["0001"])
            self.assertEqual(tuple(connection.execute("SELECT * FROM child").fetchone()), (1, 1))
            write_fixture(2, 999)
            with self.assertRaises(seed.SeedError):
                seed.seeded(connection, fixtures, replace=True)
        finally:
            connection.close()
        connection = db.connect(self.path)
        try:
            self.assertEqual(tuple(connection.execute("SELECT * FROM parent").fetchone()), (1,))
            self.assertEqual(tuple(connection.execute("SELECT * FROM child").fetchone()), (1, 1))
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
