"""Semis des fixtures synthétiques : données de démonstration, aucun bénéficiaire réel.

Le fichier JSON décrit les lignes par table, dans un ordre d'insertion compatible avec les
clés étrangères. Les `updates` règlent la circularité parcours <-> version déclarée.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from journai import db
from journai.config import load_config
from journai.migrations import applied_versions

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class SeedError(RuntimeError):
    """Semis refusé : base non vide, table inconnue, colonne inconnue, clé étrangère satisfaite plus tard."""


def load_fixture(fixtures_dir: str | Path = FIXTURES_DIR) -> dict[str, object]:
    path = Path(fixtures_dir)
    files = sorted(path.glob("*.json"))
    if not files:
        raise SeedError(f"aucun fixture dans {path}")
    tables: list[dict[str, object]] = []
    updates: list[str] = []
    for fixture in files:
        with fixture.open(encoding="utf-8") as handle:
            data = json.load(handle)
        tables += list(data.get("tables", []))
        updates += list(data.get("updates", []))
    return {"tables": tables, "updates": updates}


def _check_columns(connection: sqlite3.Connection, table: str, rows: list[dict[str, object]]) -> None:
    known = set(db.column_names(connection, table))
    if not known:
        raise SeedError(f"table inconnue dans le schéma : {table}")
    for row in rows:
        unknown = set(row) - known
        if unknown:
            raise SeedError(f"{table} : colonnes inconnues {sorted(unknown)}")


def seeded(connection: sqlite3.Connection, fixtures_dir: str | Path = FIXTURES_DIR, *, replace: bool = False) -> dict[str, int]:
    """Insère les fixtures ; refuse si les tables concernées ne sont pas vides (sauf replace)."""
    if not applied_versions(connection):
        raise SeedError("base non migrée : lancer `python -m journai.migrations` avant le semis")
    fixture = load_fixture(fixtures_dir)
    tables = fixture["tables"]
    assert isinstance(tables, list)
    counts: dict[str, int] = {}
    for entry in tables:
        table, rows = str(entry["table"]), list(entry["rows"])
        _check_columns(connection, table, rows)
        if replace:
            counts[table] = counts.get(table, 0) + len(rows)
            continue
        filled = connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()  # noqa: S608
        if int(filled["n"]):
            raise SeedError(f"table {table} non vide : utiliser --replace pour la recharger")
        counts[table] = len(rows)
    connection.execute("BEGIN")
    try:
        if replace:
            for entry in reversed(tables):
                table = str(entry["table"])
                connection.execute(f"DELETE FROM {table}")  # noqa: S608 - vidage des tables de fixtures
        for entry in tables:
            table, rows = str(entry["table"]), list(entry["rows"])
            for row in rows:
                names = list(row)
                marks = ", ".join(f":{name}" for name in names)
                connection.execute(
                    f"INSERT INTO {table} ({', '.join(names)}) VALUES ({marks})", row  # noqa: S608 - colonnes vérifiées
                )
        for sql in fixture["updates"]:
            assert isinstance(sql, str)
            connection.execute(sql)
        problems = db.integrity_problems(connection)
        if problems:
            raise SeedError(f"fixtures refusées par l'intégrité : {problems[:3]}")
    except (sqlite3.Error, SeedError) as exc:
        connection.rollback()
        raise SeedError(f"semis refusé : {exc}") from exc
    connection.commit()
    return {table: n for table, n in counts.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="journai-seed", description="Charge les fixtures synthétiques.")
    parser.add_argument("--db", dest="db_path", help="chemin de la base SQLite")
    parser.add_argument("--fixtures", dest="fixtures_dir", help="répertoire des fixtures JSON")
    parser.add_argument("--replace", action="store_true", help="vide les tables de fixtures avant insertion")
    args = parser.parse_args(argv)
    config = load_config()
    connection = db.connect(args.db_path or config.db_path)
    try:
        counts = seeded(connection, args.fixtures_dir or config.schema_dir.parent / "fixtures", replace=args.replace)
        print("fixtures insérées :", ", ".join(f"{t}={n}" for t, n in counts.items()))
    except SeedError as exc:
        print("ERREUR :", exc, file=sys.stderr)
        return 1
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
