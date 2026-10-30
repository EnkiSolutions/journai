"""Migrations versionnées : chaque fichier .sql est appliqué une fois, dans l'ordre, en transaction.

Le journal schema_migration rend l'opération idempotente et donne la version courante au
démarrage. La version n'est journalisée qu'après contrôle d'intégrité : une migration qui
laisse une clé étrangère non satisfaite est annulée et la base reste à la version vérifiée.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from journai import db
from journai.config import load_config

JOURNAL_TABLE = "schema_migration"


class MigrationError(RuntimeError):
    """Migration refusée : le schéma reste à la dernière version vérifiée."""


def _ensure_journal(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"CREATE TABLE IF NOT EXISTS {JOURNAL_TABLE} ("  # noqa: S608 - table de service du socle
        "version TEXT NOT NULL PRIMARY KEY, applique_le TEXT NOT NULL, fichier TEXT NOT NULL)"
    )


def applied_versions(connection: sqlite3.Connection) -> list[str]:
    _ensure_journal(connection)
    rows = connection.execute(f"SELECT version FROM {JOURNAL_TABLE} ORDER BY version")  # noqa: S608
    return [str(row["version"]) for row in rows]


def discover(schema_dir: str | Path) -> list[tuple[str, Path]]:
    """Versions attendues, triées par préfixe numérique du nom de fichier."""
    directory = Path(schema_dir)
    files = sorted(p for p in directory.glob("*.sql") if p.name[:4].isdigit())
    if not files:
        raise MigrationError(f"aucune migration trouvée dans {directory}")
    versions = [p.name.split("_", 1)[0] for p in files]
    if len(set(versions)) != len(versions):
        raise MigrationError(f"numéros de migration dupliqués dans {directory}")
    return list(zip(versions, files))


def plan(connection: sqlite3.Connection, schema_dir: str | Path) -> list[tuple[str, Path]]:
    done = set(applied_versions(connection))
    return [(version, path) for version, path in discover(schema_dir) if version not in done]


def statements(sql: str) -> list[str]:
    """Découpe le script en instructions complètes (sqlite3.complete_statement gère quotes et commentaires)."""
    out: list[str] = []
    buffer: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        if sqlite3.complete_statement(" ".join(buffer)):
            out.append(" ".join(buffer).strip())
            buffer = []
    if "".join(buffer).strip():
        raise MigrationError("script de migration incomplet (instruction non terminée)")
    return out


def migrate(connection: sqlite3.Connection, schema_dir: str | Path) -> list[str]:
    _ensure_journal(connection)
    applied: list[str] = []
    for version, path in plan(connection, schema_dir):
        instructions = statements(path.read_text(encoding="utf-8"))
        if not instructions:
            raise MigrationError(f"{path.name} ne contient aucune instruction")
        connection.execute("BEGIN")
        try:
            for sql in instructions:
                connection.execute(sql)
            connection.execute(
                f"INSERT INTO {JOURNAL_TABLE} (version, applique_le, fichier) VALUES (?, ?, ?)",  # noqa: S608
                (version, _now(), path.name),
            )
            problems = db.integrity_problems(connection)
        except sqlite3.Error as exc:
            connection.rollback()
            raise MigrationError(f"migration {path.name} refusée : {exc}") from exc
        if problems:
            connection.rollback()
            raise MigrationError(f"migration {path.name} : intégrité refusée {problems[:3]}")
        connection.commit()
        applied.append(version)
    return applied


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="journai-migrate", description="Applique les migrations versionnées.")
    parser.add_argument("--db", dest="db_path", help="chemin de la base SQLite")
    parser.add_argument("--schema-dir", dest="schema_dir", help="répertoire des migrations .sql")
    args = parser.parse_args(argv)
    config = load_config()
    connection = db.connect(args.db_path or config.db_path)
    try:
        applied = migrate(connection, args.schema_dir or config.schema_dir)
        versions = applied_versions(connection)
        print("migrations appliquées :", ", ".join(applied) if applied else "aucune (déjà à jour)")
        print("version courante :", versions[-1] if versions else "aucune")
    except MigrationError as exc:
        print("ERREUR :", exc, file=sys.stderr)
        return 1
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
