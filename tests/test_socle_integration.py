import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from journai import db, migrations, seed, validation
from journai.config import load_config


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "journai" / "migrations"
FIXTURES = ROOT / "journai" / "fixtures"
PRINCIPAL = (
    "espace", "structure", "projet", "public", "canal", "point_contact", "parcours",
    "version_parcours", "etape", "transition_etape", "occurrence_contact", "operation",
    "ressource", "constat", "action", "objet", "indicateur",
)
AUDIT = {"revision", "cree_par", "cree_le", "modifie_par", "modifie_le", "archive_le"}


class SocleIntegrationTests(unittest.TestCase):
    def test_config_migrations_fixtures_and_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_file = root / "config.json"
            config_file.write_text(json.dumps({"env": "test", "db": str(root / "data.db"),
                                               "schema_dir": str(SCHEMA)}), encoding="utf-8")
            environment = {k: v for k, v in os.environ.items() if not k.startswith("JOURNAI_")}
            with patch.dict(os.environ, environment, clear=True):
                config = load_config(config_file)
            self.assertEqual(config.env, "test")
            self.assertEqual(config.schema_dir, SCHEMA)
            self.assertEqual({p.name for p in FIXTURES.glob("*.json")}, {"espace-a.json", "espace-b.json"})
            versions = [f"{number:04}" for number in range(1, 8)]
            connection = db.connect(config.db_path)
            try:
                self.assertEqual(migrations.migrate(connection, config.schema_dir), versions)
                counts = seed.seeded(connection, FIXTURES, env=config.env)
                self.assertEqual(counts["espace"], 2)
                self.assertEqual(sum(counts.values()), 116)
                self.assert_database(connection, versions)
                snapshot = list(connection.iterdump())
                self.assertEqual(migrations.migrate(connection, config.schema_dir), [])
                with self.assertRaises(seed.SeedError):
                    seed.seeded(connection, FIXTURES, env=config.env)
                self.assertEqual(list(connection.iterdump()), snapshot)
            finally:
                connection.close()
            connection = db.connect(config.db_path, create=False)
            try:
                self.assert_database(connection, versions)
                self.assertEqual(list(connection.iterdump()), snapshot)
                self.assertEqual(migrations.migrate(connection, config.schema_dir), [])
                self.assertEqual(list(connection.iterdump()), snapshot)
            finally:
                connection.close()

    def assert_database(self, connection, versions):
        for pragma, expected in (("foreign_keys", 1), ("recursive_triggers", 1), ("journal_mode", "wal")):
            self.assertEqual(connection.execute(f"PRAGMA {pragma}").fetchone()[0], expected)
        self.assertEqual(db.integrity_problems(connection), [])
        self.assertEqual(migrations.applied_versions(connection), versions)
        journal = list(connection.execute("SELECT version, applique_le, fichier, empreinte_sha256 "
                                          "FROM schema_migration ORDER BY version"))
        for row, (version, path) in zip(journal, migrations.discover(SCHEMA), strict=True):
            self.assertEqual((row[0], row[2], row[3]),
                             (version, path.name, hashlib.sha256(path.read_bytes()).hexdigest()))
            self.assert_instant(row[1])
        for table in db.table_names(connection):
            if table == migrations.JOURNAL_TABLE:
                continue
            info = list(connection.execute("SELECT * FROM pragma_table_info(?)", (table,)))
            for row in connection.execute(f'SELECT * FROM "{table}"'):
                for column in info:
                    name, kind = column[1], column[2]
                    value = row[name]
                    if value is None:
                        continue
                    if "INT" not in kind.upper() and (name in {"id", "cle_stable"}
                                                      or name.endswith(("_id", "_par"))):
                        self.assertEqual(str(UUID(value)), value, (table, name))
                    elif name in validation.INSTANTS:
                        self.assert_instant(value)
        for table in PRINCIPAL:
            with self.subTest(table=table):
                self.assertTrue(AUDIT <= set(db.column_names(connection, table)))
                rows = list(connection.execute(f'SELECT revision, cree_par, cree_le, modifie_par, '
                                               f'modifie_le, archive_le FROM "{table}"'))
                self.assertTrue(rows)
                for row in rows:
                    self.assertEqual(row[0], 1)
                    self.assertIsNotNone(row[1])
                    self.assertIsNotNone(row[2])
                    self.assertEqual(tuple(row[3:]), (None, None, None))

    def assert_instant(self, value):
        parsed = datetime.fromisoformat(value)
        self.assertEqual(parsed.utcoffset(), timezone.utc.utcoffset(parsed))
        self.assertEqual(parsed.isoformat(timespec="microseconds"), value)
        self.assertTrue(value.endswith("+00:00"))


if __name__ == "__main__":
    unittest.main()
