import base64
import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from journai import db, migrations, seed
from journai.auth import AuthContext, AuthError, DemoAuth
from journai.config import Config


KEY = "synthetic-test-key-0123456789abcdef"
USER = "11111111-1111-4111-8111-111111111111"
SPACE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
NOW = 1700000000
CONFIG = Config("test", Path(":memory:"), "localhost", 8000, "INFO", Path("."), "")


def b64(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def token(payload, key=KEY):
    if not isinstance(payload, bytes):
        payload = json.dumps(payload, separators=(",", ":")).encode()
    signed = "v1." + b64(payload)
    return signed + "." + b64(hmac.digest(key.encode(), signed.encode(), hashlib.sha256))


class AuthTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"JOURNAI_JETON_DEV": KEY}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.auth = DemoAuth(CONFIG)
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE utilisateur (id TEXT PRIMARY KEY, statut TEXT);
            CREATE TABLE membre_espace (utilisateur_id TEXT, espace_id TEXT, statut TEXT);
        """)
        self.db.execute("INSERT INTO utilisateur VALUES (?, 'actif')", (USER,))
        self.db.execute("INSERT INTO membre_espace VALUES (?, ?, 'actif')", (USER, SPACE))
        self.claims = {"sub": USER, "espace_id": SPACE, "iat": NOW - 10, "exp": NOW + 10}

    def authenticate(self, value, **kwargs):
        return self.auth.authenticate(self.db, value, maintenant=NOW, **kwargs)

    def denied(self, value, status=401, **kwargs):
        with self.assertRaises(AuthError) as caught:
            self.authenticate(value, **kwargs)
        self.assertEqual(caught.exception.status, status)
        self.assertNotIn(KEY, str(caught.exception))
        if isinstance(value, str) and value:
            self.assertNotIn(value, str(caught.exception))

    def test_valid_and_space_switch(self):
        value = "Bearer " + token(self.claims)
        self.assertEqual(self.authenticate(value), AuthContext(USER, SPACE))
        self.assertEqual(self.authenticate(value, espace_id=SPACE), AuthContext(USER, SPACE))
        self.denied(value, 403, espace_id=OTHER)
        self.db.execute("INSERT INTO membre_espace VALUES (?, ?, 'actif')", (USER, OTHER))
        other_token = "Bearer " + token({**self.claims, "espace_id": OTHER})
        self.assertEqual(self.authenticate(other_token), AuthContext(USER, OTHER))

    def test_signed_original_json_bytes(self):
        payload = json.dumps(self.claims, indent=2).encode()
        signed = token(payload)
        self.assertEqual(self.authenticate("Bearer " + signed), AuthContext(USER, SPACE))
        _, _, signature = signed.split(".")
        modified = b64(json.dumps(self.claims, separators=(",", ":")).encode())
        self.denied("Bearer v1." + modified + "." + signature)

    def test_real_migrations_and_fixtures(self):
        root = Path(__file__).resolve().parents[1] / "journai"
        with tempfile.TemporaryDirectory() as directory:
            connection = db.connect(Path(directory) / "auth.db")
            try:
                migrations.migrate(connection, root / "migrations")
                seed.seeded(connection, root / "fixtures", env="test")
                user, space = connection.execute(
                    "SELECT utilisateur_id, espace_id FROM membre_espace WHERE statut = 'actif' LIMIT 1"
                ).fetchone()
                value = "Bearer " + token({**self.claims, "sub": user, "espace_id": space})
                self.assertEqual(self.auth.authenticate(connection, value, maintenant=NOW),
                                 AuthContext(user, space))
            finally:
                connection.close()

    def test_bad_transport_format_signature_and_encoding(self):
        good = token(self.claims)
        version, payload, signature = good.split(".")
        invalid = [None, "", good, "Basic " + good, "Bearer  " + good,
                   "Bearer " + good + " ", "Bearer v2." + payload + "." + signature,
                   "Bearer " + good + ".extra", "Bearer v1.." + signature,
                   "Bearer v1." + payload + "=." + signature,
                   "Bearer v1." + payload + "." + signature + "=",
                   "Bearer v1." + payload + "." + signature[:-1] + "!",
                   "Bearer " + token(self.claims, key="another-synthetic-key-0123456789"),
                   "Bearer v1." + b64(b"different") + "." + signature,
                   "Bearer v1." + payload + "." + b64(bytes(32))]
        for value in invalid:
            with self.subTest(value=value):
                self.denied(value)
        # Last base64url character with altered unused pad bits must not be accepted.
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        noncanonical = signature[:-1] + alphabet[alphabet.index(signature[-1]) ^ 1]
        self.denied("Bearer v1." + payload + "." + noncanonical)

    def test_bad_json_claims_and_uuids(self):
        bad_payloads = [b"\xff", b"{", b"[]", b"null", b'{"sub":1,"sub":2}',
                        json.dumps({**self.claims, "espace_id": SPACE.upper()}).encode(),
                        json.dumps({**self.claims, "espace_id": "{" + SPACE + "}"}).encode(),
                        json.dumps({**self.claims, "sub": 1}).encode(),
                        json.dumps({**self.claims, "role": "administrateur"}).encode(),
                        json.dumps({k: v for k, v in self.claims.items() if k != "sub"}).encode()]
        duplicate = json.dumps(self.claims)[:-1] + ', "sub": "' + USER + '"}'
        bad_payloads.append(duplicate.encode())
        for payload in bad_payloads:
            with self.subTest(payload=payload):
                self.denied("Bearer " + token(payload))

    def test_dates_strict_and_boundaries(self):
        for iat, exp in [(0, 3600), (NOW, NOW + 3600), (NOW - 3600, NOW)]:
            claims = {**self.claims, "iat": iat, "exp": exp}
            if iat <= NOW < exp and exp - iat <= 3600:
                self.authenticate("Bearer " + token(claims))
            else:
                self.denied("Bearer " + token(claims))
        for iat, exp in [(-1, NOW + 1), (NOW + 1, NOW + 2), (NOW - 1, NOW),
                         (NOW, NOW), (NOW - 1, NOW + 3600), (True, NOW + 1),
                         (NOW, False), (float(NOW), NOW + 1), (NOW, str(NOW + 1)),
                         (None, NOW + 1)]:
            with self.subTest(iat=iat, exp=exp):
                self.denied("Bearer " + token({**self.claims, "iat": iat, "exp": exp}))

    def test_identity_and_membership_reloaded(self):
        value = "Bearer " + token(self.claims)
        self.authenticate(value)
        self.db.execute("UPDATE utilisateur SET statut = 'inactif'")
        self.denied(value)
        self.db.execute("UPDATE utilisateur SET statut = 'actif'")
        self.db.execute("UPDATE membre_espace SET statut = 'inactif'")
        self.denied(value, 403)
        self.db.execute("DELETE FROM membre_espace")
        self.denied(value, 403)
        self.db.execute("DELETE FROM utilisateur")
        self.denied(value)

    def test_environment_and_key_refused_without_leaking(self):
        for env in ("staging", "prod", "unknown"):
            with self.subTest(env=env), self.assertRaises(ValueError) as caught:
                DemoAuth(replace(CONFIG, env=env))
            self.assertNotIn(KEY, str(caught.exception))
        for key in ("", "a" * 31, "é" * 32):
            with self.subTest(key=key), patch.dict(os.environ, {"JOURNAI_JETON_DEV": key}):
                with self.assertRaises(ValueError) as caught:
                    DemoAuth(CONFIG)
                if key:
                    self.assertNotIn(key, str(caught.exception))
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            DemoAuth(CONFIG)
        with patch.dict(os.environ, {"JOURNAI_JETON_DEV": "x" * 32}):
            DemoAuth(replace(CONFIG, env="dev"))


if __name__ == "__main__":
    unittest.main()
