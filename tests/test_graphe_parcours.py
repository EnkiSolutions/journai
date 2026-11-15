import sqlite3
import tempfile
import unittest
from pathlib import Path

from journai import db, migrations


SCHEMA = Path(__file__).resolve().parents[1] / 'journai' / 'migrations'
NOW = '2026-01-01T00:00:00.000000+00:00'


def uid(kind, number):
    return f'{kind:08d}-0000-4000-8000-{number:012d}'


class GrapheParcoursTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'data.db'
        self.connection = db.connect(self.path)
        self.addCleanup(self.close)
        self.assertEqual(migrations.migrate(self.connection, SCHEMA),
                         [f'{n:04}' for n in range(1, 9)])
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
        for version, space, number in ((1, 1, 1), (2, 1, 2), (3, 2, 1)):
            c.execute("INSERT INTO version_parcours (id, parcours_id, espace_id, numero, perspective, cree_par, cree_le) VALUES (?, ?, ?, ?, 'observee', ?, ?)",
                      (uid(6, version), uid(5, space), uid(2, space), number, uid(1, 1), NOW))
        for step, version, space in ((1, 1, 1), (2, 1, 1), (3, 1, 1),
                                     (4, 1, 1), (5, 2, 1), (6, 3, 2)):
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
            "INSERT INTO etape (id, version_parcours_id, espace_id, cle_stable, titre, objectif_public, ordre_affichage, cree_par, cree_le) VALUES (?, ?, ?, ?, 'Étape', 'Objectif', ?, ?, ?)",
            (uid(7, step), uid(6, version), uid(2, space), key or uid(8, step), step, uid(1, 1), NOW))

    def transition(self, number, source, destination, version=1, space=1):
        self.connection.execute(
            'INSERT INTO transition_etape (id, version_parcours_id, espace_id, etape_source_id, etape_destination_id, ordre_affichage, cree_par, cree_le) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (uid(9, number), uid(6, version), uid(2, space), uid(7, source), uid(7, destination), number, uid(1, 1), NOW))

    def graph(self):
        return ([tuple(row) for row in self.connection.execute(
                    'SELECT id, version_parcours_id, cle_stable FROM etape ORDER BY id')],
                [tuple(row) for row in self.connection.execute(
                    'SELECT id, version_parcours_id, espace_id, etape_source_id, etape_destination_id FROM transition_etape ORDER BY id')])

    def assert_persisted(self, expected):
        self.connection.commit()
        self.reopen()
        self.assertEqual(self.graph(), expected)
        self.assertEqual(db.integrity_problems(self.connection), [])

    def test_graph_survives_reordering_and_reopening(self):
        for number, source, destination in ((1, 1, 2), (2, 1, 3), (3, 2, 1), (4, 1, 4)):
            self.transition(number, source, destination)
        before = self.graph()
        self.assertEqual([(edge[3], edge[4]) for edge in before[1]],
                         [(uid(7, a), uid(7, b)) for a, b in ((1, 2), (1, 3), (2, 1), (1, 4))])
        self.assertNotIn(uid(7, 4), [edge[3] for edge in before[1]])
        self.connection.execute('UPDATE etape SET ordre_affichage = 10 - ordre_affichage WHERE version_parcours_id = ?', (uid(6, 1),))
        self.connection.execute('UPDATE transition_etape SET ordre_affichage = 10 - ordre_affichage')
        self.assertEqual(self.graph(), before)
        self.assert_persisted(before)

    def test_stable_keys_are_unique_per_version_on_insert_and_update(self):
        self.step(7, 2, key=uid(8, 1))
        before = self.graph()
        with self.assertRaises(sqlite3.IntegrityError):
            self.step(8, 1, key=uid(8, 1))
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute('UPDATE etape SET cle_stable = ? WHERE id = ?', (uid(8, 1), uid(7, 2)))
        self.assertEqual(self.graph(), before)
        self.connection.execute('UPDATE etape SET cle_stable = ? WHERE id = ?', (uid(8, 2), uid(7, 5)))
        self.assert_persisted(self.graph())

    def test_transition_endpoints_and_declared_space_are_scoped(self):
        self.transition(1, 1, 2)
        self.connection.execute('UPDATE transition_etape SET etape_destination_id = ? WHERE id = ?', (uid(7, 3), uid(9, 1)))
        before = self.graph()
        for source, destination, space in ((5, 3, 1), (1, 5, 1),
                                            (6, 3, 1), (1, 6, 1), (1, 3, 2)):
            with self.subTest(operation='insert', source=source, destination=destination, space=space):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.transition(3, source, destination, space=space)
            with self.subTest(operation='update', source=source, destination=destination, space=space):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.connection.execute(
                        'UPDATE transition_etape SET etape_source_id = ?, etape_destination_id = ?, espace_id = ? WHERE id = ?',
                        (uid(7, source), uid(7, destination), uid(2, space), uid(9, 1)))
        self.assertEqual(self.graph(), before)
        self.assert_persisted(before)

    def test_linked_steps_and_transition_cannot_change_version(self):
        self.transition(1, 1, 2)
        before = self.graph()
        for step in (1, 2):
            with self.subTest(step=step), self.assertRaises(sqlite3.IntegrityError):
                self.connection.execute('UPDATE etape SET version_parcours_id = ? WHERE id = ?', (uid(6, 2), uid(7, step)))
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute('UPDATE transition_etape SET version_parcours_id = ? WHERE id = ?', (uid(6, 2), uid(9, 1)))
        self.assertEqual(self.graph(), before)
        self.assert_persisted(before)


if __name__ == '__main__':
    unittest.main()
