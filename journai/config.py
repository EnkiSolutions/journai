"""Configuration du socle : aucun secret n'est stocké dans le dépôt.

Priorité : défauts, exemple JSON, copie locale ou fichier explicite, environnement.
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
DEFAULT_CORS_ORIGIN = ""


@dataclass(frozen=True)
class Config:
    """Valeurs nécessaires au démarrage, sans secret."""

    env: str
    db_path: Path
    host: str
    port: int
    log_level: str
    schema_dir: Path
    cors_origin: str


def _load_file(path: Path, *, optional: bool = False) -> dict[str, object]:
    try:
        with path.open(encoding="utf-8") as handle:
            loaded = json.load(handle)
    except FileNotFoundError:
        if optional:
            return {}
        raise
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} doit contenir un objet JSON")
    return loaded


def load_config(config_file: str | os.PathLike[str] | None = None) -> Config:
    """Charger l'exemple, la configuration locale, puis l'environnement."""
    data = _load_file(Path("config/journai.example.json"), optional=True)
    local = Path(config_file) if config_file is not None else Path("config/journai.json")
    data.update(_load_file(local, optional=config_file is None))
    env = os.environ.get("JOURNAI_ENV", str(data.get("env", DEFAULT_ENV)))
    if env not in {"dev", "test", "staging", "prod"}:
        raise ValueError(f"JOURNAI_ENV invalide : {env!r}")
    db_raw = os.environ.get("JOURNAI_DB", data.get("db", DEFAULT_DB_PATH))
    if not isinstance(db_raw, str):
        raise ValueError("db doit être un chemin textuel")
    db_path = Path(db_raw)
    host = os.environ.get("JOURNAI_HOST", str(data.get("host", DEFAULT_HOST)))
    log_level = os.environ.get("JOURNAI_LOG_LEVEL", str(data.get("log_level", DEFAULT_LOG_LEVEL)))
    schema_raw = os.environ.get("JOURNAI_SCHEMA_DIR", data.get("schema_dir", DEFAULT_SCHEMA_DIR))
    if not isinstance(schema_raw, str):
        raise ValueError("schema_dir doit être un chemin textuel")
    schema_dir = Path(schema_raw)
    cors_origin = os.environ.get("JOURNAI_CORS_ORIGIN", str(data.get("cors_origin", DEFAULT_CORS_ORIGIN)))
    port_raw = os.environ.get("JOURNAI_PORT", data.get("port", DEFAULT_PORT))
    try:
        if isinstance(port_raw, bool) or not isinstance(port_raw, (str, int)):
            raise ValueError("le port doit être entier")
        port = int(port_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"JOURNAI_PORT invalide : {port_raw!r}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"JOURNAI_PORT hors plage : {port}")
    return Config(env, db_path, host, port, log_level, schema_dir, cors_origin)
