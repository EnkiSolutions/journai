"""Commandes locales de migration, semis et consultation du socle."""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

from journai import db, migrations, seed
from journai.config import DEFAULT_SCHEMA_DIR, load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="journai", description="Socle local JournAI")
    parser.add_argument("--config", help="fichier JSON de configuration")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("init", help="appliquer les migrations")
    seed_parser = commands.add_parser("seed", help="charger les fixtures synthétiques")
    seed_parser.add_argument("--replace", action="store_true", help="remplacer les données des fixtures")
    commands.add_parser("status", help="afficher les versions et les totaux par table")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        level = logging.getLevelNamesMapping().get(config.log_level.upper())
        if not isinstance(level, int):
            raise ValueError("niveau de journalisation invalide")
        logging.basicConfig(stream=sys.stdout, level=level, format="%(asctime)s %(levelname)s %(message)s")
        schema_dir = config.schema_dir
        if schema_dir == Path(DEFAULT_SCHEMA_DIR):
            schema_dir = Path(migrations.__file__).parent / "migrations"

        if args.command == "status":
            # La lecture ne crée ni base ni journal et ne modifie pas le mode SQLite.
            connection = sqlite3.connect(config.db_path.resolve().as_uri() + "?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
        else:
            connection = db.connect(config.db_path)
        try:
            if args.command in (None, "init"):
                applied = migrations.migrate(connection, schema_dir)
                logging.info("Migrations appliquées : %s", ", ".join(applied) or "aucune")
            if args.command in (None, "seed"):
                counts = seed.seeded(connection, env=config.env, replace=getattr(args, "replace", False),
                                     allow_replace=getattr(args, "replace", False))
                logging.info("Fixtures insérées : %s", ", ".join(f"{table}={count}" for table, count in counts.items()))
            if args.command == "status":
                tables = db.table_names(connection)
                if migrations.JOURNAL_TABLE not in tables:
                    raise migrations.MigrationError("base non migrée : lancer journai init")
                versions = migrations.applied_versions(connection)
                print("Versions :", ", ".join(versions) or "aucune")
                for table in tables:
                    quoted = '"' + table.replace('"', '""') + '"'
                    count = connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
                    print(f"{table}: {count}")
        finally:
            connection.close()
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        print(f"ERREUR : {exc}", file=sys.stderr)
        return 1
    return 0
