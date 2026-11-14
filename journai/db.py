"""Accès SQLite du socle : clés étrangères actives, journal d'audit, verrou d'intégrité."""

from __future__ import annotations

import sqlite3
from pathlib import Path

def connect(db_path: str | Path, *, create: bool = True) -> sqlite3.Connection:
    """Ouvre la base, crée les dossiers, active les invariants structurels."""
    path = Path(db_path)
    if str(path) != ":memory:" and create:
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, autocommit=True)
    try:
        connection.row_factory = sqlite3.Row
        for name, setting, expected in (
            ("foreign_keys", "ON", 1),
            ("recursive_triggers", "ON", 1),
            ("journal_mode", "WAL", "wal"),
        ):
            connection.execute(f"PRAGMA {name} = {setting}")
            row = connection.execute(f"PRAGMA {name}").fetchone()
            if row is None or row[0] != expected:
                raise RuntimeError(f"PRAGMA {name} incorrect : {row}")
        connection.autocommit = False
    except Exception as exc:
        connection.close()
        raise RuntimeError(f"initialisation SQLite refusée : {exc}") from exc
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
