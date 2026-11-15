import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from journai import db, migrations


SCHEMA = Path(__file__).resolve().parents[1] / 'journai' / 'migrations'
NOW = '2026-01-01T00:00:00+00:00'


class IntegriteNumeriqueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.path = root / 'data.db'
        old = root / 'schema_8'
        old.mkdir()
        for file in SCHEMA.glob('000[1-8]_*.sql'):
            shutil.copyfile(file, old / file.name)
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

    def test_upgrade_preserves_populated_database_and_journal(self):
        rows = {table: [tuple(row) for row in self.c.execute(f'SELECT * FROM {table}')]
                for table in ('estimation_action', 'mesure_indicateur', 'schema_migration')}
        self.assertEqual(migrations.migrate(self.c, SCHEMA), ['0009'])
        self.reopen()
        for table in ('estimation_action', 'mesure_indicateur'):
            self.assertEqual([tuple(row) for row in self.c.execute(f'SELECT * FROM {table}')], rows[table])
        self.assertEqual([tuple(row) for row in self.c.execute("SELECT * FROM schema_migration WHERE version < '0009' ORDER BY version")], rows['schema_migration'])
        before = list(self.c.iterdump())
        self.assertEqual(migrations.migrate(self.c, SCHEMA), [])
        self.assertEqual(list(self.c.iterdump()), before)
        self.assertEqual(db.integrity_problems(self.c), [])

    def test_invalid_existing_data_refused_atomically(self):
        for case in ('charge', 'cout', 'mesure'):
            with self.subTest(case=case):
                if case == 'charge':
                    self.estimation('bad', 2, 1, None, None)
                elif case == 'cout':
                    self.estimation('bad', None, None, 2, 1)
                else:
                    self.mesure('bad', 'texte')
                self.c.commit()
                before = list(self.c.iterdump())
                with self.assertRaisesRegex(migrations.MigrationError, 'donnees_numeriques_invalides'):
                    migrations.migrate(self.c, SCHEMA)
                self.reopen()
                self.assertEqual(list(self.c.iterdump()), before)
                self.assertEqual(migrations.applied_versions(self.c), [f'{n:04}' for n in range(1, 9)])
                table = 'mesure_indicateur' if case == 'mesure' else 'estimation_action'
                self.c.execute(f"DELETE FROM {table} WHERE id = 'bad'")
                self.c.commit()

    def test_insert_update_guards_and_persistence(self):
        migrations.migrate(self.c, SCHEMA)
        self.estimation('egal', 2, 2, 3, 3)
        self.estimation('partiel', 2, None, None, 3)
        self.mesure('entier', 2)
        self.mesure('decimal', 2.5)
        self.c.execute("UPDATE estimation_action SET charge_min_h=2, charge_max_h=2, cout_min=3, cout_max=3 WHERE id='ok'")
        self.c.execute("UPDATE estimation_action SET charge_min_h=NULL, cout_max=NULL WHERE id='partiel'")
        self.c.execute("UPDATE mesure_indicateur SET valeur=3 WHERE id='ok'")
        self.c.execute("UPDATE mesure_indicateur SET valeur=3.25 WHERE id='ok'")
        self.c.commit()
        before = list(self.c.iterdump())
        for field in ('charge', 'cout'):
            with self.subTest(field=field):
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'bornes estimation'):
                    values = (2, 1, None, None) if field == 'charge' else (None, None, 2, 1)
                    self.estimation('bad', *values)
                cols = ('charge_min_h', 'charge_max_h') if field == 'charge' else ('cout_min', 'cout_max')
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'bornes estimation'):
                    self.c.execute(f"UPDATE estimation_action SET {cols[0]}=4, {cols[1]}=1 WHERE id='ok'")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'valeur mesure'):
            self.mesure('bad', 'texte')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'valeur mesure'):
            self.c.execute("UPDATE mesure_indicateur SET valeur='texte' WHERE id='ok'")
        self.c.commit()
        self.reopen()
        self.assertEqual(list(self.c.iterdump()), before)
        self.assertEqual(db.integrity_problems(self.c), [])


if __name__ == '__main__':
    unittest.main()
