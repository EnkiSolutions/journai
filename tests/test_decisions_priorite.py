import shutil
import tempfile
import unittest
from pathlib import Path

import test_arbitrage_donnees as arb
from test_arbitrage_donnees import CHECK, FK, NOW, uid


TABLE = 'decision_priorite'
UNIQUE = 'SQLITE_CONSTRAINT_UNIQUE'


class DecisionPrioriteTests(unittest.TestCase):
    close = arb.ArbitrageDonneesTests.close
    insert = arb.ArbitrageDonneesTests.insert
    update = arb.ArbitrageDonneesTests.update
    refused = arb.ArbitrageDonneesTests.refused
    refusal_cases = arb.ArbitrageDonneesTests.refusal_cases
    persisted = arb.ArbitrageDonneesTests.persisted

    def snapshots(self):
        result = arb.ArbitrageDonneesTests.snapshots(self)
        result[TABLE] = [tuple(row) for row in self.connection.execute(
            'SELECT * FROM decision_priorite ORDER BY id')]
        return result

    def setUp(self):
        arb.ArbitrageDonneesTests.setUp(self)
        expected = self.snapshots()
        for number, action, space in ((1, 1, 1), (2, 1, 1), (3, 2, 1), (4, 3, 2)):
            row = dict(id=uid(6, number), action_id=uid(5, action), espace_id=uid(2, space),
                       auteur_id=uid(1, 2), complexite_technique='faible',
                       complexite_organisationnelle='moyenne', incertitude='forte',
                       justification=f'Estimation {number}', cree_le=NOW)
            self.assertEqual(self.insert('estimation_action', row).rowcount, 1)
            expected['estimation_action'].append((row['id'], row['action_id'], row['espace_id'],
                row['auteur_id'], None, None, None, None, None, None, None, 'faible',
                'moyenne', 'forte', row['justification'], NOW, 1))
            self.assertEqual(self.snapshots(), expected)
        for number, action, project, space in ((1, 1, 1, 1), (2, 1, 1, 1),
                                                (3, 1, 2, 1), (4, 3, 4, 2)):
            row = dict(id=uid(7, number), action_id=uid(5, action), projet_id=uid(4, project),
                       espace_id=uid(2, space), auteur_id=uid(1, 3), importance='forte',
                       impact_attendu='moyenne', confiance='faible',
                       justification=f'Avis {number}', cree_le=NOW)
            self.assertEqual(self.insert('evaluation_action', row).rowcount, 1)
            expected['evaluation_action'].append((*row.values(), 1))
            self.assertEqual(self.snapshots(), expected)
        self.expected = expected

    def decision(self, number, *, project=1, space=1, action=1, estimation=1, evaluation=1,
                 classe='a_traiter', rang=1, replaces=None):
        return dict(id=uid(8, number), action_id=uid(5, action), projet_id=uid(4, project),
                    espace_id=uid(2, space), estimation_retenue_id=uid(6, estimation),
                    evaluation_retenue_id=uid(7, evaluation), classe_priorite=classe, rang=rang,
                    motif=f'Décision {number}', decideur_id=uid(1, 1), decide_le=NOW,
                    remplace_decision_id=replaces, revision=1)

    def add_decision(self, row, *, default_revision=False):
        values = dict(row)
        if default_revision:
            del values['revision']
        self.assertEqual(self.insert(TABLE, values).rowcount, 1)
        self.expected[TABLE].append(tuple(row.values()))
        self.expected[TABLE].sort()
        self.assertEqual(self.snapshots(), self.expected)

    def change_decision(self, row, changes):
        self.assertEqual(self.update(TABLE, row['id'], changes).rowcount, 1)
        self.expected[TABLE].remove(tuple(row.values()))
        row.update(changes)
        self.expected[TABLE].append(tuple(row.values()))
        self.expected[TABLE].sort()
        self.assertEqual(self.snapshots(), self.expected)

    def test_decisions_independantes_et_modifications(self):
        first = self.decision(1)
        second = self.decision(2, project=2, evaluation=3, classe='programme', rang=2)
        other = self.decision(3, project=4, space=2, action=3, estimation=4,
                              evaluation=4, classe='differe', rang=3)
        for row in (first, second, other):
            self.add_decision(row, default_revision=True)
        for number, classe in ((4, 'suspendu'), (5, 'renonce')):
            self.add_decision(self.decision(number, classe=classe, rang=number), default_revision=True)
        self.change_decision(first, {'motif': 'Modification locale', 'rang': 9})
        self.change_decision(first, {'estimation_retenue_id': uid(6, 2),
                                     'evaluation_retenue_id': uid(7, 2)})
        self.persisted(self.expected)

    def test_references_et_valeurs_refusees(self):
        first = self.decision(1)
        neighbor = self.decision(2, project=2, evaluation=3)
        other = self.decision(3, action=3, project=4, space=2, estimation=4, evaluation=4)
        for row in (first, neighbor, other):
            self.add_decision(row, default_revision=True)
        cases = [
            ('décideur absent', {'decideur_id': uid(1, 99)}, FK),
            ('estimation absente', {'estimation_retenue_id': uid(6, 99)}, FK),
            ('évaluation absente', {'evaluation_retenue_id': uid(7, 99)}, FK),
            ('action absente', {'action_id': uid(5, 99)}, FK),
            ('projet absent', {'projet_id': uid(4, 99)}, FK),
            ('couple absent', {'projet_id': uid(4, 3)}, FK),
            ('prédécesseur absent', {'remplace_decision_id': uid(8, 99)}, FK),
            ('estimation autre action', {'estimation_retenue_id': uid(6, 3)}, FK),
            ('avis autre projet', {'evaluation_retenue_id': uid(7, 3)}, FK),
            ('estimation autre espace', {'estimation_retenue_id': uid(6, 4)}, FK),
            ('avis autre espace', {'evaluation_retenue_id': uid(7, 4)}, FK),
            ('couple autre espace', {'action_id': uid(5, 3), 'projet_id': uid(4, 4)}, FK),
            ('espace incohérent', {'espace_id': uid(2, 2)}, FK),
            ('classe', {'classe_priorite': 'invalide'}, CHECK),
            ('rang nul', {'rang': 0}, CHECK),
            ('rang négatif', {'rang': -1}, CHECK),
            ('révision nulle', {'revision': 0}, CHECK),
            ('id pris', {'id': neighbor['id']}, UNIQUE),
        ]
        self.refusal_cases(TABLE, first, first['id'], cases)
        self.refusal_cases(TABLE, other, other['id'], [
            ('second espace incohérent', {'espace_id': uid(2, 1)}, FK),
        ])
        self.assertEqual(self.snapshots(), self.expected)
        self.persisted(self.expected)

    def refused_space(self, operation):
        before = self.snapshots()
        with self.assertRaisesRegex(arb.sqlite3.IntegrityError, 'decisions dans des espaces differents') as error:
            operation()
        self.assertEqual(error.exception.sqlite_errorname, 'SQLITE_CONSTRAINT_TRIGGER')
        self.assertEqual(self.snapshots(), before)

    def test_remplacements_inter_espaces_et_deplacements_refuses(self):
        first = self.decision(1)
        second = self.decision(2, replaces=first['id'])
        other = self.decision(3, action=3, project=4, space=2, estimation=4, evaluation=4)
        spare = self.decision(4)
        for row in (first, second, other, spare):
            self.add_decision(row)
        to_other = dict(action_id=uid(5, 3), projet_id=uid(4, 4), espace_id=uid(2, 2),
                        estimation_retenue_id=uid(6, 4), evaluation_retenue_id=uid(7, 4))
        to_first = dict(action_id=uid(5, 1), projet_id=uid(4, 1), espace_id=uid(2, 1),
                        estimation_retenue_id=uid(6, 1), evaluation_retenue_id=uid(7, 1))
        self.change_decision(spare, to_other)
        self.change_decision(spare, to_first)
        for label, operation in (
            ('insertion', lambda: self.insert(TABLE, self.decision(5, replaces=other['id']))),
            ('lien', lambda: self.update(TABLE, second['id'], {'remplace_decision_id': other['id']})),
            ('successeur', lambda: self.update(TABLE, second['id'], to_other)),
            ('prédécesseur', lambda: self.update(TABLE, first['id'], to_other)),
        ):
            with self.subTest(mutation=label):
                self.refused_space(operation)
                self.assertEqual(self.connection.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.persisted(self.expected)

    def test_references_differees_controlees(self):
        c = self.connection
        c.commit()
        c.execute('PRAGMA defer_foreign_keys = ON')
        future = uid(8, 10)
        successor = self.decision(1, replaces=future)
        self.add_decision(successor)
        wrong = self.decision(2, action=3, project=4, space=2, estimation=4, evaluation=4)
        self.add_decision(wrong)
        self.refused_space(lambda: self.insert(TABLE, dict(wrong, id=future)))
        self.refused_space(lambda: self.update(TABLE, wrong['id'], {'id': future}))
        self.add_decision(self.decision(10))
        self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.persisted(self.expected)

    def test_lien_differe_modifie_avant_insertion_du_predecesseur(self):
        successor = self.decision(1)
        self.add_decision(successor)
        self.connection.commit()
        self.connection.execute('PRAGMA defer_foreign_keys = ON')
        future = uid(8, 10)
        self.change_decision(successor, {'remplace_decision_id': future})
        self.refused_space(lambda: self.insert(TABLE, self.decision(
            10, action=3, project=4, space=2, estimation=4, evaluation=4)))
        self.add_decision(self.decision(10))
        self.assertEqual(self.connection.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.persisted(self.expected)

    def test_chaine_de_remplacement_et_suppressions(self):
        first = self.decision(1)
        second = self.decision(2, estimation=2, evaluation=2, replaces=first['id'])
        third = self.decision(3, estimation=1, evaluation=1, replaces=second['id'])
        spare = self.decision(4)
        for row in (first, second, third, spare):
            self.add_decision(row, default_revision=True)
        self.refusal_cases(TABLE, spare, spare['id'], [
            ('prédécesseur déjà remplacé', {'remplace_decision_id': first['id']}, UNIQUE),
        ])
        self.refused(CHECK, lambda: self.insert(TABLE, self.decision(9, replaces=uid(8, 9))))
        self.refused(CHECK, lambda: self.update(TABLE, spare['id'], {'remplace_decision_id': spare['id']}))
        for table, row_id in (('estimation_action', uid(6, 1)),
                              ('evaluation_action', uid(7, 1)), (TABLE, first['id'])):
            with self.subTest(table=table):
                # SQLite reports ON DELETE RESTRICT as a trigger constraint.
                self.refused('SQLITE_CONSTRAINT_TRIGGER', lambda: self.connection.execute(f'DELETE FROM {table} WHERE id = ?', (row_id,)))
        self.assertEqual(self.snapshots(), self.expected)
        self.persisted(self.expected)


class DecisionEspaceMigrationTests(unittest.TestCase):
    close = DecisionPrioriteTests.close
    insert = DecisionPrioriteTests.insert
    update = DecisionPrioriteTests.update
    snapshots = DecisionPrioriteTests.snapshots
    decision = DecisionPrioriteTests.decision
    add_decision = DecisionPrioriteTests.add_decision

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.old_schema = Path(directory.name) / 'schema_9'
        self.old_schema.mkdir()
        for path in arb.SCHEMA.glob('*.sql'):
            if path.name[:4] <= '0009':
                shutil.copyfile(path, self.old_schema / path.name)
        self.schema_10 = Path(directory.name) / 'schema_10'
        shutil.copytree(self.old_schema, self.schema_10)
        for path in arb.SCHEMA.glob('0010_*.sql'):
            shutil.copyfile(path, self.schema_10 / path.name)
        self.path = Path(directory.name) / 'decisions.db'
        self.connection = arb.db.connect(self.path)
        self.addCleanup(self.close)
        c = self.connection
        self.assertEqual(arb.migrations.migrate(c, self.old_schema), [f'{n:04}' for n in range(1, 10)])
        for number in (1, 2, 3):
            c.execute('INSERT INTO utilisateur (id, nom_affiche, email, cree_le) VALUES (?, ?, ?, ?)',
                      (uid(1, number), f'U{number}', f'u{number}@example.invalid', NOW))
        for space, action, project, estimate, evaluation in ((1, 1, 1, 1, 1), (2, 3, 4, 4, 4)):
            c.execute('INSERT INTO espace (id, nom, cree_par, cree_le) VALUES (?, ?, ?, ?)',
                      (uid(2, space), f'E{space}', uid(1, 1), NOW))
            c.execute("INSERT INTO structure (id, espace_id, nom, type_structure, cree_par, cree_le) VALUES (?, ?, 'S', 'autre', ?, ?)",
                      (uid(3, space), uid(2, space), uid(1, 1), NOW))
            c.execute("INSERT INTO projet (id, espace_id, structure_pilote_id, nom, finalite, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, 'P', 'F', ?, ?, ?)",
                      (uid(4, project), uid(2, space), uid(3, space), uid(1, 1), uid(1, 1), NOW))
            c.execute("INSERT INTO action (id, espace_id, projet_pilote_id, titre, description, nature, responsable_id, critere_acceptation, cree_par, cree_le) VALUES (?, ?, ?, 'A', 'D', 'livrable', ?, 'C', ?, ?)",
                      (uid(5, action), uid(2, space), uid(4, project), uid(1, 1), uid(1, 1), NOW))
            c.execute("INSERT INTO action_projet (action_id, projet_id, espace_id, motif_rattachement) VALUES (?, ?, ?, 'M')",
                      (uid(5, action), uid(4, project), uid(2, space)))
            c.execute("INSERT INTO estimation_action (id, action_id, espace_id, auteur_id, complexite_technique, complexite_organisationnelle, incertitude, justification, cree_le) VALUES (?, ?, ?, ?, 'faible', 'moyenne', 'forte', 'E', ?)",
                      (uid(6, estimate), uid(5, action), uid(2, space), uid(1, 1), NOW))
            c.execute("INSERT INTO evaluation_action (id, action_id, projet_id, espace_id, auteur_id, importance, impact_attendu, confiance, justification, cree_le) VALUES (?, ?, ?, ?, ?, 'faible', 'moyenne', 'forte', 'E', ?)",
                      (uid(7, evaluation), uid(5, action), uid(4, project), uid(2, space), uid(1, 1), NOW))
        c.commit()
        self.expected = self.snapshots()

    def test_migration_preserves_valid_link_after_reopen(self):
        first = self.decision(1)
        second = self.decision(2, replaces=first['id'])
        for row in (first, second):
            self.add_decision(row)
        self.connection.commit()
        before = self.snapshots()
        journal = [tuple(row) for row in self.connection.execute('SELECT * FROM schema_migration ORDER BY version')]
        self.assertEqual(arb.migrations.migrate(self.connection, self.schema_10), ['0010'])
        self.close()
        self.connection = arb.db.connect(self.path)
        self.assertEqual(self.snapshots(), before)
        rows = [tuple(row) for row in self.connection.execute('SELECT * FROM schema_migration ORDER BY version')]
        self.assertEqual(rows[:-1], journal)
        self.assertEqual(rows[-1][0], '0010')
        self.assertEqual(arb.migrations.migrate(self.connection, self.schema_10), [])
        self.assertEqual(arb.db.integrity_problems(self.connection), [])

    def test_migration_rejects_existing_cross_space_link_without_changes(self):
        first = self.decision(1)
        second = self.decision(2, action=3, project=4, space=2, estimation=4,
                               evaluation=4, replaces=first['id'])
        for row in (first, second):
            self.add_decision(row)
        self.connection.commit()
        before = list(self.connection.iterdump())
        journal = [tuple(row) for row in self.connection.execute('SELECT * FROM schema_migration ORDER BY version')]
        with self.assertRaisesRegex(arb.migrations.MigrationError, 'decisions_espaces_incoherents'):
            arb.migrations.migrate(self.connection, self.schema_10)
        self.close()
        self.connection = arb.db.connect(self.path)
        self.assertEqual(list(self.connection.iterdump()), before)
        self.assertEqual([tuple(row) for row in self.connection.execute(
            'SELECT * FROM schema_migration ORDER BY version')], journal)
        self.assertEqual(arb.migrations.applied_versions(self.connection), [f'{n:04}' for n in range(1, 10)])
        self.assertEqual(arb.db.integrity_problems(self.connection), [])


if __name__ == '__main__':
    unittest.main()
