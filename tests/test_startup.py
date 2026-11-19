import base64
import hashlib
import hmac
import http.client
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KEY = "startup-synthetic-key-0123456789abcdef"
SPACE = "a850d82b-814e-540f-bf03-ef86588e90b9"
ADMIN = "b5c7d06a-d5aa-5527-9739-4d9bce0be0ae"
PROJECT = "d433b0ab-5208-520a-8068-b00950d5f467"
OTHER_PROJECT = "028ef5b1-354b-5ca3-b352-b177b47a4852"


def token(user=ADMIN, space=SPACE):
    now = int(time.time())
    payload = json.dumps({"sub": user, "espace_id": space, "iat": now - 1, "exp": now + 300}).encode()
    encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip("=")
    signed = "v1." + encode(payload)
    return signed + "." + encode(hmac.digest(KEY.encode(), signed.encode(), hashlib.sha256))


class StartupTests(unittest.TestCase):
    def test_documented_startup_and_http(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "configured.db"
            env = {k: v for k, v in os.environ.items() if not k.startswith("JOURNAI_")}
            env.update(PYTHONPATH=str(ROOT), PYTHONUTF8="1", JOURNAI_DB=str(database),
                       TEMP=directory, TMP=directory, TMPDIR=directory)
            command = [sys.executable, "-m", "journai"]
            for action in ("init", "seed", "status"):
                result = subprocess.run([*command, action], cwd=root, env=env, capture_output=True,
                                        text=True, encoding="utf-8", timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
            with closing(sqlite3.connect(database)) as connection:
                before = list(connection.iterdump())
            result = subprocess.run([*command, "selftest"], cwd=root, env=env, capture_output=True,
                                    text=True, encoding="utf-8", timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Selftest réussi", result.stdout)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(before, list(connection.iterdump()))
            self.assertFalse(list(root.glob("journai-selftest-*")))
            for extra in ({}, {"JOURNAI_JETON_DEV": "short"},
                          {"JOURNAI_JETON_DEV": KEY, "JOURNAI_ENV": "staging"},
                          {"JOURNAI_JETON_DEV": KEY, "JOURNAI_ENV": "prod"},
                          {"JOURNAI_PORT": "invalid"}):
                result = subprocess.run([*command, "serve"], cwd=root, env={**env, **extra},
                                        capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ERREUR", result.stderr)
                self.assertNotIn(KEY, result.stdout + result.stderr)
            import socket
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            process = subprocess.Popen([*command, "serve"], cwd=root,
                                       env={**env, "JOURNAI_JETON_DEV": KEY, "JOURNAI_PORT": str(port)},
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 10
                while True:
                    try:
                        with closing(http.client.HTTPConnection("127.0.0.1", port, timeout=1)) as client:
                            client.request("GET", "/api/v1/projet", headers={"Authorization": "Bearer " + token()})
                            response = client.getresponse()
                            body = response.read()
                            self.assertEqual(response.status, 200)
                            payload = json.loads(body)
                            projects = payload["data"]
                            self.assertEqual(len(projects), payload["meta"]["total"])
                            self.assertEqual(projects[0]["id"], PROJECT)
                            self.assertNotIn(OTHER_PROJECT, {project["id"] for project in projects})
                        break
                    except (ConnectionRefusedError, ConnectionResetError):
                        if process.poll() is not None or time.monotonic() >= deadline:
                            self.fail("serve n'est pas prêt")
                        time.sleep(0.05)
                for auth, path, expected in (
                    (None, "/api/v1/projet", 401),
                    ("Bearer invalid", "/api/v1/projet", 401),
                    ("Bearer " + token("00000000-0000-4000-8000-000000000000"), "/api/v1/projet", 401),
                    ("Bearer " + token(space="00000000-0000-4000-8000-000000000000"), "/api/v1/projet", 403),
                    ("Bearer " + token(), "/api/v1/projet/" + OTHER_PROJECT, 403),
                ):
                    with closing(http.client.HTTPConnection("127.0.0.1", port, timeout=3)) as client:
                        client.request("GET", path, headers={"Authorization": auth} if auth else {})
                        response = client.getresponse()
                        body = response.read().decode()
                        self.assertEqual(response.status, expected)
                        self.assertNotIn(KEY, body)
                        if auth:
                            self.assertNotIn(auth.removeprefix("Bearer "), body)
                        self.assertNotIn(OTHER_PROJECT, body)
            finally:
                process.terminate()
                stdout, stderr = process.communicate(timeout=10)
                self.assertNotIn(KEY, stdout + stderr)
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(before, list(connection.iterdump()))


if __name__ == "__main__":
    unittest.main()
