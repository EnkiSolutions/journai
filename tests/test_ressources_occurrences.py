import sqlite3
import tempfile
import unittest
from pathlib import Path

from journai import db, migrations


SCHEMA = Path(__file__).resolve().parents[1] / 'journai' / 'migrations'
NOW = '2026-01-01T00:00:00.000000+00:00'


def uid(kind, number):
    return f'{kind:08d}-0000-4000-8000-{number:012d}'


class RessourcesOccurrencesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'data.db'
        self.connection = db.connect(self.path)
        self.addCleanup(self.close)
        self.assertEqual(migrations.migrate(self.connection, SCHEMA),
                         [f'{n:04}' for n in range(1, 12)])
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
            c.execute("INSERT INTO ressource (id, espace_id, projet_pilote_id, nom, type_ressource, etat, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, ?, 'logiciel', 'disponible', ?, ?, ?)",
                      (uid(13, number), uid(2, space), uid(4, space), f'Ressource {number}', uid(1, 1), uid(1, 1), NOW))
        c.commit()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def rows(self, table, order):
        return [dict(row) for row in self.connection.execute(f'SELECT * FROM {table} ORDER BY {order}')]

    def link(self, occurrence, resource, space=1, usage='Accueil', role='necessaire', state='utilise'):
        return (uid(10, occurrence), uid(13, resource), uid(2, space), usage, role, state)

    def test_reuse_isolation_independence_and_persistence(self):
        c = self.connection
        insert = 'INSERT INTO occurrence_ressource VALUES (?, ?, ?, ?, ?, ?)'
        update = ('UPDATE occurrence_ressource SET occurrence_contact_id = ?, ressource_id = ?, '
                  'espace_id = ?, usage = ?, role_occurrence = ?, etat_utilisation = ? '
                  'WHERE occurrence_contact_id = ? AND ressource_id = ?')
        resources = self.rows('ressource', 'id')
        occurrences = self.rows('occurrence_contact', 'id')
        initial = (self.link(1, 1), self.link(2, 1, usage='Information', role='prevue', state='reserve'),
                   self.link(1, 2, usage='Suivi', role='suffisante', state='non_utilise'),
                   self.link(3, 3, usage='Contrôle', role='bloquante', state='hors_service'))
        for values in initial:
            c.execute(insert, values)
        self.assertEqual(c.execute('SELECT count(*) FROM ressource WHERE id = ?', (uid(13, 1),)).fetchone()[0], 1)
        moved = self.link(3, 2, usage='Alternative', role='insuffisante', state='consomme')
        self.assertEqual(c.execute(update, (*moved, uid(10, 3), uid(13, 3))).rowcount, 1)
        self.assertEqual(tuple(c.execute('SELECT * FROM occurrence_ressource WHERE occurrence_contact_id = ? AND ressource_id = ?', (uid(10, 3), uid(13, 2))).fetchone()), moved)
        self.assertEqual(c.execute(update, (*initial[3], uid(10, 3), uid(13, 2))).rowcount, 1)
        expected = [initial[0], initial[2], initial[1], initial[3]]
        self.assertEqual([tuple(row.values()) for row in self.rows('occurrence_ressource', 'occurrence_contact_id, ressource_id')], expected)
        self.assertEqual(self.rows('ressource', 'id'), resources)
        self.assertEqual(self.rows('occurrence_contact', 'id'), occurrences)

        changed = self.link(1, 1, usage='Orientation', role='prevue', state='reserve')
        self.assertEqual(c.execute(update, (*changed, uid(10, 1), uid(13, 1))).rowcount, 1)
        expected[0] = changed
        self.assertEqual([tuple(row.values()) for row in self.rows('occurrence_ressource', 'occurrence_contact_id, ressource_id')], expected)
        self.assertEqual(self.rows('ressource', 'id'), resources)
        self.assertEqual(self.rows('occurrence_contact', 'id'), occurrences)
        self.assertEqual(c.execute("UPDATE ressource SET etat = 'maintenance' WHERE id = ?", (uid(13, 1),)).rowcount, 1)
        resources[0]['etat'] = 'maintenance'
        self.assertEqual(self.rows('ressource', 'id'), resources)
        self.assertEqual(self.rows('occurrence_contact', 'id'), occurrences)
        self.assertEqual([tuple(row.values()) for row in self.rows('occurrence_ressource', 'occurrence_contact_id, ressource_id')], expected)

        with self.assertRaisesRegex(sqlite3.IntegrityError, 'UNIQUE constraint failed: occurrence_ressource.occurrence_contact_id, occurrence_ressource.ressource_id'):
            c.execute(insert, changed)
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'UNIQUE constraint failed: occurrence_ressource.occurrence_contact_id, occurrence_ressource.ressource_id'):
            c.execute(update, (*changed, uid(10, 3), uid(13, 3)))
        self.assertEqual([tuple(row.values()) for row in self.rows('occurrence_ressource', 'occurrence_contact_id, ressource_id')], expected)
        self.assertEqual(self.rows('ressource', 'id'), resources)
        self.assertEqual(self.rows('occurrence_contact', 'id'), occurrences)

        for values in (self.link(4, 2), self.link(2, 4), self.link(2, 2, space=2)):
            with self.subTest(invalid_space=values):
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
                    c.execute(insert, values)
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
                    c.execute(update, (*values, uid(10, 3), uid(13, 3)))
                self.assertEqual([tuple(row.values()) for row in self.rows('occurrence_ressource', 'occurrence_contact_id, ressource_id')], expected)
                self.assertEqual(self.rows('ressource', 'id'), resources)
                self.assertEqual(self.rows('occurrence_contact', 'id'), occurrences)
        c.commit()
        self.close()
        self.connection = db.connect(self.path)
        self.assertEqual([tuple(row.values()) for row in self.rows('occurrence_ressource', 'occurrence_contact_id, ressource_id')], expected)
        self.assertEqual(self.rows('ressource', 'id'), resources)
        self.assertEqual(self.rows('occurrence_contact', 'id'), occurrences)
        self.assertEqual(db.integrity_problems(self.connection), [])

    def test_utilisation_states_on_insert_update_and_reopen(self):
        c = self.connection
        insert = 'INSERT INTO occurrence_ressource VALUES (?, ?, ?, ?, ?, ?)'
        update = ('UPDATE occurrence_ressource SET etat_utilisation = ? '
                  'WHERE occurrence_contact_id = ? AND ressource_id = ?')
        states = ('utilise', 'reserve', 'consomme', 'hors_service', 'non_utilise')
        pairs = ((1, 1), (1, 2), (1, 3), (2, 1), (2, 2))
        select = ('SELECT * FROM occurrence_ressource '
                  'WHERE occurrence_contact_id = ? AND ressource_id = ?')
        for (occurrence, resource), state in zip(pairs, states):
            with self.subTest(insert=state):
                values = self.link(occurrence, resource, state=state)
                self.assertEqual(c.execute(insert, values).rowcount, 1)
                self.assertEqual(tuple(c.execute(select, values[:2]).fetchone()), values)

        for (occurrence, resource), state in zip(pairs, states[1:] + states[:1]):
            with self.subTest(update=state):
                values = self.link(occurrence, resource, state=state)
                self.assertEqual(c.execute(update, (state, *values[:2])).rowcount, 1)
                self.assertEqual(tuple(c.execute(select, values[:2]).fetchone()), values)

        associations = self.rows('occurrence_ressource', 'occurrence_contact_id, ressource_id')
        resources = self.rows('ressource', 'id')
        occurrences = self.rows('occurrence_contact', 'id')

        def assert_snapshots():
            self.assertEqual(self.rows('occurrence_ressource', 'occurrence_contact_id, ressource_id'), associations)
            self.assertEqual(self.rows('ressource', 'id'), resources)
            self.assertEqual(self.rows('occurrence_contact', 'id'), occurrences)

        invalid_states = (None, 'inconnu', 'dégradé', 'indisponible',
                          'remplace', 'libere', 'bloque', 'inchange')
        for state in invalid_states:
            message = ('NOT NULL constraint failed: occurrence_ressource.etat_utilisation'
                       if state is None else
                       "CHECK constraint failed: etat_utilisation IN ('utilise', 'reserve', 'consomme', 'hors_service', 'non_utilise')")
            for operation in ('insert', 'update'):
                with self.subTest(invalid=state, operation=operation):
                    with self.assertRaises(sqlite3.IntegrityError) as error:
                        if operation == 'insert':
                            c.execute(insert, self.link(3, 3, state=state))
                        else:
                            c.execute(update, (state, uid(10, 1), uid(13, 1)))
                    self.assertEqual(str(error.exception), message)
                    assert_snapshots()

        c.commit()
        self.close()
        self.connection = db.connect(self.path)
        assert_snapshots()
        self.assertEqual(db.integrity_problems(self.connection), [])


if __name__ == '__main__':
    unittest.main()
