"""Authentification de démonstration F01, réservée aux environnements locaux."""

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass

from journai.config import Config
from journai.validation import canonical_uuid


class AuthError(Exception):
    def __init__(self, status: int):
        self.status = status
        super().__init__("Authentification refusée" if status == 401 else "Accès refusé")


@dataclass(frozen=True)
class AuthContext:
    utilisateur_id: str
    espace_id: str


def _decode(segment: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", segment):
        raise ValueError("encodage invalide")
    decoded = base64.b64decode(segment + "=" * (-len(segment) % 4), altchars=b"-_", validate=True)
    if base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != segment:
        raise ValueError("encodage non canonique")
    return decoded


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("clé dupliquée")
        result[key] = value
    return result


class DemoAuth:
    def __init__(self, config: Config):
        if config.env not in {"dev", "test"}:
            raise ValueError("Authentification de démonstration interdite dans cet environnement")
        key = os.environ.get("JOURNAI_JETON_DEV", "")
        if not key.isascii() or len(key) < 32:
            raise ValueError("Clé de démonstration absente ou invalide")
        self._key = key.encode("ascii")

    def authenticate(self, connection: sqlite3.Connection, authorization: str | None, *,
                     espace_id: str | None = None, maintenant: int | None = None) -> AuthContext:
        try:
            if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
                raise ValueError("transport invalide")
            parts = authorization[7:].split(".")
            if len(parts) != 3 or parts[0] != "v1":
                raise ValueError("format invalide")
            payload_bytes = _decode(parts[1])
            signature = _decode(parts[2])
            expected = hmac.digest(self._key, f"v1.{parts[1]}".encode("ascii"), hashlib.sha256)
            if not hmac.compare_digest(signature, expected):
                raise ValueError("signature invalide")
            payload = json.loads(payload_bytes.decode("utf-8"), object_pairs_hook=_object)
            if not isinstance(payload, dict) or set(payload) != {"sub", "espace_id", "iat", "exp"}:
                raise ValueError("revendications invalides")
            utilisateur_id = canonical_uuid(payload["sub"])
            signed_space = canonical_uuid(payload["espace_id"])
            iat, exp = payload["iat"], payload["exp"]
            now = time.time() if maintenant is None else maintenant
            if (type(iat) is not int or type(exp) is not int or
                    not 0 <= iat <= now < exp or exp - iat > 3600):
                raise ValueError("dates invalides")
        except (ValueError, TypeError, UnicodeError, binascii.Error, RecursionError):
            raise AuthError(401) from None

        user = connection.execute("SELECT 1 FROM utilisateur WHERE id = ? AND statut = 'actif'",
                                  (utilisateur_id,)).fetchone()
        if user is None:
            raise AuthError(401)
        membership = connection.execute(
            "SELECT 1 FROM membre_espace WHERE utilisateur_id = ? AND espace_id = ? AND statut = 'actif'",
            (utilisateur_id, signed_space),
        ).fetchone()
        if membership is None or (espace_id is not None and espace_id != signed_space):
            raise AuthError(403)
        return AuthContext(utilisateur_id, signed_space)
