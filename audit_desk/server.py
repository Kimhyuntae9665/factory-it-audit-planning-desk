"""Loopback-only native HTTP API for the synthetic planning matrix."""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from audit_desk.core import CUTOFFS, Desk, PlanningError

ROOT = Path(__file__).resolve().parents[1]
STATIC = {"/": ("static/index.html", "text/html; charset=utf-8"),
          "/app.js": ("static/app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("static/style.css", "text/css; charset=utf-8")}
MAX_BODY = 16_384


def strict_json(raw):
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PlanningError("duplicate_json_key", 400)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=no_duplicates)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # No synthetic source text, review notes or demo actor tokens in logs.
        return

    def _send(self, status, payload, content_type="application/json; charset=utf-8",
              filename=None):
        data = (json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
                if isinstance(payload, (dict, list)) else payload)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
                         "base-uri 'none'; frame-ancestors 'none'")
        if filename:
            self.send_header("Content-Disposition", 'attachment; filename="' + filename + '"')
        self.end_headers()
        self.wfile.write(data)

    def _error(self, error):
        if isinstance(error, PlanningError):
            self._send(error.status, {"error": error.code})
        else:
            self._send(400, {"error": "invalid_request"})

    def _context(self, query):
        def one(name, default=None):
            vals = query.get(name, [])
            if not vals:
                if default is not None:
                    return default
                raise PlanningError("missing_" + name, 400)
            if len(vals) != 1 or not vals[0]:
                raise PlanningError("invalid_" + name, 400)
            return vals[0]
        return (one("service"), one("period", "2026-08"),
                one("cutoff", CUTOFFS[0]))

    def _actor(self):
        return self.headers.get("X-Demo-Actor", "")

    def do_GET(self):
        route = urlparse(self.path)
        if route.path in STATIC:
            file, mime = STATIC[route.path]
            self._send(200, (ROOT / file).read_bytes(), mime)
            return
        if route.path == "/health":
            self._send(200, {"status": "ok", "scope": "synthetic_loopback"})
            return
        query = parse_qs(route.query, keep_blank_values=True)
        actor = self._actor()
        try:
            if route.path == "/api/meta":
                result = self.server.desk.metadata(actor)
            elif route.path == "/api/plan":
                result = self.server.desk.plan(actor, *self._context(query))
            elif route.path.startswith("/api/source/"):
                doc_id = unquote(route.path.removeprefix("/api/source/"))
                result = self.server.desk.source(actor, *self._context(query), doc_id)
            elif route.path == "/api/reviews":
                result = self.server.desk.history(actor, *self._context(query))
            elif route.path.startswith("/api/export/"):
                receipt_id = unquote(route.path.removeprefix("/api/export/"))
                result = self.server.desk.export(actor, *self._context(query), receipt_id)
                self._send(200, result, filename="reviewed-audit-plan.json")
                return
            else:
                raise PlanningError("not_found", 404)
            self._send(200, result)
        except (PlanningError, ValueError, TypeError, json.JSONDecodeError) as error:
            self._error(error)

    def do_POST(self):
        route = urlparse(self.path)
        if route.path != "/api/reviews":
            self._send(404, {"error": "not_found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > MAX_BODY:
                raise PlanningError("invalid_body_size", 413)
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                raise PlanningError("json_required", 415)
            data = strict_json(self.rfile.read(size))
            if not isinstance(data, dict) or set(data) != {
                    "service", "period", "cutoff", "fingerprint", "note"}:
                raise PlanningError("review_body_shape", 400)
            result, created = self.server.desk.review(
                self._actor(), data["service"], data["period"], data["cutoff"],
                data["fingerprint"], data["note"])
            self._send(201 if created else 200, result)
        except (PlanningError, ValueError, TypeError, json.JSONDecodeError) as error:
            self._error(error)


def make_server(host="127.0.0.1", port=19095, desk=None):
    if host != "127.0.0.1":
        raise ValueError("loopback_only")
    server = ThreadingHTTPServer((host, port), Handler)
    server.desk = desk or Desk()
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19095)
    args = parser.parse_args()
    with make_server(args.host, args.port) as server:
        print("P15 synthetic audit planning listening on 127.0.0.1:" + str(server.server_port),
              flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
