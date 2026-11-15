import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from journai import db, migrations


SCHEMA = Path(__file__).resolve().parents[1] / 'journai' / 'migrations'
NOW = '2026-01-01T00:00:00+00:00'


class CommentairesEspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.path = root / 'data.db'
        self.old_schema = root / 'schema_7'
        self.old_schema.mkdir()
        for file in SCHEMA.glob('000[1-7]_*.sql'):
            shutil.copyfile(file, self.old_schema / file.name)
        self.connection = db.connect(self.path)
        self.addCleanup(lambda: self.connection.close())
        migrations.migrate(self.connection, self.old_schema)
        c = self.connection
        c.execute("INSERT INTO utilisateur (id, nom_affiche, email, cree_le) VALUES ('u', 'U', 'u@example.invalid', ?)", (NOW,))
        for space in ('a', 'b'):
            c.execute('INSERT INTO espace (id, nom, cree_par, cree_le) VALUES (?, ?, ?, ?)', (space, space, 'u', NOW))
            c.execute("INSERT INTO objet (id, espace_id, type_objet, cree_par, cree_le) VALUES (?, ?, 'action', 'u', ?)",
                      ('o' + space, space, NOW))
        c.execute('CREATE TABLE reference_commentaire (id TEXT REFERENCES commentaire(id))')
        c.commit()

    def insert(self, ident, space, parent=None):
        self.connection.execute(
            "INSERT INTO commentaire (id, espace_id, objet_id, auteur_id, commentaire_parent_id, contenu, cree_le) "
            "VALUES (?, ?, ?, 'u', ?, 'contenu', ?)", (ident, space, 'o' + space, parent, NOW))

    def test_upgrade_and_invariant(self):
        self.insert('parent', 'a')
        self.insert('enfant', 'a', 'parent')
        self.insert('autre', 'b')
        self.connection.execute("INSERT INTO reference_commentaire VALUES ('enfant')")
        self.connection.commit()
        before = [tuple(row) for row in self.connection.execute('SELECT * FROM commentaire ORDER BY id')]
        self.assertEqual(migrations.migrate(self.connection, SCHEMA), ['0008'])
        self.connection.close()
        self.connection = db.connect(self.path)
        self.assertEqual([tuple(row) for row in self.connection.execute('SELECT * FROM commentaire ORDER BY id')], before)
        self.assertEqual(self.connection.execute('SELECT id FROM reference_commentaire').fetchone()[0], 'enfant')
        self.assertEqual(migrations.migrate(self.connection, SCHEMA), [])
        self.assertEqual(db.integrity_problems(self.connection), [])
        self.insert('sans_parent', 'b')
        self.insert('valide', 'a', 'parent')
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert('orphelin', 'a', 'absent')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'espaces differents'):
            self.insert('invalide', 'b', 'parent')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'espaces differents'):
            self.connection.execute("UPDATE commentaire SET commentaire_parent_id='autre' WHERE id='enfant'")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'espaces differents'):
            self.connection.execute("UPDATE commentaire SET espace_id='b', objet_id='ob' WHERE id='enfant'")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'espaces differents'):
            self.connection.execute("UPDATE commentaire SET espace_id='b', objet_id='ob' WHERE id='parent'")
        self.assertEqual(self.connection.execute('PRAGMA foreign_keys').fetchone()[0], 1)

    def test_deferred_parent_insert_and_id_change_are_checked(self):
        migrations.migrate(self.connection, SCHEMA)
        c = self.connection
        c.execute('PRAGMA defer_foreign_keys = ON')
        self.insert('enfant', 'a', 'futur')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'espaces differents'):
            self.insert('futur', 'b')
        self.insert('parent', 'b')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'espaces differents'):
            c.execute("UPDATE commentaire SET id='futur' WHERE id='parent'")
        c.rollback()

    def test_invalid_existing_relation_rolls_back_without_loss(self):
        self.insert('parent', 'a')
        self.insert('enfant', 'b', 'parent')
        self.connection.execute("INSERT INTO reference_commentaire VALUES ('enfant')")
        self.connection.commit()
        before = list(self.connection.iterdump())
        with self.assertRaisesRegex(migrations.MigrationError, 'commentaires_espaces_incoherents'):
            migrations.migrate(self.connection, SCHEMA)
        self.connection.close()
        self.connection = db.connect(self.path)
        self.assertEqual(list(self.connection.iterdump()), before)
        self.assertEqual(migrations.applied_versions(self.connection), [f'{n:04}' for n in range(1, 8)])
        self.assertEqual(self.connection.execute('PRAGMA foreign_keys').fetchone()[0], 1)
        self.assertEqual(db.integrity_problems(self.connection), [])


if __name__ == '__main__':
    unittest.main()
