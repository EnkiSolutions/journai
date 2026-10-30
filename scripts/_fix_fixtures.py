"""Correction locale des fixtures synthétiques puis audit schéma + énumérations (jetable)."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from journai import db, migrations  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "journai" / "migrations"
FIX = ROOT / "journai" / "fixtures"
T0 = "2026-01-05T09:00:00+00:00"

conn = db.connect(":memory:")
migrations.migrate(conn, SCHEMA)
COLS = {t: set(db.column_names(conn, t)) for t in db.table_names(conn)}
SQL = "\n".join(p.read_text(encoding="utf-8") for p in sorted(SCHEMA.glob("*.sql")))
ENUM = {}
for block, body in re.findall(r"CREATE TABLE (\w+) \((.*?)\n\);", SQL, re.S):
    for col, values in re.findall(r"CHECK \((\w+) IN \(([^)]*)\)\)", body):
        ENUM[(block, col)] = {v.strip(" '") for v in values.split(",")}

ROLE = {  # rôle de l'opération dans l'occurrence, selon le scénario
    ("a-o-obs-contact-guichet", "a-op-guichet"): "realise",
    ("a-o-obs-suivi", "a-op-relance"): "contributif",
    ("a-occ-2", "a-op-relance"): "realise",
    ("a-occ-3", "a-op-guichet"): "declencheur",
    ("b-o-1", "b-op-permanence"): "realise",
}

for name in ("a", "b"):
    path = FIX / f"espace-{name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    tables = data["tables"] if isinstance(data, dict) else data
    for entry in tables:
        table = entry["table"]
        for n, row in enumerate(entry["rows"], 1):
            where = f"{table} #{n}"
            unknown = set(row) - COLS.get(table, set())
            if unknown:
                sys.exit(f"{where} : clés inconnues {sorted(unknown)}")
            if table == "operation" and "etat_operationnel" not in row:
                row["etat_operationnel"] = "assure"
            is_id = lambda v: str(v).startswith(("u-", "s-"))
            admin = "u-admin" if name == "a" else "u-espace-b"
            if "cree_par" in row and not is_id(row["cree_par"]):
                row["cree_par"] = admin
            if "cree_le" in row and is_id(row["cree_le"]):
                row["cree_le"] = T0
            if row.get("modifie_par") is not None and not is_id(row["modifie_par"]):
                row["modifie_par"] = admin
            if row.get("modifie_le") is not None and is_id(row["modifie_le"]):
                row["modifie_le"] = T0
            if row.get("resolu_par") is not None and not is_id(row["resolu_par"]):
                row["resolu_par"] = admin
            if row.get("resolu_le") is not None and is_id(row["resolu_le"]):
                row["resolu_le"] = T0
            if table == "occurrence_operation":
                key = (row["occurrence_contact_id"], row["operation_id"])
                row["role_operation"] = ROLE.get(key, "realise")
            for key, value in row.items():
                allowed = ENUM.get((table, key))
                if allowed is not None and value is not None and value not in allowed:
                    sys.exit(f"{where} : {key}={value!r} hors énumération {sorted(allowed)}")
            for key in ("cree_par", "modifie_par", "resolu_par"):
                value = row.get(key)
                if value is not None and not str(value).startswith(("u-", "s-")):
                    sys.exit(f"{where} : {key}={value!r} n'est pas un identifiant")
            for key in ("cree_le", "modifie_le", "resolu_le", "observe_le", "date_revision_prevue"):
                value = row.get(key)
                if value is not None and value not in ("assure",) and len(str(value)) < 20:
                    sys.exit(f"{where} : {key}={value!r} n'est pas un horodatage ISO")
    payload = {"tables": tables, "updates": data.get("updates", [])}
    if name == "a":
        payload["updates"] = [
            {"set": {"version_observee_id": "a-vp-obs-1", "version_cible_id": "a-vp-cible-2"},
             "where": "id = 'a-parc-insertion'"},
        ]
    if name == "b":
        payload["updates"] = [
            {"set": {"version_observee_id": "b-vp-obs-1"}, "where": "id = 'b-parc-atelier'"},
        ]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    n = sum(len(e["rows"]) for e in payload["tables"])
    print(f"espace-{name}.json {len(payload['tables'])} tables {n} lignes")
