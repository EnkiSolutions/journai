import http.client
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from contextlib import closing
from email.parser import Parser
from pathlib import Path
from zipfile import ZipFile

from test_startup import KEY, PROJECT, token


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = {
    "0001_identite_espace_projet.sql", "0002_parcours_etape_contact.sql",
    "0003_operation_ressource_constat.sql", "0004_action_arbitrage.sql",
    "0005_collaboration_pilotage.sql", "0006_versions_courantes.sql",
    "0007_cles_occurrences.sql", "0008_commentaires_espace.sql",
    "0009_integrite_numerique.sql",
}
FIXTURES = {"espace-a.json", "espace-b.json"}


class PackagingSocleTests(unittest.TestCase):
    def assert_dev_metadata(self, content):
        metadata = Parser().parsestr(content)
        self.assertEqual(metadata.get_all("Provides-Extra", []), ["dev"])
        self.assertCountEqual(metadata.get_all("Requires-Dist", []), [
            'ruff==0.12.12; extra == "dev"',
            'mypy==1.17.1; extra == "dev"',
        ])

    def test_dev_metadata_rejects_unwanted_requirements(self):
        valid = ('Provides-Extra: dev\n'
                 'Requires-Dist: ruff==0.12.12; extra == "dev"\n'
                 'Requires-Dist: mypy==1.17.1; extra == "dev"\n')
        self.assert_dev_metadata(valid)
        for invalid in (
            valid + 'Requires-Dist: unexpected==1\n',
            valid + 'Requires-Dist: unexpected==1; extra == "other"\n',
            valid.replace('extra == "dev"', 'extra == "dev" or python_version >= "3"', 1),
            valid.replace('Provides-Extra: dev', 'Provides-Extra: other'),
            valid.replace('ruff==0.12.12', 'ruff==0.12.11'),
        ):
            with self.subTest(metadata=invalid), self.assertRaises(AssertionError):
                self.assert_dev_metadata(invalid)

    def test_wheel_contents_and_installed_migrations_and_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            shutil.copy2(ROOT / "pyproject.toml", source)
            shutil.copytree(ROOT / "journai", source / "journai",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH")
                   if key in os.environ}
            distributions = root / "distributions"
            distributions.mkdir()
            subprocess.run(
                [sys.executable, "-I", "-c",
                 "import sys; import setuptools.build_meta as b; b.build_sdist(sys.argv[1])",
                 str(distributions)], cwd=source, env=env, check=True,
            )
            sdist, = distributions.glob("*.tar.gz")
            with tarfile.open(sdist) as archive:
                members = {name.split("/", 1)[1]: name for name in archive.getnames() if "/" in name}
                for name in MIGRATIONS:
                    path = "journai/migrations/" + name
                    self.assertEqual(archive.extractfile(members[path]).read(), (source / path).read_bytes())
            wheels = root / "wheels"
            wheels.mkdir()
            subprocess.run(
                [sys.executable, "-I", "-m", "pip", "--isolated", "wheel", "--no-index",
                 "--no-deps", "--no-build-isolation", "--wheel-dir", str(wheels), str(source)],
                cwd=root, env=env, check=True,
            )
            wheel, = wheels.glob("*.whl")
            with ZipFile(wheel) as archive:
                names = set(archive.namelist())
                for folder, expected in (("migrations", MIGRATIONS), ("fixtures", FIXTURES)):
                    prefix = f"journai/{folder}/"
                    self.assertEqual({name for name in names if name.startswith(prefix)},
                                     {prefix + name for name in expected})
                    for name in expected:
                        self.assertEqual(archive.read(prefix + name),
                                         (ROOT / "journai" / folder / name).read_bytes())
                metadata, = (name for name in names if name.endswith(".dist-info/METADATA"))
                content = archive.read(metadata).decode("utf-8")
                self.assertIn("Requires-Python: >=3.12", content)
                self.assert_dev_metadata(content)
                entry_points, = (name for name in names if name.endswith(".dist-info/entry_points.txt"))
                self.assertIn("journai = journai.cli:main", archive.read(entry_points).decode("utf-8"))
            target = root / "installed"
            subprocess.run(
                [sys.executable, "-I", "-m", "pip", "--isolated", "install", "--no-index",
                 "--no-deps", "--target", str(target), str(wheel)],
                cwd=root, env=env, check=True,
            )
            subprocess.run(
                [sys.executable, "-I", "-c", INSTALLED_CHECK, str(target), str(ROOT), str(root / "data.db")],
                cwd=root, env=env, check=True,
            )
            empty = root / "empty"
            empty.mkdir()
            module_env = {**env, "PYTHONPATH": str(target), "PYTHONUTF8": "1"}
            module_db = root / "module.db"
            for expected in ("0009", "aucune (déjà à jour)"):
                result = subprocess.run(
                    [sys.executable, "-m", "journai.migrations", "--db", str(module_db)],
                    cwd=empty, env=module_env, text=True, capture_output=True, encoding="utf-8",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)
            overrides = []
            for name in ("config", "env", "explicit"):
                schema = root / (name + "-schema")
                schema.mkdir()
                (schema / "0001_override.sql").write_text(
                    f"CREATE TABLE {name}_override (id INTEGER);", encoding="utf-8")
                overrides.append(schema)
            (empty / "config").mkdir()
            (empty / "config" / "journai.json").write_text(
                json.dumps({"schema_dir": str(overrides[0])}), encoding="utf-8")
            for index, name in enumerate(("config", "env", "explicit")):
                override_env = dict(module_env)
                if index >= 1:
                    override_env["JOURNAI_SCHEMA_DIR"] = str(overrides[1])
                command = [sys.executable, "-m", "journai.migrations", "--db", str(root / (name + ".db"))]
                if index == 2:
                    command += ["--schema-dir", str(overrides[2])]
                result = subprocess.run(command, cwd=empty, env=override_env, text=True,
                                        capture_output=True, encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stderr)
                with closing(sqlite3.connect(root / (name + ".db"))) as connection:
                    self.assertIsNotNone(connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                        (name + "_override",)).fetchone())
            console = target / "bin" / ("journai.exe" if os.name == "nt" else "journai")
            console_env = {**env, "PYTHONPATH": str(target), "PYTHONUTF8": "1", "JOURNAI_DB": str(root / "console.db")}
            result = subprocess.run([str(console)], cwd=root, env=console_env, text=True,
                                    capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("espace=2", result.stdout)
            result = subprocess.run([str(console), "status"], cwd=root, env=console_env, text=True,
                                    capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("espace: 2", result.stdout)
            self.assertIn("0009", result.stdout)
            result = subprocess.run([str(console), "selftest"], cwd=root, env=console_env,
                                    text=True, capture_output=True, encoding="utf-8", timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Selftest réussi", result.stdout)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            process = subprocess.Popen([str(console), "serve"], cwd=root,
                                       env={**console_env, "JOURNAI_JETON_DEV": KEY,
                                            "JOURNAI_PORT": str(port)},
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 10
                while True:
                    try:
                        with closing(http.client.HTTPConnection("127.0.0.1", port, timeout=1)) as client:
                            client.request("GET", "/api/v1/projet", headers={"Authorization": "Bearer " + token()})
                            response = client.getresponse()
                            body = response.read().decode("utf-8")
                            self.assertEqual(response.status, 200)
                            self.assertIn(PROJECT, body)
                        break
                    except (ConnectionRefusedError, ConnectionResetError):
                        if process.poll() is not None or time.monotonic() >= deadline:
                            self.fail("console installée non prête")
                        time.sleep(0.05)
            finally:
                process.terminate()
                stdout, stderr = process.communicate(timeout=10)
                self.assertNotIn(KEY, stdout + stderr)


INSTALLED_CHECK = r'''
import json
import sys
from pathlib import Path

installed, checkout, database = map(Path, sys.argv[1:])
sys.path[:] = [str(installed)] + [p for p in sys.path if p and
    "site-packages" not in p and "dist-packages" not in p and
    not Path(p).resolve().is_relative_to(checkout.resolve())]
from journai import config, db, migrations, seed, validation
import journai

package = installed / "journai"
for module in (journai, config, db, migrations, seed, validation):
    assert Path(module.__file__).resolve().is_relative_to(package.resolve()), module.__file__
versions = [f"{number:04}" for number in range(1, 10)]
connection = db.connect(database)
try:
    assert migrations.migrate(connection, package / "migrations") == versions
    counts = seed.seeded(connection, env="test")
    assert counts["espace"] == 2 and sum(counts.values()) == 116
finally:
    connection.close()
connection = db.connect(database, create=False)
try:
    assert migrations.applied_versions(connection) == versions
    assert migrations.migrate(connection, package / "migrations") == []
    for fixture in ("espace-a.json", "espace-b.json"):
        data = json.loads((package / "fixtures" / fixture).read_text(encoding="utf-8"))
        for table in ("espace", "projet"):
            rows = next(entry["rows"] for entry in data["tables"] if entry["table"] == table)
            for row in rows:
                assert connection.execute(f'SELECT 1 FROM "{table}" WHERE id = ?', (row["id"],)).fetchone()
    assert db.integrity_problems(connection) == []
finally:
    connection.close()
'''


if __name__ == "__main__":
    unittest.main()
