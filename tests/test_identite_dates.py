import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from journai import db, migrations, seed, validation


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "journai" / "migrations"
FIXTURES = ROOT / "journai" / "fixtures"


class IdentityTimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "data.db"
        self.fixtures = self.root / "fixtures"
        shutil.copytree(FIXTURES, self.fixtures)
        self.file = self.fixtures / "espace-a.json"
        self.base = json.loads(self.file.read_text(encoding="utf-8"))
        connection = db.connect(self.path)
        migrations.migrate(connection, SCHEMA)
        connection.close()

    def save(self, data):
        self.file.write_text(json.dumps(data), encoding="utf-8")

    def snapshot(self):
        connection = db.connect(self.path)
        try:
            self.assertEqual(db.integrity_problems(connection), [])
            return list(connection.iterdump())
        finally:
            connection.close()

    @staticmethod
    def row(data, table):
        return next(entry["rows"][0] for entry in data["tables"] if entry["table"] == table)

    def test_normalizes_insert_and_declarative_update_on_real_seed(self):
        data = copy.deepcopy(self.base)
        users = next(entry["rows"] for entry in data["tables"] if entry["table"] == "utilisateur")
        users[0]["cree_le"] = "2026-01-02T00:30:00+02:00"
        users[1]["cree_le"] = "2026-01-01T17:30:00-05:00"
        data["updates"][0]["set"]["modifie_le"] = "2026-01-02T00:30:00+02:00"
        self.save(data)
        connection = db.connect(self.path)
        try:
            self.assertEqual(sum(seed.seeded(connection, self.fixtures, env="test").values()), 116)
            for user in users:
                result = connection.execute("SELECT cree_le FROM utilisateur WHERE id = ?", (user["id"],))
                self.assertEqual(result.fetchone()[0], "2026-01-01T22:30:00.000000+00:00")
            update = data["updates"][0]
            result = connection.execute("SELECT modifie_le FROM parcours WHERE id = ?", (update["id"],))
            self.assertEqual(result.fetchone()[0], "2026-01-01T22:30:00.000000+00:00")
            self.assertEqual(connection.execute("SELECT role FROM membre_espace ORDER BY role LIMIT 1").fetchone()[0],
                             "administrateur")
            civil = self.row(data, "constat")["observe_le"]
            self.assertEqual(connection.execute("SELECT observe_le FROM constat WHERE id = ?",
                                                (self.row(data, "constat")["id"],)).fetchone()[0], civil)
            self.assertEqual(db.integrity_problems(connection), [])
            snapshot = list(connection.iterdump())
        finally:
            connection.close()
        self.assertEqual(self.snapshot(), snapshot)

    def test_integer_keys_in_inserts_and_declarative_updates(self):
        scripts = self.root / "technical-schema"
        scripts.mkdir()
        (scripts / "0001_technical.sql").write_text(
            "CREATE TABLE parent (id INTEGER PRIMARY KEY);"
            "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id));",
            encoding="utf-8",
        )
        fixtures = self.root / "technical-fixtures"
        fixtures.mkdir()
        (fixtures / "data.json").write_text(json.dumps({
            "env": "test",
            "tables": [
                {"table": "parent", "rows": [{"id": 1}, {"id": 2}]},
                {"table": "child", "rows": [{"id": 3, "parent_id": 1}]},
            ],
            "updates": [{"table": "child", "id": 3, "set": {"parent_id": 2}}],
        }), encoding="utf-8")
        path = self.root / "technical.db"
        connection = db.connect(path)
        try:
            migrations.migrate(connection, scripts)
            self.assertEqual(seed.seeded(connection, fixtures, env="test"), {"parent": 2, "child": 1})
            self.assertEqual(tuple(connection.execute("SELECT id, parent_id FROM child").fetchone()), (3, 2))
            self.assertEqual(db.integrity_problems(connection), [])
            snapshot = list(connection.iterdump())
        finally:
            connection.close()
        connection = db.connect(path)
        try:
            self.assertEqual(list(connection.iterdump()), snapshot)
            self.assertEqual(db.integrity_problems(connection), [])
        finally:
            connection.close()

    def test_chronological_order_after_normalization(self):
        early = "2026-01-02T00:30:00+02:00"
        late = "2026-01-01T23:00:00+00:00"
        self.assertGreater(early, late)
        self.assertLess(validation.canonical_instant(early), validation.canonical_instant(late))
        self.assertEqual(validation.canonical_instant("2026-01-01T17:30:00-05:00"),
                         validation.canonical_instant(early))

    def test_invalid_values_refused_before_replace_changes_anything(self):
        connection = db.connect(self.path)
        seed.seeded(connection, self.fixtures, env="test")
        connection.close()
        original = self.snapshot()
        cases = [
            ("utilisateur", "id", "not-a-uuid"),
            ("utilisateur", "id", self.row(self.base, "utilisateur")["id"].upper()),
            ("utilisateur", "id", self.row(self.base, "utilisateur")["id"].replace("-", "")),
            ("utilisateur", "id", 4),
            ("utilisateur", "id", None),
            ("etape", "cle_stable", "incorrect"),
            ("projet", "espace_id", False),
            ("espace", "cree_par", "incorrect"),
            ("structure", "modifie_par", 1),
            ("version_parcours", "valide_par", "incorrect"),
            ("utilisateur", "cree_le", "2026-01-01T12:00:00"),
            ("utilisateur", "cree_le", "2026-02-30T12:00:00+00:00"),
            ("utilisateur", "cree_le", 5),
            ("utilisateur", "cree_le", None),
            ("structure", "archive_le", "2026-01-01"),
        ]
        for table, key, value in cases:
            with self.subTest(table=table, key=key, value=value):
                data = copy.deepcopy(self.base)
                self.row(data, table)[key] = value
                self.save(data)
                connection = db.connect(self.path)
                statements = []
                connection.set_trace_callback(statements.append)
                try:
                    with self.assertRaises(seed.SeedError):
                        seed.seeded(connection, self.fixtures, env="test", replace=True, allow_replace=True)
                    self.assertFalse(any(s.lstrip().upper().startswith(("UPDATE ", "DELETE ", "INSERT "))
                                         for s in statements))
                finally:
                    connection.close()
                self.assertEqual(self.snapshot(), original)

    def test_invalid_declarative_updates_and_late_fk_failure_preserve_snapshot(self):
        connection = db.connect(self.path)
        seed.seeded(connection, self.fixtures, env="test")
        connection.close()
        original = self.snapshot()
        for kind in ("id", "reference", "integer_reference", "instant", "missing", "foreign_key"):
            with self.subTest(kind=kind):
                data = copy.deepcopy(self.base)
                update = data["updates"][0]
                if kind == "id":
                    update["id"] = 123
                elif kind == "reference":
                    update["set"]["version_cible_id"] = "BAD"
                elif kind == "integer_reference":
                    update["set"]["version_cible_id"] = 123
                elif kind == "instant":
                    update["set"]["modifie_le"] = "2026-01-01T00:00:00"
                elif kind == "missing":
                    update["id"] = "00000000-0000-4000-8000-000000000000"
                else:
                    update["set"]["version_cible_id"] = "00000000-0000-4000-8000-000000000000"
                self.save(data)
                connection = db.connect(self.path)
                statements = []
                connection.set_trace_callback(statements.append)
                try:
                    with self.assertRaises(seed.SeedError):
                        seed.seeded(connection, self.fixtures, env="test", replace=True, allow_replace=True)
                    if kind in {"id", "reference", "integer_reference", "instant"}:
                        self.assertFalse(any(s.lstrip().upper().startswith(("UPDATE ", "DELETE ", "INSERT "))
                                             for s in statements))
                finally:
                    connection.close()
                self.assertEqual(self.snapshot(), original)

    def test_new_migration_journal_canonical_without_rewriting_old_rows(self):
        scripts = self.root / "scripts"
        scripts.mkdir()
        (scripts / "0001_first.sql").write_text("CREATE TABLE first (id INTEGER);", encoding="utf-8")
        connection = db.connect(self.path)
        # Use a separate migrated file so the real seven migration checksums remain untouched.
        connection.close()
        path = self.root / "journal.db"
        connection = db.connect(path)
        try:
            migrations.migrate(connection, scripts)
            connection.execute("UPDATE schema_migration SET applique_le = ? WHERE version = '0001'", ("old",))
            connection.commit()
            (scripts / "0002_second.sql").write_text("CREATE TABLE second (id INTEGER);", encoding="utf-8")
            migrations.migrate(connection, scripts)
            rows = list(connection.execute("SELECT version, applique_le FROM schema_migration ORDER BY version"))
            self.assertEqual(tuple(rows[0]), ("0001", "old"))
            self.assertRegex(rows[1][1], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00$")
            self.assertEqual(validation.canonical_instant(rows[1][1]), rows[1][1])
            self.assertEqual(db.integrity_problems(connection), [])
            snapshot = list(connection.iterdump())
        finally:
            connection.close()
        connection = db.connect(path)
        try:
            self.assertEqual(list(connection.iterdump()), snapshot)
            self.assertEqual(db.integrity_problems(connection), [])
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
