import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from journai import db, migrations


SCHEMA = Path(__file__).resolve().parents[1] / 'journai' / 'migrations'
NOW = '2026-01-01T00:00:00.000000+00:00'


def uid(kind, number):
    return f'{kind:08d}-0000-4000-8000-{number:012d}'


class OccurrencesStablesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.path = root / 'data.db'
        self.old_schema = root / 'schema_6'
        self.old_schema.mkdir()
        for file in SCHEMA.glob('000[1-6]_*.sql'):
            shutil.copyfile(file, self.old_schema / file.name)
        self.connection = db.connect(self.path)
        self.addCleanup(self.close)
        migrations.migrate(self.connection, self.old_schema)
        c = self.connection
        c.execute('INSERT INTO utilisateur (id, nom_affiche, email, cree_le) VALUES (?, ?, ?, ?)',
                  (uid(1, 1), 'Test', 'test@example.invalid', NOW))
        for space in (1, 2):
            c.execute('INSERT INTO espace (id, nom, cree_par, cree_le) VALUES (?, ?, ?, ?)',
                      (uid(2, space), f'Espace {space}', uid(1, 1), NOW))
            c.execute("INSERT INTO structure (id, espace_id, nom, type_structure, cree_par, cree_le) VALUES (?, ?, 'Structure', 'autre', ?, ?)",
                      (uid(3, space), uid(2, space), uid(1, 1), NOW))
            c.execute("INSERT INTO projet (id, espace_id, structure_pilote_id, nom, finalite, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, 'Projet', 'Finalité', ?, ?, ?)",
                      (uid(4, space), uid(2, space), uid(3, space), uid(1, 1), uid(1, 1), NOW))
            c.execute("INSERT INTO parcours (id, espace_id, projet_id, nom, finalite, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, 'Parcours', 'Finalité', ?, ?, ?)",
                      (uid(5, space), uid(2, space), uid(4, space), uid(1, 1), uid(1, 1), NOW))
            c.execute("INSERT INTO canal (id, espace_id, nom, type_canal, cree_par, cree_le) VALUES (?, ?, 'Canal', 'autre', ?, ?)",
                      (uid(8, space), uid(2, space), uid(1, 1), NOW))
            c.execute("INSERT INTO point_contact (id, espace_id, projet_id, nom, intention, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, 'Contact', 'Intention', ?, ?, ?)",
                      (uid(9, space), uid(2, space), uid(4, space), uid(1, 1), uid(1, 1), NOW))
        for version, space, number in ((1, 1, 1), (2, 1, 2), (3, 2, 1)):
            c.execute("INSERT INTO version_parcours (id, parcours_id, espace_id, numero, perspective, cree_par, cree_le) VALUES (?, ?, ?, ?, 'observee', ?, ?)",
                      (uid(6, version), uid(5, space), uid(2, space), number, uid(1, 1), NOW))
        for step, version, space in ((1, 1, 1), (2, 1, 1), (3, 2, 1), (4, 3, 2)):
            self.step(step, version, space)
        c.commit()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def reopen(self):
        self.close()
        self.connection = db.connect(self.path)

    def step(self, step, version, space=1, key=None):
        self.connection.execute(
            "INSERT INTO etape (id, version_parcours_id, espace_id, cle_stable, titre, objectif_public, ordre_affichage, cree_par, cree_le) VALUES (?, ?, ?, ?, 'Étape', 'Objectif', 0, ?, ?)",
            (uid(7, step), uid(6, version), uid(2, space), key or uid(11, step), uid(1, 1), NOW))

    def occurrence(self, number, step, key, space=1, contact=None, channel=None):
        self.connection.execute(
            "INSERT INTO occurrence_contact (id, espace_id, etape_id, point_contact_id, canal_id, cle_stable, besoin_public, experience_attendue, criticite, frequence, etat_operationnel, ordre_affichage, cree_par, cree_le) VALUES (?, ?, ?, ?, ?, ?, 'Besoin', 'Expérience', 'mineure', 'continue', 'prevu', 0, ?, ?)",
            (uid(10, number), uid(2, space), uid(7, step), contact or uid(9, space),
             channel or uid(8, space), key, uid(1, 1), NOW))

    def upgrade(self):
        self.assertEqual(migrations.migrate(self.connection, SCHEMA), ['0007'])

    def test_upgrade_preserves_rows_and_is_idempotent(self):
        self.occurrence(1, 1, uid(11, 1))
        self.occurrence(2, 3, uid(11, 1))
        self.connection.commit()
        before = [tuple(row) for row in self.connection.execute('SELECT * FROM occurrence_contact ORDER BY id')]
        self.upgrade()
        self.reopen()
        self.assertEqual([tuple(row) for row in self.connection.execute('SELECT * FROM occurrence_contact ORDER BY id')], before)
        self.assertEqual(migrations.applied_versions(self.connection), [f'{n:04}' for n in range(1, 8)])
        self.assertEqual(migrations.migrate(self.connection, SCHEMA), [])
        self.assertEqual(db.integrity_problems(self.connection), [])

    def test_duplicate_upgrade_is_atomic(self):
        self.occurrence(1, 1, uid(11, 1))
        self.occurrence(2, 2, uid(11, 1))
        self.connection.commit()
        before = list(self.connection.iterdump())
        with self.assertRaisesRegex(migrations.MigrationError, 'cles_occurrences_dupliquees'):
            self.upgrade()
        self.reopen()
        self.assertEqual(list(self.connection.iterdump()), before)
        self.assertEqual(migrations.applied_versions(self.connection), [f'{n:04}' for n in range(1, 7)])

    def test_collisions_moves_and_existing_constraints(self):
        self.upgrade()
        c = self.connection
        c.execute("INSERT INTO canal (id, espace_id, nom, type_canal, cree_par, cree_le) VALUES (?, ?, 'Autre canal', 'autre', ?, ?)",
                  (uid(8, 3), uid(2, 1), uid(1, 1), NOW))
        self.occurrence(1, 1, uid(11, 1))  # Même clé qu'une étape : namespaces indépendants.
        self.occurrence(2, 2, uid(11, 2))
        self.occurrence(3, 3, uid(11, 1))  # Même clé, autre version.
        for step in (1, 2):
            with self.subTest(step=step), self.assertRaisesRegex(sqlite3.IntegrityError, 'cle stable occurrence'):
                self.occurrence(4, step, uid(11, 1), channel=uid(8, 3))
        c.execute('UPDATE occurrence_contact SET cle_stable = cle_stable WHERE id = ?', (uid(10, 1),))
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'cle stable occurrence'):
            c.execute('UPDATE occurrence_contact SET cle_stable = ? WHERE id = ?', (uid(11, 1), uid(10, 2)))
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'cle stable occurrence'):
            c.execute('UPDATE occurrence_contact SET etape_id = ? WHERE id = ?', (uid(7, 2), uid(10, 3)))
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'cle stable occurrence'):
            c.execute('UPDATE etape SET version_parcours_id = ? WHERE id = ?', (uid(6, 1), uid(7, 3)))
        with self.assertRaises(sqlite3.IntegrityError):
            self.occurrence(4, 1, uid(11, 4))  # étape/contact/canal déjà utilisé
        for step, contact, channel in ((4, uid(9, 1), uid(8, 1)),
                                       (1, uid(9, 2), uid(8, 1)),
                                       (1, uid(9, 1), uid(8, 2))):
            with self.subTest(step=step, contact=contact, channel=channel), self.assertRaises(sqlite3.IntegrityError):
                self.occurrence(4, step, uid(11, 4), contact=contact, channel=channel)
        self.occurrence(4, 4, uid(11, 1), space=2)
        self.occurrence(5, 1, uid(11, 5), channel=uid(8, 3))
        c.execute('UPDATE occurrence_contact SET cle_stable = ? WHERE id = ?', (uid(11, 3), uid(10, 3)))
        c.execute('UPDATE etape SET version_parcours_id = ? WHERE id = ?', (uid(6, 1), uid(7, 3)))
        c.execute('UPDATE occurrence_contact SET canal_id = ?, etape_id = ? WHERE id = ?',
                  (uid(8, 3), uid(7, 2), uid(10, 1)))
        c.execute('UPDATE occurrence_contact SET besoin_public = ? WHERE id = ?', ('Modifié', uid(10, 2)))
        c.commit()
        self.reopen()
        self.assertEqual(self.connection.execute('SELECT etape_id FROM occurrence_contact WHERE id = ?', (uid(10, 1),)).fetchone()[0], uid(7, 2))
        self.assertEqual(db.integrity_problems(self.connection), [])

    def test_deferred_step_insertion_and_update(self):
        self.upgrade()
        c = self.connection
        self.occurrence(1, 1, uid(11, 1))
        c.commit()
        c.execute('PRAGMA defer_foreign_keys = ON')
        self.occurrence(2, 5, uid(11, 1))
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'cle stable occurrence'):
            self.step(5, 1)
        self.step(5, 2)
        self.occurrence(3, 6, uid(11, 1))
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'cle stable occurrence'):
            c.execute('UPDATE etape SET id = ? WHERE id = ?', (uid(7, 6), uid(7, 3)))
        c.execute('UPDATE occurrence_contact SET cle_stable = ? WHERE id = ?', (uid(11, 6), uid(10, 3)))
        self.step(6, 1)
        c.commit()
        self.reopen()
        self.assertEqual(db.integrity_problems(self.connection), [])
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM occurrence_contact').fetchone()[0], 3)


if __name__ == '__main__':
    unittest.main()

