import sqlite3
import tempfile
import unittest
from pathlib import Path

from journai import db, migrations


SCHEMA = Path(__file__).resolve().parents[1] / 'journai' / 'migrations'
NOW = '2026-01-01T00:00:00.000000+00:00'
ROLES = ('declencheur', 'realise', 'contributif', 'controle', 'evalue')


def uid(kind, number):
    return f'{kind:08d}-0000-4000-8000-{number:012d}'


class OperationsOccurrencesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'data.db'
        self.connection = db.connect(self.path)
        self.addCleanup(self.close)
        self.assertEqual(migrations.migrate(self.connection, SCHEMA),
                         [f'{n:04}' for n in range(1, 10)])
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
            c.execute("INSERT INTO version_parcours (id, parcours_id, espace_id, numero, perspective, cree_par, cree_le) VALUES (?, ?, ?, 1, 'observee', ?, ?)",
                      (uid(6, space), uid(5, space), uid(2, space), uid(1, 1), NOW))
            c.execute("INSERT INTO canal (id, espace_id, nom, type_canal, cree_par, cree_le) VALUES (?, ?, 'Canal', 'autre', ?, ?)",
                      (uid(8, space), uid(2, space), uid(1, 1), NOW))
            c.execute("INSERT INTO point_contact (id, espace_id, projet_id, nom, intention, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, 'Contact', 'Intention', ?, ?, ?)",
                      (uid(9, space), uid(2, space), uid(4, space), uid(1, 1), uid(1, 1), NOW))
        for number, space in ((1, 1), (2, 1), (3, 1), (4, 2)):
            c.execute("INSERT INTO etape (id, version_parcours_id, espace_id, cle_stable, titre, objectif_public, ordre_affichage, cree_par, cree_le) VALUES (?, ?, ?, ?, 'Étape', 'Objectif', 0, ?, ?)",
                      (uid(7, number), uid(6, space), uid(2, space), uid(11, number), uid(1, 1), NOW))
            c.execute("INSERT INTO occurrence_contact (id, espace_id, etape_id, point_contact_id, canal_id, cle_stable, besoin_public, experience_attendue, criticite, frequence, etat_operationnel, ordre_affichage, cree_par, cree_le) VALUES (?, ?, ?, ?, ?, ?, 'Besoin', 'Expérience', 'mineure', 'continue', 'prevu', 0, ?, ?)",
                      (uid(10, number), uid(2, space), uid(7, number), uid(9, space), uid(8, space), uid(12, number), uid(1, 1), NOW))
            c.execute("INSERT INTO operation (id, espace_id, projet_pilote_id, nom, responsable_id, frequence, mode_execution, etat_operationnel, cree_par, cree_le) VALUES (?, ?, ?, ?, ?, 'continue', 'humain', 'non_assure', ?, ?)",
                      (uid(13, number), uid(2, space), uid(4, space), f'Opération {number}', uid(1, 1), uid(1, 1), NOW))
        c.commit()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def rows(self, table, order):
        return [tuple(row) for row in self.connection.execute(f'SELECT * FROM {table} ORDER BY {order}')]

    def link(self, occurrence, operation, space=1, role='realise'):
        return (uid(10, occurrence), uid(13, operation), uid(2, space), role)


    def test_reuse_isolation_roles_and_persistence(self):
        c = self.connection
        insert = 'INSERT INTO occurrence_operation VALUES (?, ?, ?, ?)'
        update = ('UPDATE occurrence_operation SET occurrence_contact_id = ?, operation_id = ?, '
                  'espace_id = ?, role_operation = ? WHERE occurrence_contact_id = ? AND operation_id = ?')
        definitions = self.rows('operation', 'id')
        occurrences = self.rows('occurrence_contact', 'id')
        for values in (self.link(1, 1), self.link(2, 1, role='declencheur'),
                       self.link(1, 2, role='contributif'), self.link(3, 3, role='controle')):
            c.execute(insert, values)
        self.assertEqual(c.execute('SELECT count(*) FROM operation WHERE id = ?', (uid(13, 1),)).fetchone()[0], 1)
        self.assertEqual(c.execute(update, (*self.link(3, 2, role='evalue'), uid(10, 3), uid(13, 3))).rowcount, 1)
        self.assertEqual(c.execute(update, (*self.link(3, 3, role='controle'), uid(10, 3), uid(13, 2))).rowcount, 1)
        self.assertEqual(self.rows('operation', 'id'), definitions)
        self.assertEqual(self.rows('occurrence_contact', 'id'), occurrences)
        self.assertEqual(c.execute('SELECT etat_operationnel FROM operation WHERE id = ?', (uid(13, 1),)).fetchone()[0], 'non_assure')

        # Les deux opérations sont essayées avec des couples libres et des références valides.
        for role in ROLES:
            with self.subTest(role=role):
                c.execute(insert, self.link(2, 2, role=role))
                self.assertEqual(c.execute('SELECT role_operation FROM occurrence_operation WHERE occurrence_contact_id = ? AND operation_id = ?', (uid(10, 2), uid(13, 2))).fetchone()[0], role)
                c.execute('DELETE FROM occurrence_operation WHERE occurrence_contact_id = ? AND operation_id = ?', (uid(10, 2), uid(13, 2)))
                self.assertEqual(c.execute(update, (*self.link(3, 3, role=role), uid(10, 3), uid(13, 3))).rowcount, 1)
                self.assertEqual(c.execute('SELECT role_operation FROM occurrence_operation WHERE occurrence_contact_id = ? AND operation_id = ?', (uid(10, 3), uid(13, 3))).fetchone()[0], role)
        expected = [self.link(1, 1), self.link(1, 2, role='contributif'),
                    self.link(2, 1, role='declencheur'), self.link(3, 3, role='evalue')]
        self.assertEqual(self.rows('occurrence_operation', 'occurrence_contact_id, operation_id'), expected)

        with self.assertRaisesRegex(sqlite3.IntegrityError, 'UNIQUE constraint failed'):
            c.execute(insert, self.link(1, 1))
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'UNIQUE constraint failed'):
            c.execute(update, (*self.link(1, 1), uid(10, 3), uid(13, 3)))
        self.assertEqual(self.rows('occurrence_operation', 'occurrence_contact_id, operation_id'), expected)

        for values in (self.link(4, 2), self.link(2, 4), self.link(2, 2, space=2)):
            with self.subTest(invalid_space=values):
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
                    c.execute(insert, values)
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
                    c.execute(update, (*values, uid(10, 3), uid(13, 3)))
                self.assertEqual(self.rows('occurrence_operation', 'occurrence_contact_id, operation_id'), expected)

        with self.assertRaisesRegex(sqlite3.IntegrityError, 'CHECK constraint failed: role_operation'):
            c.execute(insert, self.link(2, 2, role='inconnu'))
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'CHECK constraint failed: role_operation'):
            c.execute(update, (*self.link(3, 3, role='inconnu'), uid(10, 3), uid(13, 3)))
        self.assertEqual(self.rows('occurrence_operation', 'occurrence_contact_id, operation_id'), expected)
        self.assertEqual(self.rows('operation', 'id'), definitions)
        self.assertEqual(self.rows('occurrence_contact', 'id'), occurrences)
        c.commit()
        self.close()
        self.connection = db.connect(self.path)
        self.assertEqual(self.rows('occurrence_operation', 'occurrence_contact_id, operation_id'), expected)
        self.assertEqual(self.rows('operation', 'id'), definitions)
        self.assertEqual(self.rows('occurrence_contact', 'id'), occurrences)
        self.assertEqual(db.integrity_problems(self.connection), [])


if __name__ == '__main__':
    unittest.main()
