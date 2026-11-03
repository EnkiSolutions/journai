"""Audit local des fixtures contre le schéma : colonnes, énumérations, dates, FK (jetable)."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from journai import db, migrations  # noqa: E402

SCHEMA = Path(__file__).resolve().parent.parent / "journai" / "migrations"
FIX = Path(__file__).resolve().parent.parent / "journai" / "fixtures"

conn = db.connect(":memory:")
migrations.migrate(conn, SCHEMA)
COLS = {t: set(db.column_names(conn, t)) for t in db.table_names(conn)}
SQL = "\n".join(p.read_text(encoding="utf-8") for p in sorted(SCHEMA.glob("*.sql")))
ENUM = {}
for table, body in re.findall(r"CREATE TABLE (\w+) \((.*?)\n\);", SQL, re.S):
    for col, values in re.findall(r"CHECK \((\w+) IN \(([^)]*)\)\)", body):
        ENUM[(table, col)] = {v.strip(" '") for v in values.split(",")}
NOT_NULL = {
    table: {m[0] for m in re.findall(r"^\s*(\w+) [A-Z]+ NOT NULL", body, re.M)}
    for table, body in re.findall(r"CREATE TABLE (\w+) \((.*?)\n\);", SQL, re.S)
}

problems = []
for name in ("a", "b"):
    data = json.loads((FIX / f"espace-{name}.json").read_text(encoding="utf-8"))
    tables = data["tables"] if isinstance(data, dict) else data
    seen = {e["table"]: {tuple(sorted(r)) for r in e["rows"]} for e in tables}
    for entry in tables:
        table = entry["table"]
        rows = entry["rows"]
        for n, row in enumerate(rows, 1):
            where = f"{name}/{table}#{n}"
            if set(row) - COLS.get(table, set()):
                problems.append(f"{where} colonnes {sorted(set(row) - COLS[table])}")
            for col in sorted(NOT_NULL.get(table, set()) - set(row)):
                if col not in ("modifie_par", "modifie_le", "archive_le", "resolu_par", "resolu_le"):
                    problems.append(f"{where} manque {col}")
            for col, value in row.items():
                allowed = ENUM.get((table, col))
                if allowed is not None and value is not None and value not in allowed:
                    problems.append(f"{where} {col}={value!r} hors {sorted(allowed)}")
                if col.endswith(("_le", "_le_prevu")) and value is not None and len(str(value)) != 25:
                    problems.append(f"{where} {col}={value!r} date invalide")
                if col.endswith("_par") and value is not None and not str(value).startswith(("u-", "s-")):
                    problems.append(f"{where} {col}={value!r} identifiant invalide")
            if len(rows) != len(seen[table]):
                pass
    # identifiants référencés (vérification grossière des FK par clé)
    ids = {}
    for entry in tables:
        for row in entry["rows"]:
            if "id" in row:
                ids.setdefault(entry["table"], set()).add(row["id"])
    for entry in tables:
        for n, row in enumerate(entry["rows"], 1):
            for col, value in row.items():
                if col.endswith("_id") and not col.startswith(("espace_id",)) and value is not None:
                    target = col[: -len("_id")]
                    if target in ids and value not in ids[target] and target not in ("version_source",):
                        problems.append(f"{name}/{entry['table']}#{n} référence {col}={value!r} inconnue")

print(f"\n{len(problems)} problèmes")
for p in problems:
    print(" -", p)
