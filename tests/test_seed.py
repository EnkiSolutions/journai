import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from journai import db, migrations, seed
from journai.config import Config


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "journai" / "migrations"
FIXTURES = ROOT / "journai" / "fixtures"


class SeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "data.db"
        self.fixtures = self.root / "fixtures"
        self.fixtures.mkdir()
        self.fixture = self.fixtures / "espace-a.json"
        shutil.copy2(FIXTURES / "espace-a.json", self.fixture)
        connection = db.connect(self.path)
        try:
            migrations.migrate(connection, SCHEMA)
        finally:
            connection.close()

    def read_fixture(self):
        return json.loads(self.fixture.read_text(encoding="utf-8"))

    def write_fixture(self, data):
        self.fixture.write_text(json.dumps(data), encoding="utf-8")

    def snapshot(self):
        connection = db.connect(self.path)
        try:
            return list(connection.iterdump())
        finally:
            connection.close()

    def test_environment_and_replace_permissions(self):
        connection = db.connect(self.path)
        try:
            original = self.snapshot()
            for env in (None, "prod", "staging", "unknown", ""):
                for replace in (False, True):
                    with self.subTest(env=env, replace=replace):
                        with self.assertRaisesRegex(seed.SeedError, "environnement"):
                            seed.seeded(connection, self.fixtures, env=env, replace=replace, allow_replace=True)
            for env in (None, "prod", "staging", "unknown", ""):
                data = self.read_fixture()
                if env is None:
                    del data["env"]
                else:
                    data["env"] = env
                self.write_fixture(data)
                with self.subTest(fixture_env=env):
                    with self.assertRaisesRegex(seed.SeedError, "environnement"):
                        seed.seeded(connection, self.fixtures, env="test", replace=True, allow_replace=True)
            data["env"] = "dev"
            self.write_fixture(data)
            with self.assertRaisesRegex(seed.SeedError, "non autorisé"):
                seed.seeded(connection, self.fixtures, env="test", replace=True)
            self.assertEqual(self.snapshot(), original)
            seed.seeded(connection, self.fixtures, env="test")
            populated = self.snapshot()
            for kwargs in ({}, {"allow_replace": True}, {"replace": True}):
                with self.subTest(kwargs=kwargs), self.assertRaises(seed.SeedError):
                    seed.seeded(connection, self.fixtures, env="test", **kwargs)
                self.assertEqual(self.snapshot(), populated)
        finally:
            connection.close()

    def test_invalid_shapes_identifiers_and_free_sql_are_refused(self):
        base = self.read_fixture()
        mutations = [
            {**base, "extra": 1},
            {**base, "tables": "utilisateur"},
            {**base, "tables": [{"table": "utilisateur", "rows": {}}]},
            {**base, "tables": [{"table": "utilisateur; DROP TABLE espace", "rows": []}]},
            {**base, "tables": [{"table": "schema_migration", "rows": []}]},
            {**base, "tables": [{"table": "utilisateur", "rows": [{"id); DROP TABLE espace": "x"}]}]},
            {**base, "tables": [{"table": "utilisateur", "rows": [{"id": ["x"]}]}]},
            {**base, "updates": ["UPDATE parcours SET id = 'x'"]},
            {**base, "updates": [{"table": "parcours", "id": "x", "set": {}, "sql": "DELETE"}]},
            {**base, "updates": [{"table": "parcours", "id": "x", "set": {"bad": "x"}}]},
            {**base, "updates": [{"table": "schema_migration", "id": "x", "set": {"version": "x"}}]},
            {**base, "updates": [{"table": "parcours", "id": {"sql": "x"}, "set": {"nom": "x"}}]},
        ]
        connection = db.connect(self.path)
        try:
            original = self.snapshot()
            for data in mutations:
                with self.subTest(data=data):
                    self.write_fixture(data)
                    with self.assertRaises(seed.SeedError):
                        seed.seeded(connection, self.fixtures, env="test")
                    self.assertEqual(self.snapshot(), original)
        finally:
            connection.close()

    def test_missing_update_and_late_constraint_failures_roll_back_durably(self):
        connection = db.connect(self.path)
        try:
            seed.seeded(connection, self.fixtures, env="test")
            original = self.snapshot()
            base = self.read_fixture()
            for failure in ("missing_update", "foreign_key"):
                data = json.loads(json.dumps(base))
                if failure == "missing_update":
                    data["updates"][0]["id"] = "00000000-0000-4000-8000-000000000001"
                    message = "update doit toucher exactement une ligne"
                else:
                    data["updates"][0]["set"]["version_cible_id"] = "00000000-0000-4000-8000-000000000002"
                    message = "FOREIGN KEY constraint failed"
                self.write_fixture(data)
                with self.subTest(failure=failure):
                    with self.assertRaisesRegex(seed.SeedError, message):
                        seed.seeded(connection, self.fixtures, env="test", replace=True, allow_replace=True)
                    self.assertEqual(list(connection.iterdump()), original)
                    self.assertEqual(self.snapshot(), original)
                    connection.close()
                    connection = db.connect(self.path, create=False)
                    self.assertEqual(self.snapshot(), original)
        finally:
            connection.close()

    def test_two_fixtures_counts_and_explicit_replacement(self):
        shutil.copy2(FIXTURES / "espace-b.json", self.fixtures)
        connection = db.connect(self.path)
        try:
            counts = seed.seeded(connection, self.fixtures, env="dev")
            self.assertEqual(sum(counts.values()), 116)
            self.assertEqual(counts["utilisateur"], 3)
            self.assertEqual(counts["espace"], 2)
            original = self.snapshot()
            self.assertEqual(seed.seeded(connection, self.fixtures, env="dev", replace=True, allow_replace=True), counts)
            self.assertEqual(self.snapshot(), original)
            self.assertEqual(db.integrity_problems(connection), [])
        finally:
            connection.close()
        self.assertEqual(self.snapshot(), original)

    def test_integer_values_are_validated_before_insert_and_replace(self):
        base = self.read_fixture()
        connection = db.connect(self.path)
        try:
            for populated in (False, True):
                if populated:
                    self.write_fixture(base)
                    seed.seeded(connection, self.fixtures, env="test")
                original = self.snapshot()
                for location in ("insert", "update"):
                    for column, value in (("revision", 1.5), ("volume_estime", 2.5),
                                          ("revision", 1.0), ("revision", "1"),
                                          ("revision", True), ("revision", None),
                                          ("revision", 2**63)):
                        with self.subTest(populated=populated, location=location, column=column, value=value):
                            data = json.loads(json.dumps(base))
                            rows = next(entry["rows"] for entry in data["tables"]
                                        if entry["table"] == "occurrence_contact")
                            if location == "insert":
                                rows[0][column] = value
                            else:
                                data["updates"].append({"table": "occurrence_contact", "id": rows[0]["id"],
                                                        "set": {column: value}})
                            self.write_fixture(data)
                            statements = []
                            connection.set_trace_callback(statements.append)
                            try:
                                with self.assertRaises(seed.SeedError):
                                    seed.seeded(connection, self.fixtures, env="test", replace=populated,
                                                allow_replace=populated)
                            finally:
                                connection.set_trace_callback(None)
                            self.assertFalse(any(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
                                                 for sql in statements))
                            self.assertEqual(list(connection.iterdump()), original)
                            self.assertEqual(self.snapshot(), original)
        finally:
            connection.close()

    def test_integer_and_nullable_values_pass_without_hardening_real_columns(self):
        data = self.read_fixture()
        rows = next(entry["rows"] for entry in data["tables"] if entry["table"] == "occurrence_contact")
        rows[0].update(revision=2, volume_estime=None)
        rows[1].update(revision=3, volume_estime=5)
        data["updates"].extend([
            {"table": "occurrence_contact", "id": rows[0]["id"], "set": {"volume_estime": 6}},
            {"table": "occurrence_contact", "id": rows[1]["id"], "set": {"volume_estime": None, "revision": 4}},
        ])
        measure = next(entry["rows"][0] for entry in data["tables"] if entry["table"] == "mesure_indicateur")
        measure["valeur"] = 1.5
        self.write_fixture(data)
        connection = db.connect(self.path)
        try:
            seed.seeded(connection, self.fixtures, env="test")
            for row, expected in zip(rows[:2], ((2, 6), (4, None))):
                self.assertEqual(tuple(connection.execute(
                    "SELECT revision, volume_estime FROM occurrence_contact WHERE id = ?", (row["id"],)
                ).fetchone()), expected)
            self.assertEqual(connection.execute("SELECT valeur FROM mesure_indicateur WHERE id = ?",
                                                (measure["id"],)).fetchone()[0], 1.5)
            self.assertEqual(db.integrity_problems(connection), [])
        finally:
            connection.close()

    def test_main_uses_config_and_requires_explicit_replace(self):
        config = Config("test", self.path, "localhost", 8000, "INFO", SCHEMA, "")
        output, errors = StringIO(), StringIO()
        with patch.object(seed, "load_config", return_value=config), redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(seed.main(["--fixtures", str(self.fixtures)]), 0)
            original = self.snapshot()
            self.assertEqual(seed.main(["--fixtures", str(self.fixtures)]), 1)
            self.assertEqual(self.snapshot(), original)
            self.assertEqual(seed.main(["--fixtures", str(self.fixtures), "--replace"]), 0)
            self.assertEqual(self.snapshot(), original)
        self.assertIn("non vide", errors.getvalue())
        config = Config("staging", self.path, "localhost", 8000, "INFO", SCHEMA, "")
        with patch.object(seed, "load_config", return_value=config), redirect_stderr(errors):
            self.assertEqual(seed.main(["--fixtures", str(self.fixtures), "--replace"]), 1)
        self.assertIn("environnement", errors.getvalue())
        self.assertEqual(self.snapshot(), original)


if __name__ == "__main__":
    unittest.main()
