import base64
import hashlib
import hmac
import http.client
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import closing
from dataclasses import replace
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from journai import db, migrations, seed
from journai.api import ApiHandler, ApiServer
from journai.config import Config

ROOT = Path(__file__).resolve().parents[1]
KEY = "synthetic-test-key-0123456789abcdef"
SPACE = "a850d82b-814e-540f-bf03-ef86588e90b9"
ADMIN = "b5c7d06a-d5aa-5527-9739-4d9bce0be0ae"
CONTRIBUTOR = "7296f48c-4748-53f3-a73c-6847fa3c9ed8"
PROJECT_A = "d433b0ab-5208-520a-8068-b00950d5f467"
PROJECT_B = "028ef5b1-354b-5ca3-b352-b177b47a4852"
SHARED = "36462979-914f-5bee-893a-0984f319c5f2"
PRIVATE = "ef35cbd0-a577-5482-a098-6abdd628cb28"
ORIGIN = "https://example.test"


def token(user=ADMIN, space=SPACE, *, iat=None, exp=None, key=KEY):
    now = int(time.time())
    payload = json.dumps({"sub": user, "espace_id": space, "iat": now - 5 if iat is None else iat,
                          "exp": now + 300 if exp is None else exp}, separators=(",", ":")).encode()
    encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip("=")
    signed = "v1." + encode(payload)
    return signed + "." + encode(hmac.digest(key.encode(), signed.encode(), hashlib.sha256))


class RejectedBodyTests(unittest.TestCase):
    def test_rejections_close_before_response_without_reading_body(self):
        rejected_headers = (
            [("Content-Length", "1")],
            [("Content-Length", "0"), ("Content-Length", "0")],
            [("Transfer-Encoding", "chunked")],
            [("Cookie", "synthetic=value")],
        )
        cases = [(method, headers, 400) for method in ("GET", "HEAD", "OPTIONS")
                 for headers in rejected_headers]
        cases += [(method, headers, 405) for method in ("POST", "PUT", "CUSTOM")
                  for headers in ([], [("Content-Length", "1")], [("Transfer-Encoding", "chunked")])]
        for method, headers, status in cases:
            with self.subTest(method=method, headers=headers):
                handler = object.__new__(ApiHandler)
                handler.command = method
                handler.headers = Message()
                for name, value in headers:
                    handler.headers.add_header(name, value)
                handler.server = SimpleNamespace(config=SimpleNamespace(cors_origin=""))
                handler.close_connection = False
                handler.rfile = Mock()
                handler.wfile = io.BytesIO()
                handler.send_response = Mock(side_effect=lambda code: self.assertTrue(handler.close_connection))
                handler.send_header = Mock()
                handler.end_headers = Mock()
                getattr(handler, "do_" + method)()
                handler.send_response.assert_called_once_with(status)
                handler.rfile.read.assert_not_called()
                if status == 405:
                    self.assertIn(call("Allow", "GET, HEAD, OPTIONS"), handler.send_header.call_args_list)
                if method == "HEAD":
                    self.assertEqual(handler.wfile.getvalue(), b"")


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test.db"
        with closing(db.connect(self.path)) as connection:
            migrations.migrate(connection, ROOT / "journai/migrations")
            seed.seeded(connection, ROOT / "journai/fixtures", env="test")
        self.config = Config("test", self.path, "127.0.0.1", 0, "INFO", Path("."), ORIGIN)
        with patch.dict(os.environ, {"JOURNAI_JETON_DEV": KEY}):
            self.server = ApiServer(self.config)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.auth = "Bearer " + token()

    def stop_server(self):
        try:
            self.server.shutdown()
        finally:
            self.server.server_close()
            self.thread.join(timeout=3)
        self.assertFalse(self.thread.is_alive())

    def request(self, path, *, method="GET", auth=True, headers=(), body=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        try:
            connection.putrequest(method, path)
            if auth:
                connection.putheader("Authorization", self.auth)
            for name, value in headers:
                connection.putheader(name, value)
            if body is not None:
                connection.putheader("Content-Length", str(len(body)))
            connection.endheaders(body)
            response = connection.getresponse()
            data = response.read()
            return response.status, dict(response.getheaders()), data
        finally:
            connection.close()

    def get_json(self, path, **kwargs):
        status, headers, body = self.request(path, **kwargs)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        return status, headers, json.loads(body)

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as connection:
            return list(connection.iterdump())

    def test_internal_errors_are_logged_without_sensitive_data(self):
        secret = "synthetic-sensitive-data"
        with self.assertLogs("journai.api", level="ERROR") as logs:
            self.assertEqual(self.request("/api/v1/projet?private=" + secret, auth=False)[0], 401)
            with patch("journai.api.read", side_effect=ValueError(secret)):
                status, _, body = self.request("/api/v1/projet?private=" + secret,
                                               headers=[("X-Synthetic", secret)])
            try:
                raise RuntimeError(secret)
            except RuntimeError:
                self.server.handle_error(None, (secret, 123))
        self.assertEqual(status, 500)
        self.assertEqual(json.loads(body)["error"]["code"], "erreur_interne")
        self.assertEqual(logs.output, [
            "ERROR:journai.api:Erreur interne HTTP : ValueError",
            "ERROR:journai.api:Erreur interne HTTP : RuntimeError"])
        self.assertNotIn(secret, body.decode())
        self.assertNotIn(self.auth, " ".join(logs.output))

    def test_persistent_connection_does_not_block_another_client(self):
        with closing(http.client.HTTPConnection(*self.server.server_address, timeout=1)) as first:
            first.request("GET", "/api/v1/projet", headers={"Authorization": self.auth})
            response = first.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            self.assertFalse(response.will_close)
            self.assertIsNotNone(first.sock)
            with closing(http.client.HTTPConnection(*self.server.server_address, timeout=1)) as second:
                second.request("GET", "/api/v1/projet", headers={"Authorization": self.auth})
                response = second.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
            first.request("GET", "/api/v1/projet", headers={"Authorization": self.auth})
            response = first.getresponse()
            self.assertEqual(response.status, 200)
            response.read()

    def test_scoped_list_detail_inclusion_and_etags(self):
        status, headers, payload = self.get_json("/api/v1/projet?limit=1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["meta"]["total"], 1)
        self.assertEqual([row["id"] for row in payload["data"]], [PROJECT_A])
        self.assertNotIn("ETag", headers)
        status, headers, payload = self.get_json(f"/api/v1/projet/{PROJECT_A}?include=parcours")
        self.assertEqual(status, 200)
        self.assertEqual(headers["ETag"], f'"{PROJECT_A}@{payload["data"]["revision"]}"')
        self.assertTrue(payload["included"]["parcours"])
        self.assertTrue(all(row["projet_id"] == PROJECT_A for row in payload["included"]["parcours"]))
        status, _, payload = self.get_json(f"/api/v1/action/{SHARED}?include=action_projet")
        self.assertEqual(status, 200)
        self.assertEqual([row["projet_id"] for row in payload["included"]["action_projet"]], [PROJECT_A])
        self.assertEqual(payload["included_meta"]["action_projet"]["total"], 1)
        status, _, empty = self.get_json(f"/api/v1/action/{PRIVATE}?include=action_constat")
        self.assertEqual(status, 200)
        self.assertEqual(empty["included"]["action_constat"], [])
        self.assertEqual(empty["included_meta"]["action_constat"], {
            "ressource": "action_constat", "total": 0, "limit": 500, "offset": 0, "espace_id": SPACE})
        status, headers, payload = self.get_json("/api/v1/parcours_public")
        self.assertEqual(status, 200)
        self.assertGreater(payload["meta"]["total"], 0)
        self.assertNotIn("ETag", headers)
        self.assertNotIn("id", payload["data"][0])
        self.assertNotIn("revision", payload["data"][0])
        self.assertEqual(self.get_json("/api/v1/parcours_public/anything")[0], 404)
        self.assertEqual(self.get_json(f"/api/v1/projet/{PROJECT_B}")[0], 403)
        self.assertEqual(self.get_json(f"/api/v1/parcours?projet_id={PROJECT_B}")[0], 403)
        self.auth = "Bearer " + token(CONTRIBUTOR)
        self.assertEqual(self.get_json("/api/v1/projet?limit=1")[2]["meta"]["total"], 2)

    def test_included_pagination_and_continuation_over_http(self):
        with closing(db.connect(self.path)) as connection:
            source = connection.execute("SELECT id FROM parcours WHERE projet_id=?", (PROJECT_A,)).fetchone()[0]
            foreign = connection.execute("SELECT id FROM parcours WHERE espace_id<>?", (SPACE,)).fetchone()[0]
            sql = """INSERT INTO parcours (id, espace_id, projet_id, nom, finalite, responsable_id, cree_par, cree_le)
                     SELECT ?, espace_id, projet_id, nom, finalite, responsable_id, cree_par, cree_le FROM parcours WHERE id=?"""
            connection.executemany(sql, ((f"99999999-0000-4000-8000-{i:012d}", source) for i in range(501)))
            connection.execute(sql, ("88888888-0000-4000-8000-000000000001", foreign))
            connection.commit()
        status, _, result = self.get_json(f"/api/v1/projet/{PROJECT_A}?include=parcours")
        self.assertEqual(status, 200)
        meta = result["included_meta"]["parcours"]
        self.assertEqual(meta, {"ressource": "parcours", "total": 502, "limit": 500, "offset": 0, "espace_id": SPACE})
        first = result["included"]["parcours"]
        self.assertEqual(len(first), 500)
        status, _, rest = self.get_json(f"/api/v1/parcours?projet_id={PROJECT_A}&limit={meta['limit']}&offset={meta['offset'] + meta['limit']}")
        self.assertEqual(status, 200)
        self.assertEqual(rest["meta"]["total"], 502)
        self.assertEqual(len(rest["data"]), 2)
        self.assertTrue(all(row["espace_id"] == SPACE and row["projet_id"] == PROJECT_A for row in first + rest["data"]))
        self.assertFalse({row["id"] for row in first} & {row["id"] for row in rest["data"]})
        self.assertNotIn(foreign, {row["id"] for row in first + rest["data"]})

    def test_head_auth_and_errors_do_not_change_data(self):
        before = self.snapshot()
        url = f"/api/v1/projet/{PROJECT_A}"
        status, get_headers, _ = self.request(url)
        self.assertEqual(status, 200)
        status, head_headers, body = self.request(url, method="HEAD")
        self.assertEqual((status, body), (200, b""))
        for key in ("Content-Type", "Content-Length", "ETag"):
            self.assertEqual(head_headers[key], get_headers[key])
        self.assertEqual(self.request(url, method="HEAD", auth=False)[0], 401)
        self.assertEqual(self.request(f"/api/v1/projet/{PROJECT_B}", method="HEAD")[0], 403)
        for path, expected in (("/api/v1/action?limit=0", 400), ("/api/v1/action?sens=ASC", 400),
                               ("/api/v1/action?limit=1&limit=2", 400),
                               ("/api/v1/action?x=%ZZ", 400), ("/api/v1/nonexistent", 404),
                               ("/other/action", 404), ("/api/v1/schema_migration", 404),
                               ("/api/v1/projet?espace_id=other", 403)):
            with self.subTest(path=path):
                self.assertEqual(self.get_json(path)[0], expected)
        self.assertEqual(self.get_json(url, headers=[("X-Espace-Id", "other")])[0], 403)
        self.assertEqual(self.get_json(url, headers=[("X-Espace-Id", SPACE), ("X-Espace-Id", SPACE)])[0], 400)
        self.assertEqual(self.get_json(url, headers=[("X-Role", "administrateur")])[0], 400)
        self.assertEqual(self.get_json(url, headers=[("Cookie", "token=secret")])[0], 400)
        self.assertEqual(self.get_json(url, body=b"secret")[0], 400)
        for method in ("POST", "PUT", "PATCH", "DELETE", "TRACE", "CUSTOM"):
            with self.subTest(method=method):
                status, headers, _ = self.get_json(url, method=method, body=b"secret")
                self.assertEqual(status, 405)
                self.assertEqual(headers["Allow"], "GET, HEAD, OPTIONS")
        self.assertEqual(self.snapshot(), before)

    def test_authentication_cors_and_no_leaks(self):
        path = "/api/v1/projet"
        self.assertEqual(self.get_json(path, auth=False)[0], 401)
        self.assertEqual(self.get_json("/api/v1/unknown", auth=False, headers=[("Authorization", "Bearer invalid")])[0], 401)
        self.assertEqual(self.get_json(path, headers=[("Authorization", self.auth)])[0], 401)
        self.assertEqual(self.get_json(path + "?token=" + token(), auth=False)[0], 401)
        for value in ("Bearer invalid", "Basic abc", "Bearer " + token(key="different-synthetic-key"),
                      "Bearer " + token(iat=int(time.time()) - 20, exp=int(time.time()) - 1),
                      "Bearer " + token(iat=int(time.time()) + 100)):
            status, _, body = self.request(path, auth=False, headers=[("Authorization", value)])
            self.assertEqual(status, 401)
            self.assertNotIn(value.encode(), body)
            self.assertNotIn(KEY.encode(), body)
        for origin, allowed in ((ORIGIN, True), ("https://evil.test", False), ("null", False)):
            for method in ("GET", "OPTIONS"):
                status, headers, body = self.request(path, method=method, auth=method != "OPTIONS",
                                                     headers=[("Origin", origin)])
                self.assertEqual(status, 200)
                self.assertEqual(headers.get("Access-Control-Allow-Origin"), origin if allowed else None)
                self.assertEqual(headers.get("Access-Control-Expose-Headers"), "ETag" if allowed else None)
                self.assertEqual(headers["Vary"], "Origin")
                if method == "OPTIONS":
                    self.assertEqual(body, b"")
                    if allowed:
                        self.assertEqual(headers["Access-Control-Allow-Headers"], "Authorization")
        status, headers, payload = self.get_json(f"/api/v1/projet/{PROJECT_A}", headers=[("Origin", ORIGIN)])
        self.assertEqual(status, 200)
        self.assertEqual(headers["ETag"], f'"{PROJECT_A}@{payload["data"]["revision"]}"')
        self.assertEqual(headers["Access-Control-Expose-Headers"], "ETag")
        self.server.config = replace(self.config, cors_origin="")
        status, headers, _ = self.get_json(f"/api/v1/projet/{PROJECT_A}", headers=[("Origin", ORIGIN)])
        self.assertEqual(status, 200)
        self.assertIn("ETag", headers)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertNotIn("Access-Control-Expose-Headers", headers)
        self.server.config = self.config
        self.assertEqual(self.get_json(path, headers=[("Origin", ORIGIN), ("Origin", ORIGIN)])[0], 400)
        secret = "v1.secret.signature"
        status, _, body = self.request(path + "?" + secret + "=x")
        self.assertEqual(status, 400)
        self.assertNotIn(secret.encode(), body)

    def test_membership_changes_and_space_switch(self):
        with closing(sqlite3.connect(self.path)) as connection:
            foreign_user, foreign_space = connection.execute(
                "SELECT utilisateur_id, espace_id FROM membre_espace WHERE espace_id != ? AND statut='actif' LIMIT 1", (SPACE,)).fetchone()
            connection.execute("UPDATE membre_espace SET statut='inactif' WHERE utilisateur_id=? AND espace_id=?", (ADMIN, SPACE))
            connection.commit()
        self.assertEqual(self.get_json("/api/v1/projet")[0], 403)
        self.auth = "Bearer " + token(foreign_user, foreign_space)
        status, _, payload = self.get_json("/api/v1/projet")
        self.assertEqual(status, 200)
        self.assertTrue(payload["data"])
        self.assertTrue(all(row["espace_id"] == foreign_space for row in payload["data"]))
        self.assertEqual(self.get_json(f"/api/v1/action/{SHARED}")[0], 404)
        self.assertEqual(self.get_json(f"/api/v1/espace/{SPACE}")[0], 403)
        self.assertEqual(self.get_json(f"/api/v1/espace?espace_id={SPACE}")[0], 403)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE utilisateur SET statut='suspendu' WHERE id=?", (foreign_user,))
            connection.commit()
        self.assertEqual(self.get_json("/api/v1/projet")[0], 401)

    def test_shared_action_masks_other_project_and_internal_error(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("DELETE FROM membre_projet WHERE utilisateur_id=? AND projet_id=?", (ADMIN, PROJECT_A))
            connection.execute("INSERT INTO membre_projet (projet_id, utilisateur_id, espace_id, role) VALUES (?, ?, ?, 'lecteur')", (PROJECT_B, ADMIN, SPACE))
            connection.commit()
        status, _, result = self.get_json(f"/api/v1/action/{SHARED}?include=action_projet")
        self.assertEqual(status, 200)
        self.assertIsNone(result["data"]["projet_pilote_id"])
        self.assertEqual([row["projet_id"] for row in result["included"]["action_projet"]], [PROJECT_B])
        self.assertEqual(self.get_json(f"/api/v1/action_operation?action_id={SHARED}")[2]["meta"]["total"], 0)
        before = self.snapshot()
        with patch("journai.api.read", side_effect=RuntimeError("secret interne")):
            status, _, body = self.request("/api/v1/action")
        self.assertEqual(status, 500)
        self.assertNotIn(b"secret interne", body)
        self.assertNotIn(b"Traceback", body)
        self.assertEqual(self.snapshot(), before)


class ServeStartupTests(unittest.TestCase):
    def test_refusals_before_database_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.db"
            base = {key: value for key, value in os.environ.items() if not key.startswith("JOURNAI_")}
            base.update(PYTHONPATH=str(ROOT), JOURNAI_DB=str(path))
            for extra in ({}, {"JOURNAI_JETON_DEV": "short"},
                          {"JOURNAI_JETON_DEV": KEY, "JOURNAI_ENV": "staging"},
                          {"JOURNAI_JETON_DEV": KEY, "JOURNAI_ENV": "prod"},
                          {"JOURNAI_JETON_DEV": KEY, "JOURNAI_CORS_ORIGIN": "*"}):
                result = subprocess.run([sys.executable, "-m", "journai", "serve"], cwd=directory,
                                        env={**base, **extra}, capture_output=True, text=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ERREUR", result.stderr)
                self.assertNotIn(KEY, result.stdout + result.stderr)
                self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
