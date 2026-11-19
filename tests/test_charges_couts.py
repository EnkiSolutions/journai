import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from journai import db, migrations, seed

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "journai" / "migrations"
FIXTURES = ROOT / "journai" / "fixtures"
NOW = '2026-01-01T00:00:00+00:00'
COLUMNS = {
    'contribution_action': ('charge_prevue_h', 'charge_realisee_h'),
    'estimation_action': ('charge_min_h', 'charge_probable_h', 'charge_max_h',
                          'cout_min', 'cout_probable', 'cout_max'),
}


class ChargeCostSeedTests(unittest.TestCase):
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

    def test_charge_cost_types_are_validated_before_insert_or_replace(self):
        base = self.read_fixture()
        connection = db.connect(self.path)
        self.addCleanup(connection.close)
        for replace in (False, True):
            if replace:
                self.write_fixture(base)
                seed.seeded(connection, self.fixtures, env="test")
            before = list(connection.iterdump())
            for table, columns in COLUMNS.items():
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
        for value, updated in ((0, 2.5), (2.5, None), (None, 0)):
            data = json.loads(json.dumps(base))
            for table, columns in COLUMNS.items():
                entry = next(item for item in data["tables"] if item["table"] == table)
                entry["rows"][0].update({column: value for column in columns})
                if table == "estimation_action":
                    data["updates"].append({"table": table, "id": entry["rows"][0]["id"],
                                            "set": {column: updated for column in columns}})
            self.write_fixture(data)
            seed.seeded(connection, self.fixtures, env="test", replace=True, allow_replace=True)
            for table, columns in COLUMNS.items():
                row = next(item for item in data["tables"] if item["table"] == table)["rows"][0]
                where = "id = ?" if table == "estimation_action" else "action_id = ? AND utilisateur_id = ?"
                params = (row["id"],) if table == "estimation_action" else (row["action_id"], row["utilisateur_id"])
                stored = connection.execute(f"SELECT {', '.join(sorted(columns))} FROM {table} WHERE {where}", params)
                expected = updated if table == "estimation_action" else value
                self.assertEqual(tuple(stored.fetchone()), (expected,) * len(columns))
            self.assertEqual(db.integrity_problems(connection), [])


class ChargeCostTypeTests(unittest.TestCase):
    def setup_legacy(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.path = root / 'data.db'
        old = root / 'schema_8'
        old.mkdir()
        for file in SCHEMA.glob('000[1-8]_*.sql'):
            shutil.copyfile(file, old / file.name)
        self.schema_9 = root / 'schema_9'
        shutil.copytree(old, self.schema_9)
        for file in SCHEMA.glob('0009_*.sql'):
            shutil.copyfile(file, self.schema_9 / file.name)
        self.c = db.connect(self.path)
        self.addCleanup(lambda: self.c.close())
        migrations.migrate(self.c, old)
        c = self.c
        c.execute("INSERT INTO utilisateur (id, nom_affiche, email, cree_le) VALUES ('u', 'U', 'u@example.invalid', ?)", (NOW,))
        c.execute("INSERT INTO espace (id, nom, cree_par, cree_le) VALUES ('e', 'E', 'u', ?)", (NOW,))
        c.execute("INSERT INTO structure (id, espace_id, nom, type_structure, cree_par, cree_le) VALUES ('s', 'e', 'S', 'autre', 'u', ?)", (NOW,))
        c.execute("INSERT INTO projet (id, espace_id, structure_pilote_id, nom, finalite, responsable_id, cree_par, cree_le) VALUES ('p', 'e', 's', 'P', 'F', 'u', 'u', ?)", (NOW,))
        c.execute("INSERT INTO action (id, espace_id, projet_pilote_id, titre, description, nature, statut, responsable_id, critere_acceptation, cree_par, cree_le) VALUES ('a', 'e', 'p', 'A', 'D', 'suivi', 'propose', 'u', 'C', 'u', ?)", (NOW,))
        c.execute("INSERT INTO indicateur (id, espace_id, projet_id, nom, definition, unite, mode_calcul, sens_amelioration, periodicite, responsable_id, cree_par, cree_le) VALUES ('i', 'e', 'p', 'I', 'D', 'U', 'manuel', 'croitre', 'mensuelle', 'u', 'u', ?)", (NOW,))
        self.estimation('ok', 1, 2, 3, 4)
        self.mesure('ok', 1.5)
        c.commit()

    def reopen(self):
        self.c.close()
        self.c = db.connect(self.path)

    def estimation(self, ident, low, high, cost_low, cost_high):
        self.c.execute("INSERT INTO estimation_action (id, action_id, espace_id, auteur_id, charge_min_h, charge_max_h, cout_min, cout_max, complexite_technique, complexite_organisationnelle, incertitude, justification, cree_le) VALUES (?, 'a', 'e', 'u', ?, ?, ?, ?, 'faible', 'faible', 'faible', 'J', ?)",
                       (ident, low, high, cost_low, cost_high, NOW))

    def mesure(self, ident, value):
        self.c.execute("INSERT INTO mesure_indicateur (id, espace_id, indicateur_id, periode_debut, periode_fin, valeur, source, auteur_id, niveau_confiance, cree_le) VALUES (?, 'e', 'i', ?, ?, ?, 'S', 'u', 'forte', ?)",
                       (ident, ident, ident, value, NOW))

    def setUp(self):
        self.setup_legacy()
        self.schema_10 = Path(self.temp.name) / 'schema_10'
        self.schema_10.mkdir()
        for file in SCHEMA.glob('*.sql'):
            if file.name[:4] <= '0010':
                shutil.copyfile(file, self.schema_10 / file.name)
        migrations.migrate(self.c, self.schema_10)
        self.c.execute("INSERT INTO utilisateur (id, nom_affiche, email, cree_le) VALUES ('u2', 'U2', 'u2@example.invalid', ?)", (NOW,))
        self.c.execute("INSERT INTO contribution_action (action_id, utilisateur_id, espace_id, role_contribution) VALUES ('a', 'u', 'e', 'contributeur')")
        self.c.execute('UPDATE estimation_action SET charge_min_h=NULL, charge_max_h=NULL, cout_min=NULL, cout_max=NULL')
        self.c.commit()

    def insert(self, table, column, value):
        if table == 'contribution_action':
            self.c.execute(f"INSERT INTO contribution_action (action_id, utilisateur_id, espace_id, role_contribution, {column}) VALUES ('a', 'u2', 'e', 'contributeur', ?)", (value,))
        else:
            self.c.execute(f"INSERT INTO estimation_action (id, action_id, espace_id, auteur_id, complexite_technique, complexite_organisationnelle, incertitude, justification, cree_le, {column}) VALUES ('new', 'a', 'e', 'u', 'faible', 'faible', 'faible', 'J', ?, ?)", (NOW, value))

    def test_upgrade_valid_preserves_data_and_journal(self):
        self.c.execute("UPDATE contribution_action SET charge_prevue_h=2.5")
        self.c.execute("UPDATE estimation_action SET charge_min_h=1, charge_probable_h=2, charge_max_h=3")
        self.c.commit()
        tables = ('contribution_action', 'estimation_action', 'schema_migration')
        before = {table: [tuple(row) for row in self.c.execute(f'SELECT * FROM {table}')]
                  for table in tables}
        self.assertEqual(migrations.migrate(self.c, SCHEMA), ['0011'])
        self.reopen()
        for table in tables[:2]:
            self.assertEqual([tuple(row) for row in self.c.execute(f'SELECT * FROM {table}')], before[table])
        self.assertEqual([tuple(row) for row in self.c.execute("SELECT * FROM schema_migration WHERE version < '0011' ORDER BY version")], before['schema_migration'])
        self.assertEqual(migrations.migrate(self.c, SCHEMA), [])
        self.assertEqual(db.integrity_problems(self.c), [])

    def test_upgrade_refuses_each_invalid_stored_value_atomically(self):
        for table, columns in COLUMNS.items():
            for column in columns:
                for value in ('texte', b'bytes', float('inf')):
                    with self.subTest(table=table, column=column, value=value):
                        self.c.execute(f'UPDATE {table} SET {column}=?', (value,))
                        self.c.commit()
                        before = list(self.c.iterdump())
                        journal = [tuple(row) for row in self.c.execute('SELECT * FROM schema_migration ORDER BY version')]
                        with self.assertRaisesRegex(migrations.MigrationError, 'types_charges_couts_invalides'):
                            migrations.migrate(self.c, SCHEMA)
                        self.assertEqual(list(self.c.iterdump()), before)
                        self.reopen()
                        self.assertEqual(list(self.c.iterdump()), before)
                        self.assertEqual([tuple(row) for row in self.c.execute('SELECT * FROM schema_migration ORDER BY version')], journal)
                        self.assertEqual(migrations.applied_versions(self.c), [f'{n:04}' for n in range(1, 11)])
                        self.c.execute(f'UPDATE {table} SET {column}=NULL')
                        self.c.commit()

    def test_direct_insert_update_types_and_existing_integrity(self):
        migrations.migrate(self.c, SCHEMA)
        for table, columns in COLUMNS.items():
            for column in columns:
                for value in ('texte', b'bytes', float('inf'), float('-inf')):
                    with self.subTest(table=table, column=column, value=value):
                        with self.assertRaisesRegex(sqlite3.IntegrityError, 'types charges couts'):
                            self.insert(table, column, value)
                        with self.assertRaisesRegex(sqlite3.IntegrityError, 'types charges couts'):
                            self.c.execute(f'UPDATE {table} SET {column}=?', (value,))
                        self.assertIsNone(self.c.execute(f'SELECT {column} FROM {table}').fetchone()[0])
                        self.assertEqual(self.c.execute(f'SELECT count(*) FROM {table}').fetchone()[0], 1)
                for value, stored_type in ((None, 'null'), (2, 'integer'), (2.5, 'real'), ('2', 'integer'), (True, 'integer')):
                    with self.subTest(table=table, column=column, value=value):
                        self.insert(table, column, value)
                        where = "utilisateur_id='u2'" if table == 'contribution_action' else "id='new'"
                        row = self.c.execute(f'SELECT {column}, typeof({column}) FROM {table} WHERE {where}').fetchone()
                        self.assertEqual(tuple(row), (value if value != '2' else 2, stored_type))
                        self.c.execute(f'DELETE FROM {table} WHERE {where}')
                        self.c.execute(f'UPDATE {table} SET {column}=?', (value,))
                        row = self.c.execute(f'SELECT {column}, typeof({column}) FROM {table}').fetchone()
                        self.assertEqual(tuple(row), (value if value != '2' else 2, stored_type))
                        self.c.execute(f'UPDATE {table} SET {column}=NULL')
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute('UPDATE contribution_action SET charge_prevue_h=-1')
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute('UPDATE estimation_action SET charge_min_h=3, charge_max_h=1')
        self.c.commit()
        self.assertEqual(db.integrity_problems(self.c), [])
