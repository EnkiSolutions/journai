import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from journai.config import Config, load_config


EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "journai.example.json"


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        previous = Path.cwd()
        os.chdir(self.temp.name)
        self.addCleanup(os.chdir, previous)
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def write_json(self, path, value):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_defaults_and_real_example(self):
        expected = Config("dev", Path("var/journai.db"), "127.0.0.1", 8000,
                          "INFO", Path("journai/migrations"), "")
        self.assertEqual(load_config(), expected)
        self.assertEqual(load_config(EXAMPLE), expected)
        self.assertEqual(set(json.loads(EXAMPLE.read_text(encoding="utf-8"))),
                         {"env", "db", "host", "port", "log_level", "schema_dir", "cors_origin"})

    def test_priorities_and_explicit_file(self):
        self.write_json("config/journai.example.json", {
            "env": "test", "db": "example.db", "host": "example", "port": 1234,
            "log_level": "DEBUG", "schema_dir": "example-schema", "cors_origin": "example-origin"})
        self.write_json("config/journai.json", {"db": "local.db", "host": "local"})
        self.write_json("other.json", {"db": "explicit.db", "port": 2345})
        with patch.dict(os.environ, {"JOURNAI_HOST": "environment"}):
            self.assertEqual(load_config(), Config("test", Path("local.db"), "environment", 1234,
                                                 "DEBUG", Path("example-schema"), "example-origin"))
            self.assertEqual(load_config("other.json"), Config("test", Path("explicit.db"),
                             "environment", 2345, "DEBUG", Path("example-schema"), "example-origin"))

    def test_environment_mapping(self):
        with patch.dict(os.environ, {
            "JOURNAI_ENV": "staging", "JOURNAI_DB": "env.db", "JOURNAI_HOST": "env-host",
            "JOURNAI_PORT": "4321", "JOURNAI_LOG_LEVEL": "WARNING",
            "JOURNAI_SCHEMA_DIR": "env-schema", "JOURNAI_CORS_ORIGIN": "https://example.org",
            "JOURNAI_JETON_DEV": "not-stored-in-config"}):
            self.assertEqual(load_config(), Config("staging", Path("env.db"), "env-host", 4321,
                             "WARNING", Path("env-schema"), "https://example.org"))

    def test_path_types_and_environment_overrides(self):
        for key, env_key, attribute in (("db", "JOURNAI_DB", "db_path"),
                                        ("schema_dir", "JOURNAI_SCHEMA_DIR", "schema_dir")):
            for value in (None, True, False, 42, 1.5, [], {}):
                with self.subTest(key=key, value=value):
                    self.write_json("config/journai.json", {key: value})
                    with self.assertRaisesRegex(ValueError, key + " doit être un chemin textuel"):
                        load_config()
                    with patch.dict(os.environ, {env_key: "environment/path"}):
                        self.assertEqual(getattr(load_config(), attribute), Path("environment/path"))
            self.write_json("config/journai.json", {key: "local/path"})
            self.assertEqual(getattr(load_config(), attribute), Path("local/path"))
            self.write_json("config/journai.json", {})
            default = "var/journai.db" if key == "db" else "journai/migrations"
            self.assertEqual(getattr(load_config(), attribute), Path(default))

    def test_path_priorities_validate_only_the_selected_value(self):
        for key, env_key, attribute in (("db", "JOURNAI_DB", "db_path"),
                                        ("schema_dir", "JOURNAI_SCHEMA_DIR", "schema_dir")):
            with self.subTest(key=key):
                self.write_json("config/journai.example.json", {key: None})
                self.write_json("config/journai.json", {key: "local/path"})
                self.write_json("explicit.json", {key: "explicit/path"})
                self.assertEqual(getattr(load_config(), attribute), Path("local/path"))
                self.assertEqual(getattr(load_config("explicit.json"), attribute), Path("explicit/path"))
                self.write_json("config/journai.json", {})
                with self.assertRaisesRegex(ValueError, key + " doit être un chemin textuel"):
                    load_config()
                with patch.dict(os.environ, {env_key: "environment/path"}):
                    self.assertEqual(getattr(load_config(), attribute), Path("environment/path"))
                self.write_json("config/journai.example.json", {key: "example/path"})
                self.assertEqual(getattr(load_config(), attribute), Path("example/path"))
                self.write_json("explicit.json", {key: None})
                with self.assertRaisesRegex(ValueError, key + " doit être un chemin textuel"):
                    load_config("explicit.json")
                with patch.dict(os.environ, {env_key: "environment/path"}):
                    self.assertEqual(getattr(load_config("explicit.json"), attribute), Path("environment/path"))
                self.write_json("config/journai.example.json", {})

    def test_rejects_invalid_environment_and_port(self):
        for value in ("dev", "test", "staging", "prod"):
            with self.subTest(env=value), patch.dict(os.environ, {"JOURNAI_ENV": value}):
                self.assertEqual(load_config().env, value)
        for value in ("1", "65535"):
            with self.subTest(port=value), patch.dict(os.environ, {"JOURNAI_PORT": value}):
                self.assertEqual(load_config().port, int(value))
        for value in ("", "production", "DEV"):
            with self.subTest(env=value), patch.dict(os.environ, {"JOURNAI_ENV": value}):
                with self.assertRaises(ValueError):
                    load_config()
        for value in ("0", "65536", "abc", "1.5"):
            with self.subTest(port=value), patch.dict(os.environ, {"JOURNAI_PORT": value}):
                with self.assertRaises(ValueError):
                    load_config()
        self.write_json("config/journai.json", {"env": "unknown"})
        with self.assertRaises(ValueError):
            load_config()
        for value in (True, 1.5, None):
            with self.subTest(json_port=value):
                self.write_json("config/journai.json", {"port": value})
                with self.assertRaises(ValueError):
                    load_config()

    def test_rejects_malformed_non_object_and_missing_explicit_file(self):
        for content in ("{", "[]", "null"):
            with self.subTest(content=content):
                Path("invalid.json").write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_config("invalid.json")
        for path in ("config/journai.example.json", "config/journai.json"):
            with self.subTest(path=path):
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                Path(path).write_text("[]", encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_config()
                Path(path).unlink()
        with self.assertRaises(FileNotFoundError):
            load_config("missing.json")


if __name__ == "__main__":
    unittest.main()
