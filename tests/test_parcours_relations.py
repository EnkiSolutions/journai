import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from journai import db, migrations


SCHEMA = Path(__file__).resolve().parents[1] / "journai" / "migrations"
VERSIONS_5 = [f"{number:04}" for number in range(1, 6)]
NOW = "2026-01-01T00:00:00.000000+00:00"
USER = "00000000-0000-4000-8000-000000000001"
SPACE = [f"10000000-0000-4000-8000-{n:012d}" for n in (1, 2)]
STRUCTURE = [f"20000000-0000-4000-8000-{n:012d}" for n in (1, 2)]
PROJECT = [f"30000000-0000-4000-8000-{n:012d}" for n in (1, 2)]
PATH = [f"40000000-0000-4000-8000-{n:012d}" for n in (1, 2, 3, 4)]
VERSION = [f"50000000-0000-4000-8000-{n:012d}" for n in range(1, 8)]


class ParcoursRelationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.path = root / "data.db"
        self.old_schema = root / "old_schema"
        self.old_schema.mkdir()
        for file in SCHEMA.glob("000[1-5]_*.sql"):
            shutil.copyfile(file, self.old_schema / file.name)
        self.schema_6 = root / "schema_6"
        shutil.copytree(self.old_schema, self.schema_6)
        for file in SCHEMA.glob("0006_*.sql"):
            shutil.copyfile(file, self.schema_6 / file.name)
        self.connection = db.connect(self.path)
        self.addCleanup(self.close)
        self.assertEqual(migrations.migrate(self.connection, self.old_schema), VERSIONS_5)
        c = self.connection
        c.execute("INSERT INTO utilisateur (id, nom_affiche, email, cree_le) VALUES (?, 'Test', 'test@example.invalid', ?)", (USER, NOW))
        for i in range(2):
            c.execute("INSERT INTO espace (id, nom, cree_par, cree_le) VALUES (?, ?, ?, ?)", (SPACE[i], f'Espace {i}', USER, NOW))
            c.execute("INSERT INTO structure (id, espace_id, nom, type_structure, cree_par, cree_le) VALUES (?, ?, 'Structure', 'autre', ?, ?)", (STRUCTURE[i], SPACE[i], USER, NOW))
            c.execute("INSERT INTO projet (id, espace_id, structure_pilote_id, nom, finalite, responsable_id, cree_par, cree_le) VALUES (?, ?, ?, 'Projet', 'Finalité', ?, ?, ?)", (PROJECT[i], SPACE[i], STRUCTURE[i], USER, USER, NOW))
        for index, space in ((0, 0), (1, 0), (2, 1)):
            self.insert_path(PATH[index], space)
        for vid, path, space, perspective, number in (
            (VERSION[0], PATH[0], 0, 'observee', 1),
            (VERSION[1], PATH[0], 0, 'cible', 1),
            (VERSION[2], PATH[0], 0, 'observee', 2),
            (VERSION[3], PATH[1], 0, 'observee', 1),
            (VERSION[4], PATH[2], 1, 'observee', 1),
        ):
            self.insert_version(vid, path, space, perspective, number)
        c.commit()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def reopen(self):
        self.close()
        self.connection = db.connect(self.path)

    def insert_path(self, path, space, observed=None, target=None):
        self.connection.execute(
            "INSERT INTO parcours (id, espace_id, projet_id, nom, finalite, responsable_id, cree_par, cree_le, version_observee_id, version_cible_id) VALUES (?, ?, ?, 'Parcours', 'Finalité', ?, ?, ?, ?, ?)",
            (path, SPACE[space], PROJECT[space], USER, USER, NOW, observed, target),
        )

    def insert_version(self, vid, path, space, perspective, number, source=None):
        self.connection.execute(
            "INSERT INTO version_parcours (id, parcours_id, espace_id, numero, perspective, version_source_id, cree_par, cree_le) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (vid, path, SPACE[space], number, perspective, source, USER, NOW),
        )

    def references(self):
        return [tuple(row) for row in self.connection.execute(
            "SELECT id, version_observee_id, version_cible_id FROM parcours ORDER BY id")]

    def test_upgrade_preserves_data_and_is_idempotent(self):
        self.connection.execute("UPDATE parcours SET version_observee_id = ?, version_cible_id = ? WHERE id = ?", (VERSION[0], VERSION[1], PATH[0]))
        self.connection.commit()
        before = self.references()
        data_before = [tuple(row) for table in ('parcours', 'version_parcours')
                       for row in self.connection.execute(f"SELECT * FROM {table} ORDER BY id")]
        self.assertEqual(migrations.migrate(self.connection, self.schema_6), ['0006'])
        self.reopen()
        self.assertEqual(self.references(), before)
        self.assertEqual(data_before, [tuple(row) for table in ('parcours', 'version_parcours')
                                       for row in self.connection.execute(f"SELECT * FROM {table} ORDER BY id")])
        self.assertEqual(migrations.applied_versions(self.connection), VERSIONS_5 + ['0006'])
        self.assertEqual(migrations.migrate(self.connection, self.schema_6), [])
        self.reopen()
        self.assertEqual(self.references(), before)
        self.assertEqual(migrations.applied_versions(self.connection), VERSIONS_5 + ['0006'])
        self.assertEqual(migrations.migrate(self.connection, SCHEMA), ['0007', '0008', '0009', '0010'])
        self.assertEqual(migrations.migrate(self.connection, SCHEMA), [])

    def test_inconsistent_upgrade_rolls_back(self):
        for column, wrong in (('version_observee_id', VERSION[1]), ('version_cible_id', VERSION[0])):
            with self.subTest(column=column):
                self.connection.execute(f"UPDATE parcours SET {column} = ? WHERE id = ?", (wrong, PATH[0]))
                self.connection.commit()
                before = list(self.connection.iterdump())
                with self.assertRaisesRegex(migrations.MigrationError, 'perspectives_courantes_incoherentes'):
                    migrations.migrate(self.connection, SCHEMA)
                self.reopen()
                self.assertEqual(list(self.connection.iterdump()), before)
                self.assertEqual(migrations.applied_versions(self.connection), VERSIONS_5)
                self.assertNotIn('controle_versions_courantes', db.table_names(self.connection))
                self.connection.execute(f"UPDATE parcours SET {column} = NULL WHERE id = ?", (PATH[0],))
                self.connection.commit()

    def test_reference_updates_and_source_constraints(self):
        migrations.migrate(self.connection, SCHEMA)
        c = self.connection
        c.execute("UPDATE parcours SET version_observee_id = ?, version_cible_id = ? WHERE id = ?", (VERSION[0], VERSION[1], PATH[0]))
        for column, value in (('version_observee_id', VERSION[1]), ('version_cible_id', VERSION[0]),
                              ('version_observee_id', VERSION[3]), ('version_observee_id', VERSION[4])):
            with self.subTest(column=column, value=value), self.assertRaises(sqlite3.IntegrityError):
                c.execute(f"UPDATE parcours SET {column} = ? WHERE id = ?", (value, PATH[0]))
        for vid, perspective in ((VERSION[0], 'cible'), (VERSION[1], 'observee')):
            with self.subTest(version=vid), self.assertRaisesRegex(sqlite3.IntegrityError, 'perspective'):
                c.execute("UPDATE version_parcours SET perspective = ? WHERE id = ?", (perspective, vid))
        c.execute("UPDATE version_parcours SET perspective = 'cible' WHERE id = ?", (VERSION[2],))
        for source in (VERSION[3], VERSION[4]):
            with self.subTest(source=source), self.assertRaises(sqlite3.IntegrityError):
                self.insert_version(VERSION[5], PATH[0], 0, 'observee', 3, source)
        c.execute("UPDATE parcours SET version_observee_id = NULL, version_cible_id = NULL WHERE id = ?", (PATH[0],))
        c.commit()
        self.reopen()
        self.assertEqual(tuple(self.connection.execute("SELECT version_observee_id, version_cible_id FROM parcours WHERE id = ?", (PATH[0],)).fetchone()), (None, None))
        self.assertEqual(self.connection.execute("SELECT perspective FROM version_parcours WHERE id = ?", (VERSION[2],)).fetchone()[0], 'cible')

    def test_inserts_with_deferred_foreign_keys(self):
        migrations.migrate(self.connection, SCHEMA)
        c = self.connection
        for observed, target in ((VERSION[1], None), (None, VERSION[0])):
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'perspective'):
                self.insert_path(PATH[3], 0, observed=observed, target=target)
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_path(PATH[3], 0, observed=VERSION[3])
        c.execute("PRAGMA defer_foreign_keys = ON")
        self.insert_path(PATH[3], 0, observed=VERSION[5], target=VERSION[6])
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'perspective'):
            self.insert_version(VERSION[5], PATH[3], 0, 'cible', 1)
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'perspective'):
            self.insert_version(VERSION[6], PATH[3], 0, 'observee', 1)
        self.insert_version(VERSION[5], PATH[3], 0, 'observee', 1)
        self.insert_version(VERSION[6], PATH[3], 0, 'cible', 1)
        c.commit()
        self.reopen()
        self.assertEqual(tuple(self.connection.execute("SELECT version_observee_id, version_cible_id FROM parcours WHERE id = ?", (PATH[3],)).fetchone()), (VERSION[5], VERSION[6]))


if __name__ == '__main__':
    unittest.main()
