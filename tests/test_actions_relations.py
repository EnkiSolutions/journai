import sqlite3
import tempfile
import unittest
from pathlib import Path

from journai import db, migrations


SCHEMA = Path(__file__).resolve().parents[1] / 'journai' / 'migrations'
NOW = '2026-01-01T00:00:00.000000+00:00'


def uid(kind, number):
    return f'{kind:08d}-0000-4000-8000-{number:012d}'


class ActionRelationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'relations.db'
        self.connection = db.connect(self.path)
        self.addCleanup(self.close)
        c = self.connection
        self.assertEqual(c.execute('PRAGMA foreign_keys').fetchone()[0], 1)
        self.assertEqual(migrations.migrate(c, SCHEMA), [f'{n:04}' for n in range(1, 10)])
        for number in (1, 2, 3):
            c.execute('INSERT INTO utilisateur (id, nom_affiche, email, cree_le) VALUES (?, ?, ?, ?)',
                      (uid(1, number), f'Utilisateur {number}', f'test{number}@example.invalid', NOW))
        for space in (1, 2):
            c.execute('INSERT INTO espace (id, nom, cree_par, cree_le) VALUES (?, ?, ?, ?)',
                      (uid(2, space), f'Espace {space}', uid(1, 1), NOW))
            c.execute("INSERT INTO structure (id, espace_id, nom, type_structure, cree_par, cree_le) VALUES (?, ?, 'Structure', 'autre', ?, ?)",
                      (uid(3, space), uid(2, space), uid(1, 1), NOW))
            c.execute("INSERT INTO projet (id, espace_id, structure_pilote_id, nom, finalite, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, 'Projet', 'Finalité', ?, ?, ?)",
                      (uid(4, space), uid(2, space), uid(3, space), uid(1, 1), uid(1, 1), NOW))
        for number in range(1, 7):
            self.insert_action(number, 1 if number < 6 else 2, None)
        c.commit()

    def insert_action(self, number, space, parent):
        return self.connection.execute(
            "INSERT INTO action (id, espace_id, projet_pilote_id, action_parent_id, titre, description, nature, responsable_id, critere_acceptation, cree_par, cree_le) VALUES (?, ?, ?, ?, ?, 'Description', 'livrable', ?, 'Critère', ?, ?)",
            (uid(5, number), uid(2, space), uid(4, space), parent, f'Action {number}', uid(1, 1), uid(1, 1), NOW))

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def snapshots(self):
        return {table: [tuple(row) for row in self.connection.execute(f'SELECT * FROM {table} ORDER BY 1, 2')]
                for table in ('utilisateur', 'espace', 'structure', 'projet', 'action', 'dependance_action', 'contribution_action')}

    def refused(self, family, operation):
        before = self.snapshots()
        with self.assertRaises(sqlite3.IntegrityError) as error:
            operation()
        self.assertEqual(error.exception.sqlite_errorname, family)
        self.assertEqual(self.snapshots(), before)

    def persisted(self, expected):
        self.connection.commit()
        self.close()
        self.connection = db.connect(self.path)
        self.assertEqual(self.connection.execute('PRAGMA foreign_keys').fetchone()[0], 1)
        self.assertEqual(self.snapshots(), expected)
        self.assertEqual(db.integrity_problems(self.connection), [])

    def test_parent_direct(self):
        c = self.connection
        before = self.snapshots()
        self.assertEqual(self.insert_action(7, 1, uid(5, 2)).rowcount, 1)
        action7 = (uid(5, 7), uid(2, 1), uid(4, 1), uid(5, 2), 'Action 7', 'Description',
                   'livrable', 'propose', uid(1, 1), None, None, None, 'Critère', 1,
                   uid(1, 1), NOW, None, None, None)
        expected = dict(before)
        expected['action'] = before['action'] + [action7]
        self.assertEqual(self.snapshots(), expected)
        for parent in (uid(5, 3), None):
            self.assertEqual(c.execute('UPDATE action SET action_parent_id = ? WHERE id = ?',
                                       (parent, uid(5, 7))).rowcount, 1)
            action7 = (*action7[:3], parent, *action7[4:])
            expected['action'] = before['action'] + [action7]
            self.assertEqual(self.snapshots(), expected)
        for parent, family in ((uid(5, 99), 'SQLITE_CONSTRAINT_FOREIGNKEY'),
                               (uid(5, 6), 'SQLITE_CONSTRAINT_FOREIGNKEY'),
                               (uid(5, 8), 'SQLITE_CONSTRAINT_CHECK')):
            with self.subTest(operation='insert', parent=parent):
                self.refused(family, lambda: self.insert_action(8, 1, parent))
        for parent, family in ((uid(5, 99), 'SQLITE_CONSTRAINT_FOREIGNKEY'),
                               (uid(5, 6), 'SQLITE_CONSTRAINT_FOREIGNKEY'),
                               (uid(5, 7), 'SQLITE_CONSTRAINT_CHECK')):
            with self.subTest(operation='update', parent=parent):
                self.refused(family, lambda: c.execute('UPDATE action SET action_parent_id = ? WHERE id = ?',
                                                       (parent, uid(5, 7))))
        self.persisted(expected)

    def test_dependances(self):
        c = self.connection
        expected = self.snapshots()
        insert = 'INSERT INTO dependance_action VALUES (?, ?, ?, ?)'
        update = ('UPDATE dependance_action SET action_id = ?, prerequis_id = ?, espace_id = ? '
                  'WHERE action_id = ? AND prerequis_id = ?')
        first = (uid(5, 1), uid(5, 2), uid(2, 1), 'Préparer')
        neighbor = (uid(5, 1), uid(5, 3), uid(2, 1), 'Vérifier')
        moving = (uid(5, 2), uid(5, 4), uid(2, 1), 'Organiser')
        for row in (first, neighbor, moving):
            self.assertEqual(c.execute(insert, row).rowcount, 1)
        expected['dependance_action'] = [first, neighbor, moving]
        self.assertEqual(self.snapshots(), expected)
        moved = (uid(5, 2), uid(5, 5), uid(2, 1), 'Organiser')
        self.assertEqual(c.execute(update, (*moved[:3], *moving[:2])).rowcount, 1)
        expected['dependance_action'] = [first, neighbor, moved]
        self.assertEqual(self.snapshots(), expected)
        self.assertEqual(c.execute('UPDATE dependance_action SET justification = ? WHERE action_id = ? AND prerequis_id = ?',
                                   ('Planifier', *moved[:2])).rowcount, 1)
        moved = (*moved[:3], 'Planifier')
        expected['dependance_action'] = [first, neighbor, moved]
        self.assertEqual(self.snapshots(), expected)
        cases = (
            (first[:3], 'SQLITE_CONSTRAINT_PRIMARYKEY'),
            ((uid(5, 4), uid(5, 4), uid(2, 1)), 'SQLITE_CONSTRAINT_CHECK'),
            ((uid(5, 99), uid(5, 4), uid(2, 1)), 'SQLITE_CONSTRAINT_FOREIGNKEY'),
            ((uid(5, 4), uid(5, 99), uid(2, 1)), 'SQLITE_CONSTRAINT_FOREIGNKEY'),
            ((uid(5, 6), uid(5, 4), uid(2, 1)), 'SQLITE_CONSTRAINT_FOREIGNKEY'),
            ((uid(5, 4), uid(5, 6), uid(2, 1)), 'SQLITE_CONSTRAINT_FOREIGNKEY'),
            ((uid(5, 4), uid(5, 5), uid(2, 2)), 'SQLITE_CONSTRAINT_FOREIGNKEY'),
        )
        for values, family in cases:
            with self.subTest(operation='insert', values=values):
                self.refused(family, lambda: c.execute(insert, (*values, 'Motif')))
            with self.subTest(operation='update', values=values):
                self.refused(family, lambda: c.execute(update, (*values, *moved[:2])))
        self.assertEqual(self.snapshots(), expected)
        self.persisted(expected)

    def test_contributions(self):
        c = self.connection
        expected = self.snapshots()
        insert = 'INSERT INTO contribution_action VALUES (?, ?, ?, ?, ?, ?)'
        update = ('UPDATE contribution_action SET action_id = ?, utilisateur_id = ?, espace_id = ?, '
                  'role_contribution = ?, charge_prevue_h = ?, charge_realisee_h = ? '
                  'WHERE action_id = ? AND utilisateur_id = ?')
        first = (uid(5, 1), uid(1, 1), uid(2, 1), 'responsable', None, 0)
        neighbor = (uid(5, 1), uid(1, 2), uid(2, 1), 'contributeur', 2.5, None)
        moving = (uid(5, 2), uid(1, 3), uid(2, 1), 'relais', 0, 3)
        for row in (first, neighbor, moving):
            self.assertEqual(c.execute(insert, row).rowcount, 1)
        expected['contribution_action'] = [first, neighbor, moving]
        self.assertEqual(self.snapshots(), expected)
        moved = (uid(5, 3), uid(1, 3), uid(2, 1), 'relais', 0, 3)
        self.assertEqual(c.execute(update, (*moved, *moving[:2])).rowcount, 1)
        expected['contribution_action'] = [first, neighbor, moved]
        self.assertEqual(self.snapshots(), expected)
        changed = (*moved[:3], 'consulte', 4.5, 0)
        self.assertEqual(c.execute(update, (*changed, *moved[:2])).rowcount, 1)
        expected['contribution_action'] = [first, neighbor, changed]
        self.assertEqual(self.snapshots(), expected)
        first_updated = (*first[:3], 'contributeur', 1, 2)
        self.assertEqual(c.execute(update, (*first_updated, *first[:2])).rowcount, 1)
        expected['contribution_action'] = [first_updated, neighbor, changed]
        self.assertEqual(self.snapshots(), expected)
        cases = (
            (first, 'SQLITE_CONSTRAINT_PRIMARYKEY'),
            ((uid(5, 4), uid(1, 99), uid(2, 1), 'relais', None, None), 'SQLITE_CONSTRAINT_FOREIGNKEY'),
            ((uid(5, 4), uid(1, 1), uid(2, 1), 'invalide', None, None), 'SQLITE_CONSTRAINT_CHECK'),
            ((uid(5, 4), uid(1, 1), uid(2, 1), 'relais', -1, None), 'SQLITE_CONSTRAINT_CHECK'),
            ((uid(5, 4), uid(1, 1), uid(2, 1), 'relais', None, -1), 'SQLITE_CONSTRAINT_CHECK'),
            ((uid(5, 99), uid(1, 1), uid(2, 1), 'relais', None, None), 'SQLITE_CONSTRAINT_FOREIGNKEY'),
            ((uid(5, 6), uid(1, 1), uid(2, 1), 'relais', None, None), 'SQLITE_CONSTRAINT_FOREIGNKEY'),
            ((uid(5, 4), uid(1, 1), uid(2, 2), 'relais', None, None), 'SQLITE_CONSTRAINT_FOREIGNKEY'),
        )
        for values, family in cases:
            with self.subTest(operation='insert', values=values):
                self.refused(family, lambda: c.execute(insert, values))
            with self.subTest(operation='update', values=values):
                self.refused(family, lambda: c.execute(update, (*values, *changed[:2])))
        self.assertEqual(self.snapshots(), expected)
        self.persisted(expected)


if __name__ == '__main__':
    unittest.main()
