"""Migrations versionnées : chaque fichier .sql est appliqué une fois, dans l'ordre, en transaction.

Le journal schema_migration rend l'opération idempotente et donne la version courante au
démarrage. La version n'est journalisée qu'après contrôle d'intégrité : une migration qui
laisse une clé étrangère non satisfaite est annulée et la base reste à la version vérifiée.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from journai import db, validation
from journai.config import load_config

JOURNAL_TABLE = "schema_migration"


class MigrationError(RuntimeError):
    """Migration refusée : le schéma reste à la dernière version vérifiée."""


def _ensure_journal(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"CREATE TABLE IF NOT EXISTS {JOURNAL_TABLE} ("  # noqa: S608 - table de service du socle
        "version TEXT NOT NULL PRIMARY KEY, applique_le TEXT NOT NULL, fichier TEXT NOT NULL, "
        "empreinte_sha256 TEXT NOT NULL)"
    )
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({JOURNAL_TABLE})")}  # noqa: S608
    if "empreinte_sha256" not in columns:
        raise MigrationError("journal de migrations hérité sans empreinte SHA-256 vérifiable")


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
    _ensure_journal(connection)
    files = discover(schema_dir)
    paths = dict(files)
    rows = connection.execute(f"SELECT version, empreinte_sha256 FROM {JOURNAL_TABLE}")  # noqa: S608
    done = set()
    for version, digest in rows:
        if version not in paths or digest != hashlib.sha256(paths[version].read_bytes()).hexdigest():
            raise MigrationError(f"empreinte SHA-256 non vérifiable ou modifiée pour la migration {version}")
        done.add(version)
    return [(version, path) for version, path in files if version not in done]


def statements(sql: str) -> list[str]:
    """Découpe le script en instructions complètes (sqlite3.complete_statement gère quotes et commentaires)."""
    out: list[str] = []
    buffer: list[str] = []
    for char in sql:
        buffer.append(char)
        if char == ";" and sqlite3.complete_statement("".join(buffer)):
            instruction = "".join(buffer).strip()
            if re.sub(r"--[^\n]*|/\*.*?\*/", "", instruction, flags=re.DOTALL).strip(" ;\t\r\n"):
                out.append(instruction)
            buffer = []
    remainder = re.sub(r"--[^\n]*|/\*.*?\*/", "", "".join(buffer), flags=re.DOTALL)
    if remainder.strip():
        raise MigrationError("script de migration incomplet (instruction non terminée)")
    return out


def migrate(connection: sqlite3.Connection, schema_dir: str | Path) -> list[str]:
    _ensure_journal(connection)
    applied: list[str] = []
    for version, path in plan(connection, schema_dir):
        content = path.read_bytes()
        instructions = statements(content.decode("utf-8"))
        if not instructions:
            raise MigrationError(f"{path.name} ne contient aucune instruction")
        for sql in instructions:
            if re.match(r"\s*(?:(?:--[^\n]*(?:\n|$)|/\*.*?\*/)\s*)*"
                        r"(?:BEGIN|COMMIT|END|ROLLBACK|SAVEPOINT|RELEASE)\b", sql, re.I | re.S):
                raise MigrationError(f"{path.name} contient une commande de transaction interdite")
        try:
            for sql in instructions:
                connection.execute(sql)
            connection.execute(
                f"INSERT INTO {JOURNAL_TABLE} (version, applique_le, fichier, empreinte_sha256) "  # noqa: S608
                "VALUES (?, ?, ?, ?)",
                (version, _now(), path.name, hashlib.sha256(content).hexdigest()),
            )
            problems = db.integrity_problems(connection)
            if problems:
                raise MigrationError(f"migration {path.name} : intégrité refusée {problems[:3]}")
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise MigrationError(f"migration {path.name} refusée : {exc}") from exc
        except Exception:
            connection.rollback()
            raise
        applied.append(version)
    return applied


def _now() -> str:
    return validation.canonical_instant(datetime.now(timezone.utc).isoformat())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="journai-migrate", description="Applique les migrations versionnées.")
    parser.add_argument("--db", dest="db_path", help="chemin de la base SQLite")
    parser.add_argument("--schema-dir", dest="schema_dir", help="répertoire des migrations .sql")
    args = parser.parse_args(argv)
    config = load_config()
    connection = db.connect(args.db_path or config.db_path)
    try:
        schema_dir = config.schema_dir
        if args.schema_dir is not None:
            schema_dir = Path(args.schema_dir)
        applied = migrate(connection, schema_dir)
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
