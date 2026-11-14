import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = {
    "0001_identite_espace_projet.sql", "0002_parcours_etape_contact.sql",
    "0003_operation_ressource_constat.sql", "0004_action_arbitrage.sql",
    "0005_collaboration_pilotage.sql", "0006_versions_courantes.sql",
    "0007_cles_occurrences.sql",
}
FIXTURES = {"espace-a.json", "espace-b.json"}


class PackagingSocleTests(unittest.TestCase):
    def test_wheel_contents_and_installed_migrations_and_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            shutil.copy2(ROOT / "pyproject.toml", source)
            shutil.copytree(ROOT / "journai", source / "journai",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            wheels = root / "wheels"
            wheels.mkdir()
            env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH")
                   if key in os.environ}
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
                self.assertNotIn("Requires-Dist:", content)
                self.assertFalse(any(name.endswith(".dist-info/entry_points.txt") for name in names))
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
versions = [f"{number:04}" for number in range(1, 8)]
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
