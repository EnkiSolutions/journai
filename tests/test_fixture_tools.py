import copy
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from journai import db, migrations, seed
from scripts import _audit_fixtures as audit, _gen_fixtures as generator


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "journai" / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / f"espace-{name}.json").read_text(encoding="utf-8"))


def combined():
    tables, updates = {}, []
    for name in ("a", "b"):
        data = fixture(name)
        for entry in data["tables"]:
            tables.setdefault(entry["table"], []).extend(entry["rows"])
        updates.extend(data["updates"])
    return tables, updates


class FixtureToolTests(unittest.TestCase):
    def test_import_and_existing_fixtures_pass_both_audits(self):
        result = subprocess.run([sys.executable, "-c", "import scripts._gen_fixtures"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("a", "b"):
            tables = {e["table"]: e["rows"] for e in fixture(name)["tables"]}
            self.assertEqual(audit.pre_audit(tables), [])
            generator.audit(None, tables)
            generator.audit_rows(tables)
        with redirect_stdout(StringIO()):
            self.assertFalse(audit.main())

    def test_required_columns_defaults_and_null(self):
        tables, _ = combined()
        row = copy.deepcopy(tables["structure"][0])
        self.assertNotIn("revision", row)
        self.assertEqual(audit.pre_audit({"structure": [row]}), [])
        del row["type_structure"]
        problems = audit.pre_audit({"structure": [row]})
        self.assertTrue(any("manque type_structure" in p for p in problems), problems)
        with self.assertRaisesRegex(SystemExit, "manque type_structure"):
            generator.audit(None, {"structure": [row]})
        row["intrus"] = 1
        self.assertIn("colonne inconnue intrus", " ".join(audit.pre_audit({"structure": [row]})))
        member = copy.deepcopy(tables["membre_espace"][0])
        member["statut"] = None
        self.assertTrue(any("statut ne peut être null" in p
                            for p in audit.pre_audit({"membre_espace": [member]})))

    def test_enums_are_scoped_to_table_and_column(self):
        tables, _ = combined()
        for table, valid, invalid in (("membre_espace", "actif", "livre"),
                                      ("action", "livre", "actif")):
            row = copy.deepcopy(tables[table][0])
            row["statut"] = valid
            self.assertEqual(audit.pre_audit({table: [row]}), [])
            row["statut"] = invalid
            with self.subTest(table=table):
                self.assertIn("statut", " ".join(audit.pre_audit({table: [row]})))
                with self.assertRaisesRegex(SystemExit, "statut"):
                    generator.audit_rows({table: [row]})

    def test_uuid_instants_and_civil_dates(self):
        tables, _ = combined()
        row = copy.deepcopy(tables["constat"][0])
        for key, valid, invalids in (
            ("cree_par", row["cree_par"], ["u-author", row["cree_par"].upper()]),
            ("cree_le", "2026-01-01T12:00:00.000000+00:00",
             ["2026-01-01T12:00:00+00:00", "2026-01-01T12:00:00.000000+01:00", "invalid"]),
            ("observe_le", "2024-02-29", ["2026-02-29", "2024-02-29T00:00:00+00:00"]),
        ):
            good = {**row, key: valid}
            self.assertEqual(audit.pre_audit({"constat": [good]}), [])
            for value in invalids:
                bad = {**row, key: value}
                with self.subTest(key=key, value=value):
                    self.assertIn(key, " ".join(audit.pre_audit({"constat": [bad]})))
                    with self.assertRaisesRegex(SystemExit, key):
                        generator.audit_rows({"constat": [bad]})
        projet = {**tables["projet"][0], "date_debut": "2024-02-29"}
        self.assertEqual(audit.pre_audit({"projet": [projet]}), [])
        projet["date_debut"] = "2025-02-29"
        self.assertIn("date_debut", " ".join(audit.pre_audit({"projet": [projet]})))

    def test_emission_routes_and_round_trips_through_seed(self):
        tables, updates = combined()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(generator, "OUT", root), redirect_stdout(StringIO()):
                generator.emit(tables, updates)
            loaded = seed.load_fixture(root)
            self.assertEqual(len(loaded["updates"]), len(updates))
            for name in ("a", "b"):
                data = json.loads((root / f"espace-{name}.json").read_text(encoding="utf-8"))
                self.assertEqual(data, fixture(name))
                self.assertIn(data["env"], ("dev", "test"))
                separate = root / name
                separate.mkdir()
                (separate / "fixture.json").write_text(json.dumps(data), encoding="utf-8")
                with closing(db.connect(separate / "test.db")) as conn:
                    migrations.migrate(conn, audit.SCHEMA)
                    seed.seeded(conn, separate, env="test")
                    self.assertEqual(db.integrity_problems(conn), [])
            with closing(db.connect(root / "test.db")) as conn:
                migrations.migrate(conn, audit.SCHEMA)
                self.assertEqual(sum(seed.seeded(conn, root, env="test").values()), 116)
                self.assertEqual(db.integrity_problems(conn), [])

    def test_unknown_and_ambiguous_memberships_are_refused_before_writing(self):
        tables, updates = combined()
        for kind in ("unknown_space", "missing_member", "ambiguous_member"):
            altered = copy.deepcopy(tables)
            if kind == "unknown_space":
                altered["structure"][0]["espace_id"] = "00000000-0000-0000-0000-000000000000"
            elif kind == "missing_member":
                user = altered["utilisateur"][0]["id"]
                altered["membre_espace"] = [r for r in altered["membre_espace"] if r["utilisateur_id"] != user]
            else:
                member = copy.deepcopy(altered["membre_espace"][0])
                member["espace_id"] = next(s for s in generator.SPACES if s != member["espace_id"])
                altered["membre_espace"].append(member)
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with patch.object(generator, "OUT", root), self.assertRaisesRegex(ValueError, "appartenance"):
                    generator.emit(altered, updates)
                self.assertEqual(list(root.iterdir()), [])

    def test_main_reports_invalid_fixture_and_returns_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("a", "b"):
                data = fixture(name)
                if name == "a":
                    del data["tables"][0]["rows"][0]["nom_affiche"]
                (root / f"espace-{name}.json").write_text(json.dumps(data), encoding="utf-8")
            output = StringIO()
            with patch.object(audit, "FIX", root), redirect_stdout(output):
                self.assertTrue(audit.main())
            self.assertIn("manque nom_affiche", output.getvalue())


if __name__ == "__main__":
    unittest.main()
