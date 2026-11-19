import sqlite3
import tempfile
import unittest
from pathlib import Path

from journai import db, migrations


SCHEMA = Path(__file__).resolve().parents[1] / 'journai' / 'migrations'
NOW = '2026-01-01T00:00:00.000000+00:00'
FK = 'SQLITE_CONSTRAINT_FOREIGNKEY'
CHECK = 'SQLITE_CONSTRAINT_CHECK'


def uid(kind, number):
    return f'{kind:08d}-0000-4000-8000-{number:012d}'


class ArbitrageDonneesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'arbitrage.db'
        self.connection = db.connect(self.path)
        self.addCleanup(self.close)
        c = self.connection
        self.assertEqual(c.execute('PRAGMA foreign_keys').fetchone()[0], 1)
        self.assertEqual(migrations.migrate(c, SCHEMA), [f'{n:04}' for n in range(1, 12)])
        for number in (1, 2, 3):
            c.execute('INSERT INTO utilisateur (id, nom_affiche, email, cree_le) VALUES (?, ?, ?, ?)',
                      (uid(1, number), f'Utilisateur {number}', f'test{number}@example.invalid', NOW))
        for space in (1, 2):
            c.execute('INSERT INTO espace (id, nom, cree_par, cree_le) VALUES (?, ?, ?, ?)',
                      (uid(2, space), f'Espace {space}', uid(1, 1), NOW))
            c.execute("INSERT INTO structure (id, espace_id, nom, type_structure, cree_par, cree_le) VALUES (?, ?, 'Structure', 'autre', ?, ?)",
                      (uid(3, space), uid(2, space), uid(1, 1), NOW))
        for number, space in ((1, 1), (2, 1), (3, 1), (4, 2)):
            c.execute("INSERT INTO projet (id, espace_id, structure_pilote_id, nom, finalite, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, ?, 'Finalité', ?, ?, ?)",
                      (uid(4, number), uid(2, space), uid(3, space), f'Projet {number}', uid(1, 1), uid(1, 1), NOW))
        for number, space, project in ((1, 1, 1), (2, 1, 2), (3, 2, 4)):
            c.execute("INSERT INTO action (id, espace_id, projet_pilote_id, titre, description, nature, responsable_id, critere_acceptation, cree_par, cree_le) VALUES (?, ?, ?, ?, 'Description', 'livrable', ?, 'Critère', ?, ?)",
                      (uid(5, number), uid(2, space), uid(4, project), f'Action {number}', uid(1, 1), uid(1, 1), NOW))
        for action, project, space in ((1, 1, 1), (1, 2, 1), (2, 2, 1), (3, 4, 2)):
            c.execute("INSERT INTO action_projet (action_id, projet_id, espace_id, motif_rattachement) VALUES (?, ?, ?, 'Partage')",
                      (uid(5, action), uid(4, project), uid(2, space)))
        c.commit()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def snapshots(self):
        tables = ('utilisateur', 'espace', 'structure', 'projet', 'action', 'action_projet',
                  'estimation_action', 'evaluation_action')
        return {table: [tuple(row) for row in self.connection.execute(f'SELECT * FROM {table} ORDER BY 1, 2')]
                for table in tables}

    def insert(self, table, row):
        columns = ', '.join(row)
        values = ', '.join('?' for _ in row)
        return self.connection.execute(f'INSERT INTO {table} ({columns}) VALUES ({values})', tuple(row.values()))

    def update(self, table, row_id, changes):
        assignments = ', '.join(f'{column} = ?' for column in changes)
        return self.connection.execute(f'UPDATE {table} SET {assignments} WHERE id = ?', (*changes.values(), row_id))

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

    def refusal_cases(self, table, base, moving, cases):
        for label, changes, family in cases:
            for operation in ('insert', 'update'):
                with self.subTest(table=table, fault=label, operation=operation):
                    if operation == 'insert':
                        candidate = {**base, 'id': uid(9, 99), **changes}
                        self.refused(family, lambda: self.insert(table, candidate))
                    else:
                        self.refused(family, lambda: self.update(table, moving, changes))

    def test_estimations(self):
        table = 'estimation_action'
        expected = self.snapshots()
        first = dict(id=uid(6, 1), action_id=uid(5, 1), espace_id=uid(2, 1), auteur_id=uid(1, 1),
                     charge_min_h=0, charge_probable_h=0, charge_max_h=0,
                     cout_min=4, cout_probable=4, cout_max=4, devise='EUR',
                     complexite_technique='faible', complexite_organisationnelle='moyenne',
                     incertitude='forte', justification='Première estimation', cree_le=NOW)
        neighbor = dict(first, id=uid(6, 2), auteur_id=uid(1, 2), charge_min_h=None,
                        charge_probable_h=None, charge_max_h=2.5, cout_min=0, cout_probable=3,
                        cout_max=8, devise=None, complexite_technique='forte',
                        complexite_organisationnelle='faible', incertitude='moyenne',
                        justification='Autre estimation')
        for row in (first, neighbor):
            self.assertEqual(self.insert(table, row).rowcount, 1)
        expected[table] = [(*first.values(), 1), (*neighbor.values(), 1)]
        self.assertEqual(self.snapshots(), expected)
        self.assertEqual(self.update(table, first['id'], {'action_id': uid(5, 2)}).rowcount, 1)
        first['action_id'] = uid(5, 2)
        expected[table] = [(*first.values(), 1), (*neighbor.values(), 1)]
        self.assertEqual(self.snapshots(), expected)
        changes = dict(charge_min_h=1, charge_probable_h=2, charge_max_h=3, cout_min=0,
                       cout_probable=5, cout_max=9, devise='USD', complexite_technique='moyenne',
                       complexite_organisationnelle='forte', incertitude='faible', justification='Révisée')
        self.assertEqual(self.update(table, first['id'], changes).rowcount, 1)
        first.update(changes)
        expected[table] = [(*first.values(), 1), (*neighbor.values(), 1)]
        self.assertEqual(self.snapshots(), expected)
        numeric = ('charge_min_h', 'charge_probable_h', 'charge_max_h',
                   'cout_min', 'cout_probable', 'cout_max')
        self.assertEqual(self.update(table, first['id'], dict.fromkeys(numeric)).rowcount, 1)
        first.update(dict.fromkeys(numeric))
        expected[table] = [(*first.values(), 1), (*neighbor.values(), 1)]
        self.assertEqual(self.snapshots(), expected)
        for column in numeric:
            for value in (0, 2.5, None):
                with self.subTest(column=column, value=value):
                    self.assertEqual(self.update(table, first['id'], {column: value}).rowcount, 1)
                    first[column] = value
                    expected[table] = [(*first.values(), 1), (*neighbor.values(), 1)]
                    self.assertEqual(self.snapshots(), expected)
        cases = [
            ('action absente', {'action_id': uid(5, 99)}, FK),
            ('auteur absent', {'auteur_id': uid(1, 99)}, FK),
            ('action hors espace', {'action_id': uid(5, 3)}, FK),
            ('espace incohérent', {'espace_id': uid(2, 2)}, FK),
            ('identifiant pris', {'id': neighbor['id']}, 'SQLITE_CONSTRAINT_UNIQUE'),
            ('révision', {'revision': 0}, CHECK),
            ('devise courte', {'devise': 'EU'}, CHECK),
            ('devise longue', {'devise': 'EURO'}, CHECK),
        ]
        for prefix in ('charge', 'cout'):
            columns = ([f'{prefix}_{part}_h' for part in ('min', 'probable', 'max')]
                       if prefix == 'charge' else [f'{prefix}_{part}' for part in ('min', 'probable', 'max')])
            for column in columns:
                cases.append((f'{column} négatif', {**dict.fromkeys(columns), column: -1}, CHECK))
            cases.extend([
                (f'{prefix} probable inférieur au minimum', dict(zip(columns, (2, 1, 3))), CHECK),
                (f'{prefix} maximum inférieur au probable', dict(zip(columns, (0, 2, 1))), CHECK),
                (f'{prefix} bornes inversées sans probable', dict(zip(columns, (2, None, 1))),
                 'SQLITE_CONSTRAINT_TRIGGER'),
            ])
        for column in ('complexite_technique', 'complexite_organisationnelle', 'incertitude'):
            cases.append((f'{column} invalide', {column: 'invalide'}, CHECK))
        self.refusal_cases(table, first, first['id'], cases)
        self.assertEqual(self.snapshots(), expected)
        self.persisted(expected)

    def test_evaluations(self):
        table = 'evaluation_action'
        expected = self.snapshots()
        first = dict(id=uid(7, 1), action_id=uid(5, 1), projet_id=uid(4, 1),
                     espace_id=uid(2, 1), auteur_id=uid(1, 1), importance='faible',
                     impact_attendu='moyenne', confiance='forte', justification='Premier avis', cree_le=NOW)
        neighbor = dict(first, id=uid(7, 2), auteur_id=uid(1, 2), importance='forte',
                        impact_attendu='faible', confiance='moyenne', justification='Autre avis')
        other_project = dict(first, id=uid(7, 3), projet_id=uid(4, 2), auteur_id=uid(1, 3),
                             justification='Avis projet deux')
        other_space = dict(first, id=uid(7, 4), action_id=uid(5, 3), projet_id=uid(4, 4),
                           espace_id=uid(2, 2), justification='Avis second espace')
        rows = (first, neighbor, other_project, other_space)
        for row in rows:
            self.assertEqual(self.insert(table, row).rowcount, 1)
        expected[table] = [(*row.values(), 1) for row in rows]
        self.assertEqual(self.snapshots(), expected)
        self.assertEqual(self.update(table, first['id'], {'action_id': uid(5, 2), 'projet_id': uid(4, 2)}).rowcount, 1)
        first.update(action_id=uid(5, 2), projet_id=uid(4, 2))
        expected[table] = [(*row.values(), 1) for row in rows]
        self.assertEqual(self.snapshots(), expected)
        changes = dict(importance='moyenne', impact_attendu='forte', confiance='faible', justification='Avis révisé')
        self.assertEqual(self.update(table, first['id'], changes).rowcount, 1)
        first.update(changes)
        expected[table] = [(*row.values(), 1) for row in rows]
        self.assertEqual(self.snapshots(), expected)
        self.refusal_cases(table, other_space, other_space['id'], [
            ('couple second espace, espace déclaré incohérent', {'espace_id': uid(2, 1)}, FK),
        ])
        cases = [
            ('couple absent, objets présents', {'projet_id': uid(4, 3)}, FK),
            ('action absente', {'action_id': uid(5, 99)}, FK),
            ('projet absent', {'projet_id': uid(4, 99)}, FK),
            ('auteur absent', {'auteur_id': uid(1, 99)}, FK),
            ('action hors espace, couple existant', {'action_id': uid(5, 3), 'projet_id': uid(4, 4)}, FK),
            ('projet hors espace', {'projet_id': uid(4, 4)}, FK),
            ('espace incohérent, couple existant', {'espace_id': uid(2, 2)}, FK),
            ('identifiant pris', {'id': neighbor['id']}, 'SQLITE_CONSTRAINT_UNIQUE'),
            ('révision', {'revision': 0}, CHECK),
        ]
        for column in ('importance', 'impact_attendu', 'confiance'):
            cases.append((f'{column} invalide', {column: 'invalide'}, CHECK))
        self.refusal_cases(table, first, first['id'], cases)
        self.assertEqual(self.snapshots(), expected)
        self.persisted(expected)


if __name__ == '__main__':
    unittest.main()
