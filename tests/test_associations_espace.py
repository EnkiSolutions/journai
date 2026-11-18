import sqlite3
import tempfile
import unittest
from pathlib import Path

from journai import db, migrations


SCHEMA = Path(__file__).resolve().parents[1] / 'journai' / 'migrations'
NOW = '2026-01-01T00:00:00.000000+00:00'


def uid(kind, number):
    return f'{kind:08d}-0000-4000-8000-{number:012d}'


class AssociationsEspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'data.db'
        self.connection = db.connect(self.path)
        self.addCleanup(self.close)
        self.assertEqual(migrations.migrate(self.connection, SCHEMA),
                         [f'{n:04}' for n in range(1, 11)])
        c = self.connection
        c.execute('INSERT INTO utilisateur (id, nom_affiche, email, cree_le) VALUES (?, ?, ?, ?)',
                  (uid(1, 1), 'Test', 'test@example.invalid', NOW))
        for space in (1, 2):
            c.execute('INSERT INTO espace (id, nom, cree_par, cree_le) VALUES (?, ?, ?, ?)',
                      (uid(2, space), f'Espace {space}', uid(1, 1), NOW))
        for number, space in ((1, 1), (2, 1), (3, 2)):
            c.execute("INSERT INTO structure (id, espace_id, nom, type_structure, cree_par, cree_le) VALUES (?, ?, ?, 'association', ?, ?)",
                      (uid(3, number), uid(2, space), f'Structure {number}', uid(1, 1), NOW))
            c.execute("INSERT INTO projet (id, espace_id, structure_pilote_id, nom, finalite, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, ?, 'Finalité', ?, ?, ?)",
                      (uid(4, number), uid(2, space), uid(3, number), f'Projet {number}', uid(1, 1), uid(1, 1), NOW))
            c.execute("INSERT INTO parcours (id, espace_id, projet_id, nom, finalite, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, ?, 'Finalité', ?, ?, ?)",
                      (uid(5, number), uid(2, space), uid(4, number), f'Parcours {number}', uid(1, 1), uid(1, 1), NOW))
            c.execute("INSERT INTO public (id, espace_id, nom, role_interlocuteur, cree_par, cree_le) VALUES (?, ?, ?, 'beneficiaire', ?, ?)",
                      (uid(6, number), uid(2, space), f'Public {number}', uid(1, 1), NOW))
        c.commit()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def check_association(self, table, first_column, second_column, first_kind, second_kind, shared_table):
        c = self.connection
        columns = f'{first_column}, {second_column}, espace_id'
        role_column = ', role_dans_projet' if table == 'projet_structure' else ''
        role_value = ", 'partenaire'" if role_column else ''
        insert = f'INSERT INTO {table} ({columns}{role_column}) VALUES (?, ?, ?{role_value})'
        update = f'UPDATE {table} SET {first_column} = ?, {second_column} = ?, espace_id = ? WHERE {first_column} = ? AND {second_column} = ?'
        original = (uid(first_kind, 2), uid(second_kind, 1))
        shared_before = [tuple(row) for row in c.execute(f'SELECT * FROM {shared_table} ORDER BY id')]
        c.execute(insert, (uid(first_kind, 1), uid(second_kind, 1), uid(2, 1)))
        c.execute(insert, (*original, uid(2, 1)))
        self.assertEqual(c.execute(f'SELECT count(*) FROM {shared_table} WHERE id = ?', (uid(second_kind, 1),)).fetchone()[0], 1)
        self.assertEqual(c.execute(update, (uid(first_kind, 2), uid(second_kind, 2), uid(2, 1), *original)).rowcount, 1)
        self.assertEqual(c.execute(update, (*original, uid(2, 1), uid(first_kind, 2), uid(second_kind, 2))).rowcount, 1)
        if role_column:
            c.execute("UPDATE projet_structure SET role_dans_projet = 'co_pilote' WHERE projet_id = ? AND structure_id = ?", original)
        expected = [tuple(row) for row in c.execute(f'SELECT * FROM {table} ORDER BY {first_column}, {second_column}')]
        self.assertEqual([row[:3] for row in expected],
                         [(uid(first_kind, n), uid(second_kind, 1), uid(2, 1)) for n in (1, 2)])
        if role_column:
            self.assertEqual([row[3] for row in expected], ['partenaire', 'co_pilote'])

        with self.assertRaisesRegex(sqlite3.IntegrityError, 'UNIQUE constraint failed'):
            c.execute(insert, (uid(first_kind, 1), uid(second_kind, 1), uid(2, 1)))
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'UNIQUE constraint failed'):
            c.execute(update, (uid(first_kind, 1), uid(second_kind, 1), uid(2, 1), *original))
        for first, second, space in ((3, 2, 1), (1, 3, 1), (1, 2, 2)):
            values = (uid(first_kind, first), uid(second_kind, second), uid(2, space))
            with self.subTest(table=table, operation='insert', values=values):
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
                    c.execute(insert, values)
            with self.subTest(table=table, operation='update', values=values):
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
                    c.execute(update, (*values, *original))
        self.assertEqual([tuple(row) for row in c.execute(f'SELECT * FROM {table} ORDER BY {first_column}, {second_column}')], expected)
        self.assertEqual([tuple(row) for row in c.execute(f'SELECT * FROM {shared_table} ORDER BY id')], shared_before)
        c.commit()
        self.close()
        self.connection = db.connect(self.path)
        c = self.connection
        self.assertEqual([tuple(row) for row in c.execute(f'SELECT * FROM {table} ORDER BY {first_column}, {second_column}')], expected)
        self.assertEqual([tuple(row) for row in c.execute(f'SELECT * FROM {shared_table} ORDER BY id')], shared_before)
        self.assertEqual(db.integrity_problems(c), [])

    def test_projet_structure(self):
        self.check_association('projet_structure', 'projet_id', 'structure_id', 4, 3, 'structure')

    def test_parcours_public(self):
        self.check_association('parcours_public', 'parcours_id', 'public_id', 5, 6, 'public')


if __name__ == '__main__':
    unittest.main()
