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

    def test_charge_cost_types_are_validated_before_insert_or_replace(self):
        base = self.read_fixture()
        connection = db.connect(self.path)
        self.addCleanup(connection.close)
        for replace in (False, True):
            if replace:
                self.write_fixture(base)
                seed.seeded(connection, self.fixtures, env="test")
            before = list(connection.iterdump())
            for table, columns in seed.NUMERIC_COLUMNS.items():
                for column in columns:
                    for value in ("texte", "2", True, False, float("inf")):
                        for operation in (("insert", "update") if table == "estimation_action" else ("insert",)):
                            with self.subTest(replace=replace, table=table, column=column,
                                              value=value, operation=operation):
                                data = json.loads(json.dumps(base))
                                entry = next(item for item in data["tables"] if item["table"] == table)
                                if operation == "insert":
                                    if table == "estimation_action" and column == "charge_max_h":
                                        entry["rows"][0].update(charge_min_h=1, charge_probable_h=2)
                                    entry["rows"][0][column] = value
                                else:
                                    data["updates"].append({"table": table, "id": entry["rows"][0]["id"],
                                                            "set": {column: value}})
                                self.write_fixture(data)
                                statements = []
                                connection.set_trace_callback(statements.append)
                                try:
                                    with self.assertRaises(seed.SeedError):
                                        seed.seeded(connection, self.fixtures, env="test", replace=replace,
                                                    allow_replace=replace)
                                finally:
                                    connection.set_trace_callback(None)
                                self.assertFalse(any(sql.lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE "))
                                                     for sql in statements))
                                self.assertEqual(list(connection.iterdump()), before)
        self.assertEqual(db.integrity_problems(connection), [])

    def test_charge_cost_valid_numbers_and_null(self):
        base = self.read_fixture()
        connection = db.connect(self.path)
        self.addCleanup(connection.close)
        for value in (0, 2.5, None):
            data = json.loads(json.dumps(base))
            for table, columns in seed.NUMERIC_COLUMNS.items():
                entry = next(item for item in data["tables"] if item["table"] == table)
                entry["rows"][0].update({column: value for column in columns})
                if table == "estimation_action":
                    data["updates"].append({"table": table, "id": entry["rows"][0]["id"],
                                            "set": {column: value for column in columns}})
            self.write_fixture(data)
            seed.seeded(connection, self.fixtures, env="test", replace=True, allow_replace=True)
            for table, columns in seed.NUMERIC_COLUMNS.items():
                row = next(item for item in data["tables"] if item["table"] == table)["rows"][0]
                where = "id = ?" if table == "estimation_action" else "action_id = ? AND utilisateur_id = ?"
                params = (row["id"],) if table == "estimation_action" else (row["action_id"], row["utilisateur_id"])
                stored = connection.execute(f"SELECT {', '.join(sorted(columns))} FROM {table} WHERE {where}", params)
                self.assertEqual(tuple(stored.fetchone()), (value,) * len(columns))
            self.assertEqual(db.integrity_problems(connection), [])

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
