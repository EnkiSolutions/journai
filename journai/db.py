"""Accès SQLite du socle : clés étrangères actives, journal d'audit, verrou d'intégrité."""

from __future__ import annotations

import sqlite3
from pathlib import Path

def connect(db_path: str | Path, *, create: bool = True) -> sqlite3.Connection:
    """Ouvre la base, crée les dossiers, active les invariants structurels."""
    path = Path(db_path)
    if str(path) != ":memory:":
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
    else:
        connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    # Transactions pilotées par le code (migrations, semis) : pas de BEGIN implicite de Python.
    connection.isolation_level = None
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA recursive_triggers = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def table_names(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [str(row["name"]) for row in rows]


def column_names(connection: sqlite3.Connection, table: str) -> list[str]:
    rows = connection.execute(f"PRAGMA table_info({table})")  # noqa: S608 - nom issu du schéma
    return [str(row["name"]) for row in rows]


def integrity_problems(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """Clés étrangères non satisfaites et intégrité physique : contrôle exigé au démarrage."""
    problems = list(connection.execute("PRAGMA foreign_key_check"))
    if problems:
        return problems
    result = list(connection.execute("PRAGMA integrity_check"))
    if len(result) == 1 and str(result[0][0]) == "ok":
        return []
    return result
