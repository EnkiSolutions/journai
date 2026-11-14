"""Commandes locales de migration, semis et consultation du socle."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import http.client
import json
import logging
import os
import secrets
import sqlite3
import sys
import tempfile
import threading
import time
from contextlib import closing
from pathlib import Path

from journai import db, migrations, seed
from journai.config import Config, DEFAULT_SCHEMA_DIR, load_config


def selftest() -> None:
    """Vérifier la chaîne de lecture sur des ressources synthétiques isolées."""
    from journai.api import ApiServer

    temporary_root = Path(tempfile.gettempdir()).resolve()
    for start in (Path.cwd().resolve(), Path(__file__).resolve().parent):
        for parent in (start, *start.parents):
            if (parent / ".git").exists() and temporary_root.is_relative_to(parent):
                raise RuntimeError("Le répertoire temporaire doit être hors du dépôt")
    with tempfile.TemporaryDirectory(prefix="journai-selftest-", dir=temporary_root) as directory:
        path = Path(directory) / "selftest.db"
        with closing(db.connect(path)) as connection:
            migrations.migrate(connection, Path(migrations.__file__).parent / "migrations")
            seed.seeded(connection, env="test")
        config = Config("test", path, "127.0.0.1", 0, "WARNING", Path("."), "")
        key = secrets.token_hex(32)
        previous = os.environ.get("JOURNAI_JETON_DEV")
        try:
            os.environ["JOURNAI_JETON_DEV"] = key
            server = ApiServer(config)
        finally:
            if previous is None:
                os.environ.pop("JOURNAI_JETON_DEV", None)
            else:
                os.environ["JOURNAI_JETON_DEV"] = previous
        now = int(time.time())
        payload = json.dumps({"sub": "b5c7d06a-d5aa-5527-9739-4d9bce0be0ae",
                              "espace_id": "a850d82b-814e-540f-bf03-ef86588e90b9",
                              "iat": now, "exp": now + 300}, separators=(",", ":")).encode()
        encode = lambda value: base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
        signed = "v1." + encode(payload)
        token = signed + "." + encode(hmac.digest(key.encode(), signed.encode(), hashlib.sha256))
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        try:
            thread.start()
            for path, authorization, expected in (
                ("/api/v1/projet", "Bearer " + token, 200),
                ("/api/v1/projet", None, 401),
                ("/api/v1/projet", "Bearer invalid", 401),
                ("/api/v1/projet/028ef5b1-354b-5ca3-b352-b177b47a4852", "Bearer " + token, 403),
            ):
                with closing(http.client.HTTPConnection(*server.server_address, timeout=3)) as client:
                    client.request("GET", path, headers={"Authorization": authorization} if authorization else {})
                    response = client.getresponse()
                    body = response.read()
                    if response.status != expected or (expected == 200 and not json.loads(body).get("data")):
                        raise RuntimeError("Échec de la vérification HTTP du selftest")
        finally:
            if thread.ident is not None:
                server.shutdown()
                thread.join()
            server.server_close()
    print("Selftest réussi")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="journai", description="Socle local JournAI")
    parser.add_argument("--config", help="fichier JSON de configuration")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("init", help="appliquer les migrations")
    seed_parser = commands.add_parser("seed", help="charger les fixtures synthétiques")
    seed_parser.add_argument("--replace", action="store_true", help="remplacer les données des fixtures")
    commands.add_parser("status", help="afficher les versions et les totaux par table")
    commands.add_parser("serve", help="servir l'API de lecture locale")
    commands.add_parser("selftest", help="vérifier la chaîne sur une base temporaire")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        level = logging.getLevelNamesMapping().get(config.log_level.upper())
        if not isinstance(level, int):
            raise ValueError("niveau de journalisation invalide")
        logging.basicConfig(stream=sys.stdout, level=level, format="%(asctime)s %(levelname)s %(message)s")
        if args.command == "selftest":
            selftest()
            return 0
        if args.command == "serve":
            from journai.api import serve
            serve(config)
            return 0
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
