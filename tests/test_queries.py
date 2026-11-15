import tempfile
import unittest
from pathlib import Path

from journai import db, migrations, seed
from journai.auth import AuthContext
from journai.queries import CATALOG, QueryError, read

ROOT = Path(__file__).resolve().parents[1] / "journai"
SPACE = "a850d82b-814e-540f-bf03-ef86588e90b9"
ADMIN = "b5c7d06a-d5aa-5527-9739-4d9bce0be0ae"
CONTRIBUTOR = "7296f48c-4748-53f3-a73c-6847fa3c9ed8"
PROJECT_A = "d433b0ab-5208-520a-8068-b00950d5f467"
PROJECT_B = "028ef5b1-354b-5ca3-b352-b177b47a4852"
SHARED = "36462979-914f-5bee-893a-0984f319c5f2"
PRIVATE = "ef35cbd0-a577-5482-a098-6abdd628cb28"
COMMENT = "aaaaaaaa-0000-4000-8000-000000000001"


class QueryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.connection = db.connect(Path(temp.name) / "test.db")
        self.addCleanup(self.connection.close)
        migrations.migrate(self.connection, ROOT / "migrations")
        seed.seeded(self.connection, ROOT / "fixtures", env="test")
        self.admin = AuthContext(ADMIN, SPACE)
        self.contributor = AuthContext(CONTRIBUTOR, SPACE)
        self.connection.execute("INSERT INTO commentaire (id, espace_id, objet_id, auteur_id, contenu, cree_le) VALUES (?, ?, ?, ?, ?, ?)",
                                (COMMENT, SPACE, SHARED, ADMIN, "échange commun", "2026-01-01"))

    def query(self, name, params=None, *, identifiant=None, context=None):
        return read(self.connection, context or self.admin, name, params, identifiant=identifiant)

    def denied(self, status, name, params=None, **kwargs):
        with self.assertRaises(QueryError) as caught:
            self.query(name, params, **kwargs)
        self.assertEqual(caught.exception.status, status)

    def test_catalog_executes_and_only_authorized_tables(self):
        for name, spec in CATALOG.items():
            with self.subTest(name=name):
                result = self.query(name)
                self.assertEqual(result["meta"]["total"], len(result["data"]))
                for row in result["data"]:
                    self.assertEqual(set(row), set(spec.columns))
                    if "espace_id" in row:
                        self.assertEqual(row["espace_id"], SPACE)
        for name in ("schema_migration", "sqlite_master", "objet", "evenement", "notification", "abonnement", "projet;DROP TABLE projet"):
            self.denied(404, name)

    def test_projects_pagination_details_includes_and_membership_reload(self):
        result = self.query("projet")
        self.assertEqual(result["meta"]["total"], 1)
        self.assertEqual(result["data"][0]["id"], PROJECT_A)
        self.denied(403, "projet", identifiant=PROJECT_B)
        self.denied(403, "parcours", {"projet_id": PROJECT_B})
        included = self.query("projet", {"include": "parcours"}, identifiant=PROJECT_A)
        self.assertTrue(included["included"]["parcours"])
        self.assertTrue(all(row["projet_id"] == PROJECT_A for row in included["included"]["parcours"]))
        both = self.query("projet", {"limit": "1", "offset": "1", "ordre": "nom", "sens": "desc"}, context=self.contributor)
        self.assertEqual(both["meta"]["total"], 2)
        self.assertEqual(len(both["data"]), 1)
        full = self.query("projet", {"ordre": "nom", "sens": "desc"}, context=self.contributor)
        self.assertEqual(both["data"][0], full["data"][1])
        self.connection.execute("DELETE FROM membre_projet WHERE utilisateur_id=? AND projet_id=?", (ADMIN, PROJECT_A))
        self.assertEqual(self.query("projet")["meta"]["total"], 0)
        self.assertEqual(self.query("action")["meta"]["total"], 0)
        self.denied(403, "projet", identifiant=PROJECT_A)

    def test_shared_action_only_common_content_and_permitted_relations(self):
        self.connection.execute("DELETE FROM membre_projet WHERE utilisateur_id=? AND projet_id=?", (ADMIN, PROJECT_A))
        self.connection.execute("INSERT INTO membre_projet (projet_id, utilisateur_id, espace_id, role) VALUES (?, ?, ?, 'lecteur')", (PROJECT_B, ADMIN, SPACE))
        action = self.query("action", {"include": "commentaire"}, identifiant=SHARED)
        self.assertIsNone(action["data"]["projet_pilote_id"])
        self.assertIsNone(action["data"]["action_parent_id"])
        self.assertEqual([r["id"] for r in action["included"]["commentaire"]], [COMMENT])
        self.denied(404, "action", identifiant=PRIVATE)
        self.assertEqual(self.query("action", {"id": SHARED, "projet_pilote_id": PROJECT_A})["meta"]["total"], 0)
        included = self.query("action", {"include": "action_projet"}, identifiant=SHARED)
        links = included["included"]["action_projet"]
        self.assertEqual([r["projet_id"] for r in links], [PROJECT_B])
        self.assertEqual(included["included_meta"]["action_projet"], {
            "ressource": "action_projet", "total": 1, "limit": 500, "offset": 0, "espace_id": SPACE})
        for name in ("action_occurrence", "action_operation", "action_ressource", "action_constat", "contribution_action", "estimation_action"):
            self.assertEqual(self.query(name, {"action_id": SHARED})["meta"]["total"], 0, name)
        for relation in ("action_occurrence", "action_operation", "action_ressource", "action_constat"):
            included = self.query("action", {"include": relation}, identifiant=SHARED)
            self.assertEqual(included["included"][relation], [])
            self.assertEqual(included["included_meta"][relation], {
                "ressource": relation, "total": 0, "limit": 500, "offset": 0, "espace_id": SPACE})

    def test_pagination_total_is_scoped_before_limit(self):
        for index in range(55):
            identifier = f"99999999-0000-4000-8000-{index:012d}"
            self.connection.execute("""INSERT INTO projet
                (id, espace_id, structure_pilote_id, nom, finalite, responsable_id, cree_par, cree_le)
                SELECT ?, espace_id, structure_pilote_id, ?, finalite, responsable_id, cree_par, cree_le
                FROM projet WHERE id=?""", (identifier, f"Projet synthétique {index:03d}", PROJECT_A))
            if index < 52:
                self.connection.execute("INSERT INTO membre_projet (projet_id, utilisateur_id, espace_id, role) VALUES (?, ?, ?, 'lecteur')", (identifier, ADMIN, SPACE))
        first = self.query("projet", {"ordre": "nom"})
        self.assertEqual(first["meta"]["total"], 53)
        self.assertEqual(len(first["data"]), 50)
        last = self.query("projet", {"ordre": "nom", "offset": "50"})
        self.assertEqual(last["meta"]["total"], 53)
        self.assertEqual(len(last["data"]), 3)
        self.assertFalse({r["id"] for r in first["data"]} & {r["id"] for r in last["data"]})

    def test_included_pagination_preserves_scope_and_list_continuation(self):
        source = self.connection.execute("SELECT id FROM parcours WHERE projet_id=?", (PROJECT_A,)).fetchone()[0]
        foreign = self.connection.execute("SELECT id, projet_id FROM parcours WHERE espace_id<>?", (SPACE,)).fetchone()
        sql = """INSERT INTO parcours (id, espace_id, projet_id, nom, finalite, responsable_id, cree_par, cree_le)
                 SELECT ?, espace_id, projet_id, nom, finalite, responsable_id, cree_par, cree_le FROM parcours WHERE id=?"""
        self.connection.executemany(sql, ((f"99999999-0000-4000-8000-{i:012d}", source) for i in range(501)))
        self.connection.execute(sql, ("88888888-0000-4000-8000-000000000001", foreign[0]))
        result = self.query("projet", {"include": "parcours"}, identifiant=PROJECT_A)
        meta = result["included_meta"]["parcours"]
        self.assertEqual(meta, {"ressource": "parcours", "total": 502, "limit": 500, "offset": 0, "espace_id": SPACE})
        first = result["included"]["parcours"]
        self.assertEqual(len(first), 500)
        self.assertTrue(all(row["espace_id"] == SPACE and row["projet_id"] == PROJECT_A for row in first))
        rest = self.query("parcours", {"projet_id": PROJECT_A, "limit": str(meta["limit"]),
                                      "offset": str(meta["offset"] + meta["limit"])})
        self.assertEqual(rest["meta"]["total"], 502)
        self.assertEqual(len(rest["data"]), 2)
        self.assertTrue(all(row["espace_id"] == SPACE and row["projet_id"] == PROJECT_A for row in rest["data"]))
        self.assertFalse({row["id"] for row in first} & {row["id"] for row in rest["data"]})
        self.assertNotIn(foreign[0], {row["id"] for row in first + rest["data"]})

    def test_cross_project_association_requires_both_endpoints(self):
        other_operation = self.connection.execute("SELECT id FROM operation WHERE projet_pilote_id=?", (PROJECT_B,)).fetchone()[0]
        self.connection.execute("INSERT INTO action_operation (action_id, operation_id, espace_id, nature_intervention) VALUES (?, ?, ?, 'modifier')", (SHARED, other_operation, SPACE))
        links = self.query("action_operation", {"action_id": SHARED})["data"]
        self.assertNotIn(other_operation, [row["operation_id"] for row in links])
        included = self.query("action", {"include": "action_operation"}, identifiant=SHARED)["included"]["action_operation"]
        self.assertEqual(included, links)
        all_links = self.query("action_operation", {"action_id": SHARED}, context=self.contributor)["data"]
        self.assertIn(other_operation, [row["operation_id"] for row in all_links])

    def test_associations_and_cross_space(self):
        links = self.query("parcours_public")
        self.assertGreater(links["meta"]["total"], 0)
        row = links["data"][0]
        self.assertNotIn("id", row)
        self.assertNotIn("revision", row)
        self.assertEqual(self.query("parcours_public", {"parcours_id": row["parcours_id"]})["meta"]["total"], links["meta"]["total"])
        self.denied(404, "parcours_public", identifiant=row["parcours_id"])
        foreign = self.connection.execute("SELECT id, espace_id FROM projet WHERE espace_id <> ? LIMIT 1", (SPACE,)).fetchone()
        self.denied(404, "projet", identifiant=foreign[0])
        self.denied(403, "projet", {"espace_id": foreign[1]})
        self.assertEqual(self.query("projet", {"id": foreign[0]})["meta"]["total"], 0)
        foreign_user = self.connection.execute("SELECT utilisateur_id FROM membre_projet WHERE projet_id=?", (foreign[0],)).fetchone()[0]
        foreign_context = AuthContext(foreign_user, foreign[1])
        self.assertEqual([row["id"] for row in self.query("projet", context=foreign_context)["data"]], [foreign[0]])
        self.assertEqual(self.query("action", {"id": SHARED}, context=foreign_context)["meta"]["total"], 0)
        self.denied(404, "action", identifiant=SHARED, context=foreign_context)

    def test_invalid_inputs(self):
        for params in ({"limit": "0"}, {"limit": "501"}, {"limit": "-1"}, {"offset": "-1"},
                       {"offset": "99999999999999999999"}, {"limit": "1.0"}, {"sens": "ASC"},
                       {"ordre": "id; DROP TABLE action"}, {"unknown": "x"}, {"id OR 1=1": "x"},
                       {"limit": 1}, {"include": "action_projet"}):
            with self.subTest(params=params):
                self.denied(400, "action", params)
        self.denied(400, "action", {"include": "evenement"}, identifiant=SHARED)
        self.assertEqual(self.query("action", {"titre": "x' OR 1=1 --"})["meta"]["total"], 0)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM action").fetchone()[0], 4)

    def test_identity_rechecked_and_space_bound(self):
        self.connection.execute("UPDATE membre_espace SET statut='inactif' WHERE utilisateur_id=? AND espace_id=?", (ADMIN, SPACE))
        self.denied(403, "projet")
        self.connection.execute("UPDATE membre_espace SET statut='actif' WHERE utilisateur_id=? AND espace_id=?", (ADMIN, SPACE))
        self.connection.execute("UPDATE utilisateur SET statut='suspendu' WHERE id=?", (ADMIN,))
        self.denied(401, "projet")


if __name__ == "__main__":
    unittest.main()
