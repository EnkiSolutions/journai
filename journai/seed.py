"""Chargement atomique des fixtures synthétiques dans une base migrée."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path

from journai import db, validation
from journai.config import load_config
from journai.migrations import JOURNAL_TABLE, applied_versions

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class SeedError(RuntimeError):
    """Semis refusé sans modifier les données précédentes."""


def load_fixture(fixtures_dir: str | Path = FIXTURES_DIR) -> dict[str, list]:
    path = Path(fixtures_dir)
    files = sorted(path.glob("*.json"))
    if not files:
        raise SeedError(f"aucun fixture dans {path}")
    tables, updates = [], []
    for fixture in files:
        try:
            with fixture.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError) as exc:
            raise SeedError(f"fixture illisible {fixture} : {exc}") from exc
        if not isinstance(data, dict) or set(data) - {"env", "tables", "updates"}:
            raise SeedError(f"fixture mal formé : {fixture}")
        if data.get("env") not in ("dev", "test"):
            raise SeedError(f"environnement du fixture invalide : {fixture}")
        if not isinstance(data.get("tables"), list) or not isinstance(data.get("updates", []), list):
            raise SeedError(f"tables ou updates mal formées : {fixture}")
        tables.extend(data["tables"])
        updates.extend(data.get("updates", []))
    return {"tables": tables, "updates": updates}


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _values(values: object, columns: set[str], nullable: set[str], integer_columns: set[str], table: str) -> None:
    if not isinstance(values, dict) or not values or not all(isinstance(k, str) for k in values):
        raise SeedError(f"{table} : valeurs mal formées")
    unknown = set(values) - columns
    if unknown:
        raise SeedError(f"{table} : colonnes inconnues {sorted(unknown)}")
    for value in values.values():
        if not isinstance(value, (str, int, float, type(None))) or (
            isinstance(value, float) and not math.isfinite(value)
        ) or (isinstance(value, int) and not -(2**63) <= value < 2**63):
            raise SeedError(f"{table} : valeur non scalaire ou invalide")
    try:
        validation.normalize_values(values, nullable, integer_columns)
    except ValueError as exc:
        raise SeedError(f"{table} : {exc}") from exc


def seeded(connection: sqlite3.Connection, fixtures_dir: str | Path = FIXTURES_DIR, *,
           env: str | None = None, replace: bool = False, allow_replace: bool = False) -> dict[str, int]:
    """Insère les fixtures en dev/test ; le remplacement exige les deux autorisations."""
    if env not in ("dev", "test"):
        raise SeedError(f"environnement courant interdit ou inconnu : {env!r}")
    if replace and not allow_replace:
        raise SeedError("remplacement non autorisé")
    if not applied_versions(connection):
        raise SeedError("base non migrée : lancer `python -m journai.migrations` avant le semis")
    fixture = load_fixture(fixtures_dir)
    known = set(db.table_names(connection)) - {JOURNAL_TABLE}
    columns: dict[str, set[str]] = {}
    nullable: dict[str, set[str]] = {}
    integer_columns: dict[str, set[str]] = {}

    def check_table(name: object) -> str:
        if not isinstance(name, str) or name not in known or name.lower() == JOURNAL_TABLE.lower():
            raise SeedError(f"table inconnue ou interdite : {name!r}")
        if name not in columns:
            info = list(connection.execute("SELECT * FROM pragma_table_info(?)", (name,)))
            columns[name] = {row[1] for row in info}
            nullable[name] = {row[1] for row in info if not row[3] and not row[5]}
            integer_columns[name] = {row[1] for row in info if "INT" in row[2].upper()}
        return name

    counts: dict[str, int] = {}
    for entry in fixture["tables"]:
        if not isinstance(entry, dict) or set(entry) != {"table", "rows"} or not isinstance(entry["rows"], list):
            raise SeedError("entrée tables mal formée")
        table = check_table(entry["table"])
        for row in entry["rows"]:
            _values(row, columns[table], nullable[table], integer_columns[table], table)
        counts[table] = counts.get(table, 0) + len(entry["rows"])
    for update in fixture["updates"]:
        if not isinstance(update, dict) or set(update) != {"table", "id", "set"}:
            raise SeedError("update mal formée : attendu {table, id, set}, sans SQL libre")
        table = check_table(update["table"])
        if table not in counts:
            raise SeedError(f"{table} : update sans table à semer")
        if "id" not in columns[table]:
            raise SeedError(f"{table} : colonne id absente")
        _values({"id": update["id"]}, columns[table], nullable[table], integer_columns[table], table)
        if update["id"] is None:
            raise SeedError(f"{table} : id absent")
        _values(update["set"], columns[table], nullable[table], integer_columns[table], table)

    for table in counts:
        if not replace and connection.execute(f"SELECT 1 FROM {_quote(table)} LIMIT 1").fetchone():
            raise SeedError(f"table {table} non vide : utiliser --replace pour la recharger")
    try:
        if replace:
            # Rompre les références circulaires nullable décrites par les updates avant suppression.
            for table in counts:
                info = list(connection.execute("SELECT * FROM pragma_table_info(?)", (table,)))
                nullable_columns = {row[1] for row in info if not row[3] and not row[5]}
                foreign = list(connection.execute("SELECT * FROM pragma_foreign_key_list(?)", (table,)))
                updated = {key for update in fixture["updates"] if update["table"] == table
                           for key in update["set"]}
                clear = nullable_columns & {row[3] for row in foreign if row[2] == table or row[3] in updated}
                if clear:
                    assignments = ", ".join(f"{_quote(key)} = NULL" for key in sorted(clear))
                    connection.execute(f"UPDATE {_quote(table)} SET {assignments}")
            for table in reversed(counts):
                connection.execute(f"DELETE FROM {_quote(table)}")
        for entry in fixture["tables"]:
            table = entry["table"]
            for row in entry["rows"]:
                names = ", ".join(_quote(name) for name in row)
                marks = ", ".join("?" for _ in row)
                connection.execute(f"INSERT INTO {_quote(table)} ({names}) VALUES ({marks})", tuple(row.values()))
        for update in fixture["updates"]:
            assignments = ", ".join(f"{_quote(key)} = ?" for key in update["set"])
            cursor = connection.execute(f"UPDATE {_quote(update['table'])} SET {assignments} WHERE id = ?",
                                        (*update["set"].values(), update["id"]))
            if cursor.rowcount != 1:
                raise SeedError(f"{update['table']} : update doit toucher exactement une ligne")
        problems = db.integrity_problems(connection)
        if problems:
            raise SeedError(f"fixtures refusées par l'intégrité : {problems[:3]}")
        connection.commit()
    except Exception as exc:
        connection.rollback()
        if isinstance(exc, (sqlite3.Error, SeedError)):
            raise SeedError(f"semis refusé : {exc}") from exc
        raise
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="journai-seed", description="Charge les fixtures synthétiques.")
    parser.add_argument("--db", dest="db_path", help="chemin de la base SQLite")
    parser.add_argument("--fixtures", dest="fixtures_dir", help="répertoire des fixtures JSON")
    parser.add_argument("--replace", action="store_true", help="vide les tables de fixtures avant insertion")
    args = parser.parse_args(argv)
    try:
        config = load_config()
        connection = db.connect(args.db_path or config.db_path)
        try:
            counts = seeded(connection, args.fixtures_dir or FIXTURES_DIR,
                            env=config.env, replace=args.replace, allow_replace=args.replace)
            print("fixtures insérées :", ", ".join(f"{t}={n}" for t, n in counts.items()))
        finally:
            connection.close()
    except (SeedError, sqlite3.Error, OSError, ValueError, RuntimeError) as exc:
        print("ERREUR :", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
