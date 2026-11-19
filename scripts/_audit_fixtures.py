"""Audit local des fixtures contre les contraintes du socle."""
import json
import re
import sys
import tempfile
from contextlib import closing
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from journai import db, migrations, seed, validation  # noqa: E402

SCHEMA = Path(__file__).resolve().parent.parent / "journai" / "migrations"
FIX = Path(__file__).resolve().parent.parent / "journai" / "fixtures"

with tempfile.TemporaryDirectory() as directory, closing(db.connect(Path(directory) / "schema.db")) as conn:
    migrations.migrate(conn, SCHEMA)
    INFO = {t: list(conn.execute("SELECT * FROM pragma_table_info(?)", (t,))) for t in db.table_names(conn)}
COLS = {table: {col[1] for col in info} for table, info in INFO.items()}
NON_NULL = {table: {col[1] for col in info if col[3] or col[5]} for table, info in INFO.items()}
NOT_NULL = {table: {col[1] for col in info if (col[3] or col[5]) and col[4] is None}
            for table, info in INFO.items()}
SQL = "\n".join(p.read_text(encoding="utf-8") for p in sorted(SCHEMA.glob("*.sql")))
ENUM = {}
for table, body in re.findall(r"CREATE TABLE (\w+) \((.*?)\n\);", SQL, re.S):
    for col, values in re.findall(r"CHECK \((\w+) IN \(([^)]*)\)\)", body):
        ENUM[(table, col)] = {v.strip().strip("'") for v in values.split(",")}


def row_problems(table, row):
    if table not in COLS:
        return [f"table inconnue {table}"]
    problems = []
    for col in sorted(set(row) - COLS[table]):
        problems.append(f"colonne inconnue {col}")
    for col in sorted(NOT_NULL[table] - set(row)):
        problems.append(f"manque {col}")
    for col, value in row.items():
        if value is None:
            if col in NON_NULL[table]:
                problems.append(f"{col} ne peut être null")
            continue
        allowed = ENUM.get((table, col))
        if allowed is not None and (not isinstance(value, str) or value not in allowed):
            problems.append(f"{col}={value!r} hors énumération {sorted(allowed)}")
        try:
            if col == "id" or col == "cle_stable" or col.endswith(("_id", "_par")):
                validation.canonical_uuid(value)
            elif col in validation.INSTANTS:
                if validation.canonical_instant(value) != value:
                    raise ValueError("instant UTC non canonique")
            elif col.startswith("date_") or col in {"observe_le", "periode_debut", "periode_fin"}:
                if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                    raise ValueError("date civile non canonique")
        except (ValueError, TypeError) as exc:
            problems.append(f"{col}={value!r} invalide : {exc}")
    return problems


def pre_audit(tables):
    return [f"{table} #{n} : {problem}"
            for table, rows in tables.items() for n, row in enumerate(rows, 1)
            for problem in row_problems(table, row)]


def main():
    problems = []
    for name in ("a", "b"):
        path = FIX / f"espace-{name}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for entry in data["tables"]:
                problems.extend(f"{name}/{p}" for p in pre_audit({entry["table"]: entry["rows"]}))
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / path.name).write_text(json.dumps(data), encoding="utf-8")
                with closing(db.connect(root / "audit.db")) as conn:
                    migrations.migrate(conn, SCHEMA)
                    seed.seeded(conn, root, env="test")
        except (OSError, ValueError, KeyError, TypeError, seed.SeedError) as exc:
            problems.append(f"{name} : {exc}")
    print(f"\n{len(problems)} problèmes")
    for problem in problems:
        print(" -", problem)
    return bool(problems)


if __name__ == "__main__":
    sys.exit(main())
