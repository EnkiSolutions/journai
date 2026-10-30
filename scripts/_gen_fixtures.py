"""Générateur local des fixtures synthétiques (jetable, exécuté puis supprimé).

Contrôle à l'émission : clés inconnues et valeurs hors énumération du schéma = échec.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from journai import db, migrations  # noqa: E402

SCHEMA = Path(__file__).resolve().parent.parent / "journai" / "migrations"
OUT = Path(__file__).resolve().parent.parent / "journai" / "fixtures"
T0 = "2026-01-05T09:00:00+00:00"
T1 = "2026-02-10T09:00:00+00:00"
T2 = "2026-03-02T10:00:00+00:00"
ST = "systeme"

conn = db.connect(":memory:")
migrations.migrate(conn, SCHEMA)
COLS = {t: set(db.column_names(conn, t)) for t in db.table_names(conn)}
SQL = "\n".join(p.read_text(encoding="utf-8") for p in sorted(SCHEMA.glob("*.sql")))
ENUM = {m[0]: set(m[1].split(", ")) for m in
        re.findall(r"CHECK \((\w+) IN \(([^)]*)\)\)", SQL)}
ENUM = {k: {v.strip(" '") for v in vs.split(",")} for k, vs in
          ((k, v) for k, v in ENUM.items())}
ENUM = {k: {v.strip(" '") for v in vs.split(",")} for k, vs in
          re.findall(r"CHECK \((\w+) IN \(([^)]*)\)\)", SQL).items()} if False else ENUM


def audit(sets, tables):
    for table, rows in tables.items():
        for n, row in enumerate(rows, 1):
            unknown = set(row) - COLS.get(table, set())
            if unknown:
                sys.exit(f"{table} #{n}: clés inconnues {sorted(unknown)}")
            for key, value in row.items():
                allowed = ENUM.get(key)
                if allowed is not None and value is not None and value not in allowed:
                    sys.exit(f"{table} #{n}: {key}={value!r} hors énumération {sorted(allowed)}")
            for key in ("cree_par", "modifie_par", "resolu_par"):
                v = row.get(key)
                if v is not None and not str(v).startswith(("u-", "s-")):
                    sys.exit(f"{table} #{n}: {key}={v!r} n'est pas un identifiant")
            for key in ("cree_le", "modifie_le", "resolu_le"):
                v = row.get(key)
                if v is not None and len(str(v)) != 25:
                    sys.exit(f"{table} #{n}: {key}={v!r} n'est pas un horodatage ISO")


def audit_rows(tables):
    for table, rows in tables.items():
        for n, row in enumerate(rows, 1):
            unknown = set(row) - COLS.get(table, set())
            if unknown:
                sys.exit(f"{table} #{n} : clés inconnues {sorted(unknown)}")
            for key, value in row.items():
                allowed = ENUM.get(key)
                if allowed is not None and value is not None and value not in allowed:
                    sys.exit(f"{table} #{n} : {key}={value!r} hors énumération {sorted(allowed)}")
            for key in ("cree_par", "modifie_par", "resolu_par"):
                v = row.get(key)
                if v is not None and not str(v).startswith(("u-", "s-")):
                    sys.exit(f"{table} #{n} : {key}={v!r} n'est pas un identifiant")
            for key in ("cree_le", "modifie_le", "resolu_le", "observe_le"):
                v = row.get(key)
                if v is not None and len(str(v)) != 25:
                    sys.exit(f"{table} #{n} : {key}={v!r} n'est pas un horodatage ISO")


rows = {}


def add(table, *values):
    rows.setdefault(table, []).extend(values)


def meta(who, when=T0):
    return {"cree_par": who, "cree_le": when}


def space(table, row):
    for key in ("id", "espace_id"):
        if str(row.get(key, "")).startswith("b-"):
            return "b"
    return "a"


def emit(tables):
    audit_rows(tables)
    for name in ("a", "b"):
        payload = {"tables": [], "updates": []}
        for table, items in tables.items():
            kept = [r for r in items if space(table, r) == name]
            if kept:
                payload["tables"].append({"table": table, "rows": kept})
        OUT.glob
        (OUT / f"espace-{name}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"espace-{name}.json {len(payload['tables'])} tables")
