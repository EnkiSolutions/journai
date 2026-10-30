"""Configuration du socle : aucun secret n'est stocké dans le dépôt.

Les valeurs viennent d'un fichier JSON d'exemple puis des variables d'environnement.
Convention : JOURNAI_ENV, JOURNAI_DB, JOURNAI_HOST, JOURNAI_PORT, JOURNAI_LOG_LEVEL.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ENV = "dev"
DEFAULT_DB_PATH = "var/journai.db"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_SCHEMA_DIR = "journai/migrations"


@dataclass(frozen=True)
class Config:
    """Valeurs nécessaires au démarrage, sans secret."""

    env: str
    db_path: Path
    host: str
    port: int
    log_level: str
    schema_dir: Path


def _load_file(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} doit contenir un objet JSON")
    return loaded


def load_config(config_file: str | os.PathLike[str] | None = None) -> Config:
    """Fichier d'exemple, puis variables d'environnement (priorité à l'environnement)."""
    data = _load_file(Path(config_file) if config_file else Path("config/journai.example.json"))
    env = os.environ.get("JOURNAI_ENV", str(data.get("env", DEFAULT_ENV)))
    db_path = Path(os.environ.get("JOURNAI_DB", str(data.get("db_path", DEFAULT_DB_PATH))))
    host = os.environ.get("JOURNAI_HOST", str(data.get("host", DEFAULT_HOST)))
    log_level = os.environ.get("JOURNAI_LOG_LEVEL", str(data.get("log_level", DEFAULT_LOG_LEVEL)))
    schema_dir = Path(os.environ.get("JOURNAI_SCHEMA_DIR", str(data.get("schema_dir", DEFAULT_SCHEMA_DIR))))
    port_raw = os.environ.get("JOURNAI_PORT", data.get("port", DEFAULT_PORT))
    try:
        port = int(port_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"JOURNAI_PORT invalide : {port_raw!r}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"JOURNAI_PORT hors plage : {port}")
    return Config(env, db_path, host, port, log_level, schema_dir)
