import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from journai import db, migrations


SCHEMA = Path(__file__).resolve().parents[1] / 'journai' / 'migrations'
NOW = '2026-01-01T00:00:00.000000+00:00'


def uid(kind, number):
    return f'{kind:08d}-0000-4000-8000-{number:012d}'


class ConstatsOccurrencesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'data.db'
        self.connection = db.connect(self.path)
        self.addCleanup(self.close)
        self.assertEqual(migrations.migrate(self.connection, SCHEMA),
                         [f'{n:04}' for n in range(1, 8)])
        c = self.connection
        for number in (1, 2):
            c.execute('INSERT INTO utilisateur (id, nom_affiche, email, cree_le) VALUES (?, ?, ?, ?)',
                      (uid(1, number), f'Auteur {number}', f'test{number}@example.invalid', NOW))
            c.execute('INSERT INTO espace (id, nom, cree_par, cree_le) VALUES (?, ?, ?, ?)',
                      (uid(2, number), f'Espace {number}', uid(1, 1), NOW))
            c.execute("INSERT INTO structure (id, espace_id, nom, type_structure, cree_par, cree_le) VALUES (?, ?, 'Structure', 'autre', ?, ?)",
                      (uid(3, number), uid(2, number), uid(1, 1), NOW))
            c.execute("INSERT INTO projet (id, espace_id, structure_pilote_id, nom, finalite, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, 'Projet', 'Finalité', ?, ?, ?)",
                      (uid(4, number), uid(2, number), uid(3, number), uid(1, 1), uid(1, 1), NOW))
            c.execute("INSERT INTO parcours (id, espace_id, projet_id, nom, finalite, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, 'Parcours', 'Finalité', ?, ?, ?)",
                      (uid(5, number), uid(2, number), uid(4, number), uid(1, 1), uid(1, 1), NOW))
            c.execute("INSERT INTO version_parcours (id, parcours_id, espace_id, numero, perspective, cree_par, cree_le) VALUES (?, ?, ?, 1, 'observee', ?, ?)",
                      (uid(6, number), uid(5, number), uid(2, number), uid(1, 1), NOW))
            c.execute("INSERT INTO canal (id, espace_id, nom, type_canal, cree_par, cree_le) VALUES (?, ?, 'Canal', 'autre', ?, ?)",
                      (uid(8, number), uid(2, number), uid(1, 1), NOW))
            c.execute("INSERT INTO point_contact (id, espace_id, projet_id, nom, intention, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, 'Contact', 'Intention', ?, ?, ?)",
                      (uid(9, number), uid(2, number), uid(4, number), uid(1, 1), uid(1, 1), NOW))
        for number, space in ((1, 1), (2, 1), (3, 2)):
            c.execute("INSERT INTO etape (id, version_parcours_id, espace_id, cle_stable, titre, objectif_public, ordre_affichage, cree_par, cree_le) VALUES (?, ?, ?, ?, 'Étape', 'Objectif', 0, ?, ?)",
                      (uid(7, number), uid(6, space), uid(2, space), uid(11, number), uid(1, 1), NOW))
            c.execute("INSERT INTO occurrence_contact (id, espace_id, etape_id, point_contact_id, canal_id, cle_stable, besoin_public, experience_attendue, criticite, frequence, etat_operationnel, ordre_affichage, cree_par, cree_le) VALUES (?, ?, ?, ?, ?, ?, 'Besoin', 'Expérience', 'mineure', 'continue', 'prevu', 0, ?, ?)",
                      (uid(10, number), uid(2, space), uid(7, number), uid(9, space), uid(8, space), uid(12, number), uid(1, 1), NOW))
        c.commit()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def rows(self, table):
        return [dict(row) for row in self.connection.execute(f'SELECT * FROM {table} ORDER BY id')]

    def test_proof_fields_relations_and_persistence(self):
        c = self.connection
        occurrences = self.rows('occurrence_contact')
        expected = []

        def snapshot():
            self.assertEqual(self.rows('constat'), expected)
            self.assertEqual(self.rows('occurrence_contact'), occurrences)

        def insert(values):
            columns = ', '.join(values)
            placeholders = ', '.join('?' for _ in values)
            return c.execute(f'INSERT INTO constat ({columns}) VALUES ({placeholders})', tuple(values.values()))

        records = [
            dict(id=uid(13, 1), espace_id=uid(2, 1), occurrence_contact_id=uid(10, 1),
                 auteur_id=uid(1, 1), type_constat='hypothese', description='Attente supposée',
                 source='Entretien synthétique', observe_le=NOW, niveau_confiance='faible',
                 cree_par=uid(1, 1), cree_le=NOW),
            dict(id=uid(13, 2), espace_id=uid(2, 1), occurrence_contact_id=uid(10, 1),
                 auteur_id=uid(1, 2), type_constat='fait_valide', description='Délai observé',
                 source='Mesure synthétique', observe_le='2026-01-02T09:30:00+00:00',
                 niveau_confiance='moyenne', statut_validation='valide', cree_par=uid(1, 2), cree_le=NOW),
            dict(id=uid(13, 3), espace_id=uid(2, 1), occurrence_contact_id=uid(10, 1),
                 auteur_id=uid(1, 1), type_constat='hypothese', description='Piste écartée',
                 source='Note synthétique', observe_le='2026-01-03T12:00:00+00:00',
                 niveau_confiance='forte', statut_validation='rejete', cree_par=uid(1, 1), cree_le=NOW),
        ]
        for record in records:
            self.assertEqual(insert(record).rowcount, 1)
            expected.append({**record, 'statut_validation': record.get('statut_validation', 'a_valider'),
                             'revision': 1, 'modifie_par': None, 'modifie_le': None, 'archive_le': None})
            snapshot()

        self.assertEqual(c.execute(
            'UPDATE constat SET occurrence_contact_id = ?, auteur_id = ?, description = ?, source = ?, '
            'observe_le = ?, niveau_confiance = ? WHERE id = ?',
            (uid(10, 2), uid(1, 2), 'Description révisée', 'Source révisée',
             '2026-01-04T10:00:00+00:00', 'forte', uid(13, 3))).rowcount, 1)
        expected[2].update(occurrence_contact_id=uid(10, 2), auteur_id=uid(1, 2),
                           description='Description révisée', source='Source révisée',
                           observe_le='2026-01-04T10:00:00+00:00', niveau_confiance='forte')
        snapshot()
