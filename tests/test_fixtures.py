import json
import shutil
import tempfile
import unittest
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from journai import db, migrations, seed


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "journai" / "fixtures"
SCHEMA = ROOT / "journai" / "migrations"
COUNTS_A = {
    "utilisateur": 2, "espace": 1, "membre_espace": 2, "structure": 2,
    "projet": 2, "projet_structure": 3, "membre_projet": 3, "public": 3,
    "canal": 2, "point_contact": 1, "parcours": 1, "parcours_public": 2,
    "version_parcours": 3, "etape": 6, "transition_etape": 3,
    "occurrence_contact": 5, "operation": 2, "ressource": 2,
    "occurrence_operation": 2, "occurrence_ressource": 2, "constat": 2,
    "action": 3, "action_projet": 3, "action_occurrence": 2,
    "action_operation": 1, "action_ressource": 1, "action_constat": 1,
    "dependance_action": 1, "contribution_action": 2, "estimation_action": 2,
    "evaluation_action": 3, "decision_priorite": 3, "objet": 10,
    "commentaire": 2, "abonnement": 2, "evenement": 3, "notification": 2,
    "indicateur": 2, "mesure_indicateur": 2,
}
COUNTS_B = dict.fromkeys((
    "utilisateur", "espace", "membre_espace", "structure", "projet",
    "projet_structure", "membre_projet", "public", "canal", "point_contact",
    "parcours", "parcours_public", "version_parcours", "etape",
    "occurrence_contact", "operation", "ressource", "occurrence_operation",
    "action", "action_projet",
), 1)
INSTANTS = {"cree_le", "modifie_le", "archive_le", "valide_le", "decide_le",
            "resolu_le", "lu_le", "horodatage"}


def fixture(name):
    return json.loads((FIXTURES / f"espace-{name}.json").read_text(encoding="utf-8"))


def identifier(name):
    return str(uuid5(NAMESPACE_URL, f"journai-fixture/id/{name}"))


class FixtureTests(unittest.TestCase):
    def test_canonical_values_and_independent_datasets(self):
        identities = []
        for name in ("a", "b"):
            data = fixture(name)
            rows = [(entry["table"], row) for entry in data["tables"] for row in entry["rows"]]
            ids = {row["id"] for _, row in rows if "id" in row}
            stable = {row["cle_stable"] for _, row in rows if "cle_stable" in row}
            references = set()
            for table, row in rows:
                for key, value in row.items():
                    if value is None:
                        continue
                    if key == "id" or key == "cle_stable" or key.endswith(("_id", "_par")):
                        self.assertEqual(str(UUID(value)), value, (name, table, key))
                        if key.endswith(("_id", "_par")):
                            references.add(value)
                    elif key in INSTANTS:
                        parsed = datetime.fromisoformat(value)
                        self.assertEqual(parsed.utcoffset(), timezone.utc.utcoffset(parsed))
                        self.assertEqual(parsed.isoformat(timespec="microseconds"), value)
                        self.assertTrue(value.endswith("+00:00"))
                    elif key in {"observe_le", "periode_debut", "periode_fin"}:
                        self.assertEqual(date.fromisoformat(value).isoformat(), value)
                    elif key == "email":
                        self.assertTrue(value.endswith(".test"), value)
                if table == "objet":
                    self.assertTrue(any(t == row["type_objet"] and r.get("id") == row["id"]
                                        for t, r in rows))
            for update in data["updates"]:
                for value in (update["id"], *update["set"].values()):
                    self.assertEqual(str(UUID(value)), value)
                    references.add(value)
            self.assertLessEqual(references, ids)
            identities.append(ids | stable)
        self.assertTrue(identities[0].isdisjoint(identities[1]))

    def test_real_seed_is_committed_complete_and_reopenable(self):
        self.assertEqual(sum(COUNTS_A.values()) + sum(COUNTS_B.values()), 116)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for names, expected in (("a", Counter(COUNTS_A)), ("b", Counter(COUNTS_B)),
                                    ("ab", Counter(COUNTS_A) + Counter(COUNTS_B))):
                with self.subTest(fixtures=names):
                    location = root / names
                    location.mkdir()
                    fixture_dir = location / "fixtures"
                    fixture_dir.mkdir()
                    for name in names:
                        shutil.copy2(FIXTURES / f"espace-{name}.json", fixture_dir)
                    database = location / "data.db"
                    connection = db.connect(database)
                    try:
                        migrations.migrate(connection, SCHEMA)
                        self.assertEqual(seed.seeded(connection, fixture_dir, env="test"), dict(expected))
                        self.assertEqual(db.integrity_problems(connection), [])
                        self.assertEqual(
                            {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                             for table in COUNTS_A},
                            {table: expected[table] for table in COUNTS_A},
                        )
                        for name in names:
                            for entry in fixture(name)["tables"]:
                                table = entry["table"]
                                for row in entry["rows"]:
                                    where = " AND ".join(f"{key} IS ?" for key in row)
                                    count = connection.execute(
                                        f"SELECT COUNT(*) FROM {table} WHERE {where}", tuple(row.values())
                                    ).fetchone()[0]
                                    self.assertEqual(count, 1, (name, table, row))
                        self.assert_scenario_links(connection, names)
                        snapshot = list(connection.iterdump())
                        # A second connection sees the result without any test-side commit.
                        other = db.connect(database)
                        try:
                            self.assertEqual(list(other.iterdump()), snapshot)
                            self.assertEqual(db.integrity_problems(other), [])
                        finally:
                            other.close()
                    finally:
                        connection.close()
                    reopened = db.connect(database)
                    try:
                        self.assertEqual(list(reopened.iterdump()), snapshot)
                        self.assertEqual(db.integrity_problems(reopened), [])
                        self.assert_scenario_links(reopened, names)
                    finally:
                        reopened.close()

    def assert_scenario_links(self, connection, names):
        if "a" in names:
            current = connection.execute(
                "SELECT version_observee_id, version_cible_id FROM parcours WHERE id = ?",
                (identifier("a-parc-insertion"),),
            ).fetchone()
            self.assertEqual(tuple(current), (identifier("a-vp-obs-1"), identifier("a-vp-cible-2")))
            source = connection.execute("SELECT version_source_id FROM version_parcours WHERE id = ?",
                                        (identifier("a-vp-cible-2"),)).fetchone()
            self.assertEqual(source[0], identifier("a-vp-cible-1"))
            for table, key in (("etape", "accueil-01"), ("occurrence_contact", "accueil-guichet")):
                stable = str(uuid5(NAMESPACE_URL, f"journai-fixture/{table}/{key}"))
                self.assertEqual(connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE cle_stable = ?", (stable,)
                ).fetchone()[0], 3)
            self.assertEqual(connection.execute(
                "SELECT remplace_decision_id FROM decision_priorite WHERE id = ?",
                ("c45de4bb-d974-5db9-a700-feb919b9bfa9",),
            ).fetchone()[0], "12f5f79f-1ec0-5f24-bf19-4218bcded20b")
            self.assertEqual([tuple(row) for row in connection.execute(
                "SELECT role_occurrence, etat_utilisation FROM occurrence_ressource ORDER BY role_occurrence"
            )], [("insuffisante", "utilise"), ("necessaire", "utilise")])
        if "b" in names:
            current = connection.execute(
                "SELECT version_observee_id, version_cible_id FROM parcours WHERE id = ?",
                (identifier("b-parc-atelier"),),
            ).fetchone()
            self.assertEqual(tuple(current), (identifier("b-vp-obs-1"), None))


if __name__ == "__main__":
    unittest.main()
