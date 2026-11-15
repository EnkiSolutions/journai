import sqlite3
import tempfile
import unittest
from pathlib import Path

from journai import db, migrations


SCHEMA = Path(__file__).resolve().parents[1] / 'journai' / 'migrations'
NOW = '2026-01-01T00:00:00.000000+00:00'


def uid(kind, number):
    return f'{kind:08d}-0000-4000-8000-{number:012d}'


class ActionAssociationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'actions.db'
        self.connection = db.connect(self.path)
        self.addCleanup(self.close)
        c = self.connection
        self.assertEqual(c.execute('PRAGMA foreign_keys').fetchone()[0], 1)
        self.assertEqual(migrations.migrate(c, SCHEMA), [f'{n:04}' for n in range(1, 10)])
        c.execute('INSERT INTO utilisateur (id, nom_affiche, email, cree_le) VALUES (?, ?, ?, ?)',
                  (uid(1, 1), 'Test', 'test@example.invalid', NOW))
        for space in (1, 2):
            c.execute('INSERT INTO espace (id, nom, cree_par, cree_le) VALUES (?, ?, ?, ?)',
                      (uid(2, space), f'Espace {space}', uid(1, 1), NOW))
            c.execute("INSERT INTO structure (id, espace_id, nom, type_structure, cree_par, cree_le) VALUES (?, ?, 'Structure', 'autre', ?, ?)",
                      (uid(3, space), uid(2, space), uid(1, 1), NOW))
        for number, space in ((1, 1), (2, 1), (3, 1), (4, 2)):
            c.execute("INSERT INTO projet (id, espace_id, structure_pilote_id, nom, finalite, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, ?, 'Finalité', ?, ?, ?)",
                      (uid(4, number), uid(2, space), uid(3, space), f'Projet {number}', uid(1, 1), uid(1, 1), NOW))
        for space, project in ((1, 1), (2, 4)):
            c.execute("INSERT INTO parcours (id, espace_id, projet_id, nom, finalite, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, 'Parcours', 'Finalité', ?, ?, ?)",
                      (uid(5, space), uid(2, space), uid(4, project), uid(1, 1), uid(1, 1), NOW))
            c.execute("INSERT INTO version_parcours (id, parcours_id, espace_id, numero, perspective, cree_par, cree_le) VALUES (?, ?, ?, 1, 'observee', ?, ?)",
                      (uid(6, space), uid(5, space), uid(2, space), uid(1, 1), NOW))
            c.execute("INSERT INTO canal (id, espace_id, nom, type_canal, cree_par, cree_le) VALUES (?, ?, 'Canal', 'autre', ?, ?)",
                      (uid(8, space), uid(2, space), uid(1, 1), NOW))
            c.execute("INSERT INTO point_contact (id, espace_id, projet_id, nom, intention, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, 'Contact', 'Intention', ?, ?, ?)",
                      (uid(9, space), uid(2, space), uid(4, project), uid(1, 1), uid(1, 1), NOW))
        for number, space in ((1, 1), (2, 1), (3, 1), (4, 2)):
            project = 1 if space == 1 else 4
            c.execute("INSERT INTO etape (id, version_parcours_id, espace_id, cle_stable, titre, objectif_public, ordre_affichage, cree_par, cree_le) VALUES (?, ?, ?, ?, 'Étape', 'Objectif', 0, ?, ?)",
                      (uid(7, number), uid(6, space), uid(2, space), uid(11, number), uid(1, 1), NOW))
            c.execute("INSERT INTO occurrence_contact (id, espace_id, etape_id, point_contact_id, canal_id, cle_stable, besoin_public, experience_attendue, criticite, frequence, etat_operationnel, ordre_affichage, cree_par, cree_le) VALUES (?, ?, ?, ?, ?, ?, 'Besoin', 'Expérience', 'mineure', 'continue', 'prevu', 0, ?, ?)",
                      (uid(10, number), uid(2, space), uid(7, number), uid(9, space), uid(8, space), uid(12, number), uid(1, 1), NOW))
            c.execute("INSERT INTO operation (id, espace_id, projet_pilote_id, nom, responsable_id, frequence, mode_execution, etat_operationnel, cree_par, cree_le) VALUES (?, ?, ?, ?, ?, 'continue', 'humain', 'prevu', ?, ?)",
                      (uid(13, number), uid(2, space), uid(4, project), f'Opération {number}', uid(1, 1), uid(1, 1), NOW))
            c.execute("INSERT INTO ressource (id, espace_id, projet_pilote_id, nom, type_ressource, etat, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, ?, 'logiciel', 'disponible', ?, ?, ?)",
                      (uid(14, number), uid(2, space), uid(4, project), f'Ressource {number}', uid(1, 1), uid(1, 1), NOW))
            c.execute("INSERT INTO constat (id, espace_id, occurrence_contact_id, auteur_id, type_constat, description, source, observe_le, niveau_confiance, cree_par, cree_le) VALUES (?, ?, ?, ?, 'hypothese', 'Constat', 'Source synthétique', ?, 'faible', ?, ?)",
                      (uid(15, number), uid(2, space), uid(10, number), uid(1, 1), NOW, uid(1, 1), NOW))
        for number, space, project in ((1, 1, 1), (2, 1, 2), (3, 2, 4)):
            c.execute("INSERT INTO action (id, espace_id, projet_pilote_id, titre, description, nature, responsable_id, critere_acceptation, cree_par, cree_le) VALUES (?, ?, ?, ?, 'Description', 'livrable', ?, 'Critère', ?, ?)",
                      (uid(16, number), uid(2, space), uid(4, project), f'Action {number}', uid(1, 1), uid(1, 1), NOW))
        c.commit()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def rows(self, table):
        return [tuple(row) for row in self.connection.execute(f'SELECT * FROM {table} ORDER BY 1, 2')]

    def test_shared_action_links_isolation_and_persistence(self):
        c = self.connection
        definitions = ('action', 'projet', 'occurrence_contact', 'operation', 'ressource', 'constat')
        cases = (
            ('action_projet', 'projet_id', 4, (60, 70, 'Accueil'), (40, 30, 'Suivi'), (55, 65, 'Orientation')),
            ('action_occurrence', 'occurrence_contact_id', 10, ('Attente réduite', 'non_valide'), ('Suivi fluide', 'valide'), ('Orientation rapide', 'partiel')),
            ('action_operation', 'operation_id', 13, ('modifier',), ('controler',), ('arreter',)),
            ('action_ressource', 'ressource_id', 14, ('creer',), ('modifier',), ('controler',)),
            ('action_constat', 'constat_id', 15, (), (), ()),
        )
        before = {table: self.rows(table) for table in definitions}
        expected = {case[0]: [] for case in cases}
        for table, target, kind, local1, local2, changed in cases:
            with self.subTest(table=table):
                placeholders = ', '.join('?' for _ in range(3 + len(local1)))
                insert = f'INSERT INTO {table} VALUES ({placeholders})'
                update = f'UPDATE {table} SET action_id = ?, {target} = ?, espace_id = ? WHERE action_id = ? AND {target} = ?'
                first = (uid(16, 1), uid(kind, 1), uid(2, 1), *local1)
                neighbor = (uid(16, 1), uid(kind, 2), uid(2, 1), *local2)
                moving = (uid(16, 2), uid(kind, 3), uid(2, 1), *local1)
                for row in (first, neighbor, moving):
                    self.assertEqual(c.execute(insert, row).rowcount, 1)
                expected[table] = [first, neighbor, moving]
                self.assertEqual(self.rows(table), expected[table])
                moved = (uid(16, 2), uid(kind, 2), uid(2, 1), *local1)
                self.assertEqual(c.execute(update, (*moved[:3], *moving[:2])).rowcount, 1)
                self.assertEqual(self.rows(table), [first, neighbor, moved])
                self.assertEqual(c.execute(update, (*moving[:3], *moved[:2])).rowcount, 1)
                self.assertEqual(self.rows(table), expected[table])
                if local1:
                    columns = {
                        'action_projet': ('part_charge', 'part_budget', 'motif_rattachement'),
                        'action_occurrence': ('effet_attendu', 'etat_validation_effet'),
                        'action_operation': ('nature_intervention',),
                        'action_ressource': ('nature_intervention',),
                    }[table]
                    assignments = ', '.join(f'{column} = ?' for column in columns)
                    self.assertEqual(c.execute(f'UPDATE {table} SET {assignments} WHERE action_id = ? AND {target} = ?',
                                               (*changed, *first[:2])).rowcount, 1)
                    first = (*first[:3], *changed)
                    expected[table] = [first, neighbor, moving]
                self.assertEqual(self.rows(table), expected[table])
                self.assertEqual({name: self.rows(name) for name in definitions}, before)

                def assert_snapshots():
                    self.assertEqual({name: self.rows(name) for name in expected}, expected)
                    self.assertEqual({name: self.rows(name) for name in definitions}, before)

                duplicate_message = f'UNIQUE constraint failed: {table}.action_id, {table}.{target}'
                for operation in ('insert', 'update'):
                    with self.subTest(refusal='duplicate', operation=operation):
                        with self.assertRaises(sqlite3.IntegrityError) as error:
                            if operation == 'insert':
                                c.execute(insert, first)
                            else:
                                c.execute(update, (*first[:3], *moving[:2]))
                        self.assertEqual(str(error.exception), duplicate_message)
                        assert_snapshots()
                for action, destination, space in ((3, 3, 1), (2, 4, 1), (2, 2, 2)):
                    invalid = (uid(16, action), uid(kind, destination), uid(2, space))
                    for operation in ('insert', 'update'):
                        with self.subTest(refusal='space', values=invalid, operation=operation):
                            with self.assertRaises(sqlite3.IntegrityError) as error:
                                if operation == 'insert':
                                    c.execute(insert, (*invalid, *local1))
                                else:
                                    c.execute(update, (*invalid, *moving[:2]))
                            self.assertEqual(str(error.exception), 'FOREIGN KEY constraint failed')
                            assert_snapshots()

        self.assertEqual(c.execute('SELECT count(*) FROM action WHERE id = ?', (uid(16, 1),)).fetchone()[0], 1)
        self.assertEqual(c.execute('SELECT count(*) FROM action_projet WHERE action_id = ?', (uid(16, 1),)).fetchone()[0], 2)
        c.commit()
        self.close()
        self.connection = db.connect(self.path)
        self.assertEqual(self.connection.execute('PRAGMA foreign_keys').fetchone()[0], 1)
        self.assertEqual({name: self.rows(name) for name in expected}, expected)
        self.assertEqual({name: self.rows(name) for name in definitions}, before)
        self.assertEqual(db.integrity_problems(self.connection), [])


if __name__ == '__main__':
    unittest.main()
