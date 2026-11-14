"""Transport HTTP de lecture F01 ; aucune opération d'écriture."""

import json
import re
import sqlite3
from contextlib import closing
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qsl, urlsplit

from journai.auth import AuthError, DemoAuth
from journai.config import Config
from journai.queries import CATALOG, QueryError, read

SAFE_FIELDS = {column for resource in CATALOG.values() for column in resource.columns} | {
    "limit", "offset", "ordre", "sens", "include", "corps", "authorization", "origin", "parametre"
}


class ApiServer(HTTPServer):
    def __init__(self, config: Config):
        self.auth = DemoAuth(config)
        self.config = config
        origin = config.cors_origin
        if origin:
            parsed = urlsplit(origin)
            if (parsed.scheme not in {"http", "https"} or not parsed.netloc or
                    parsed.username is not None or parsed.password is not None or
                    parsed.path or parsed.query or parsed.fragment or "*" in origin or
                    any(c.isspace() or ord(c) < 32 for c in origin)):
                raise ValueError("Origine CORS invalide")
        super().__init__((config.host, config.port), ApiHandler)

    def handle_error(self, request, client_address):
        pass


class ApiHandler(BaseHTTPRequestHandler):
    server: ApiServer
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(3)

    def log_message(self, format, *args):
        pass  # Les URL et en-têtes peuvent contenir des données sensibles.

    def _cors(self):
        origins = self.headers.get_all("Origin", []) if hasattr(self, "headers") else []
        if len(origins) == 1 and self.server.config.cors_origin and origins[0] == self.server.config.cors_origin:
            self.send_header("Access-Control-Allow-Origin", origins[0])
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization")
        self.send_header("Vary", "Origin")

    def _respond(self, status, payload=None, *, etag=None):
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        if payload is not None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if etag:
            self.send_header("ETag", etag)
        if status == 405:
            self.send_header("Allow", "GET, HEAD, OPTIONS")
        self._cors()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, status, fields=()):
        codes = {400: ("parametres_invalides", "Paramètres invalides"),
                 401: ("authentification_requise", "Authentification refusée"),
                 403: ("acces_refuse", "Accès refusé"),
                 404: ("introuvable", "Ressource introuvable"),
                 405: ("methode_interdite", "Méthode non autorisée"),
                 500: ("erreur_interne", "Une erreur interne est survenue")}
        code, message = codes.get(status, codes[400])
        error: dict[str, str | list[str]] = {"code": code, "message": message}
        if fields:
            error["champs"] = [field if field in SAFE_FIELDS else "parametre" for field in fields]
        elif status == 400:
            error["champs"] = ["parametre"]
        self._respond(status, {"error": error})

    def send_error(self, code, message=None, explain=None):
        self.close_connection = True
        self._error(code if code in (400, 401, 403, 404, 405, 500) else 400)

    def _no_body(self):
        lengths = self.headers.get_all("Content-Length", [])
        if (len(lengths) > 1 or (lengths and lengths[0] != "0") or
                self.headers.get_all("Transfer-Encoding", []) or self.headers.get_all("Cookie", [])):
            self._discard_body()
            self.close_connection = True
            raise QueryError(400)

    def do_OPTIONS(self):
        try:
            self._no_body()
            if len(self.headers.get_all("Origin", [])) > 1:
                raise QueryError(400)
            self._respond(200)
        except QueryError as exc:
            self._error(exc.status, exc.fields)

    def do_GET(self):
        try:
            self._no_body()
            if len(self.headers.get_all("Origin", [])) > 1:
                raise QueryError(400)
            auth = self.headers.get_all("Authorization", [])
            if len(auth) != 1:
                raise AuthError(401)
            spaces = self.headers.get_all("X-Espace-Id", [])
            if len(spaces) > 1:
                raise QueryError(400, ("espace_id",))
            if any(self.headers.get_all(name, []) for name in ("X-Projet-Id", "X-Role")):
                raise QueryError(400)
            with closing(sqlite3.connect(self.server.config.db_path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
                connection.execute("BEGIN")
                context = self.server.auth.authenticate(connection, auth[0], espace_id=spaces[0] if spaces else None)
                self._read(connection, context)
        except (AuthError, QueryError) as exc:
            self._error(exc.status, getattr(exc, "fields", ()))
        except Exception:
            self._error(500)

    def _read(self, connection, context):
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc or parsed.fragment or re.search(r"%(?![0-9a-fA-F]{2})", parsed.query):
            raise QueryError(400)
        try:
            pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True,
                              encoding="utf-8", errors="strict", max_num_fields=100)
        except (ValueError, UnicodeError):
            raise QueryError(400) from None
        params = dict(pairs)
        if len(params) != len(pairs):
            raise QueryError(400)
        if "espace_id" in params and params["espace_id"] != context.espace_id:
            raise QueryError(403, ("espace_id",))
        path = parsed.path.split("/")
        if len(path) not in (4, 5) or path[:3] != ["", "api", "v1"] or not all(path[3:]):
            raise QueryError(404)
        name = path[3]
        identifier = path[4] if len(path) == 5 else None
        if name == "espace" and identifier is not None and identifier != context.espace_id:
            raise QueryError(403, ("espace_id",))
        result = read(connection, context, name, params, identifiant=identifier)
        data = result["data"]
        etag = f'"{data["id"]}@{data["revision"]}"' if identifier and isinstance(data, dict) and "id" in data and "revision" in data else None
        self._respond(200, result, etag=etag)

    do_HEAD = do_GET

    def __getattr__(self, name):
        if name.startswith("do_"):
            return self._method_not_allowed
        raise AttributeError(name)

    def _discard_body(self):
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) == 1 and lengths[0].isascii() and lengths[0].isdigit() and len(lengths[0]) < 7:
            self.rfile.read(int(lengths[0]))

    def _method_not_allowed(self):
        self._discard_body()
        self.close_connection = True
        self._error(405)


def serve(config: Config):
    server = ApiServer(config)
    try:
        server.serve_forever()
    finally:
        server.server_close()
