"""Local-only IT Incident & Asset demo, Python 3.10+, no external packages."""
import csv
import io
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from store import Store


def spreadsheet_safe(value):
    """Prevent spreadsheet formula execution when CSV is opened interactively."""
    text = str(value)
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "\u0027" + text
    return text

ROOT = Path(__file__).resolve().parent
ASSETS = {"/": (ROOT / "static/index.html", "text/html; charset=utf-8"),
          "/static/app.js": (ROOT / "static/app.js", "text/javascript; charset=utf-8"),
          "/static/style.css": (ROOT / "static/style.css", "text/css; charset=utf-8")}


class Handler(BaseHTTPRequestHandler):
    store = None
    server_version = "InfraOpsDemo/1.0"

    def log_message(self, fmt, *args):
        print("[http] " + fmt % args)

    def respond(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def static(self, path):
        entry = ASSETS.get(path)
        if not entry:
            return self.respond({"error": "Not found"}, 404)
        file_path, mime = entry
        if not file_path.is_file():
            return self.respond({"error": "Missing file"}, 500)
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        path = url.path
        qs = parse_qs(url.query)
        try:
            if path in ASSETS:
                return self.static(path)
            if path == "/api/health":
                return self.respond({"status": "ok", "app": "InfraOps Desk", "mode": "local demo"})
            if path == "/api/assets":
                return self.respond({"assets": self.store.assets()})
            if path == "/api/dashboard":
                return self.respond(self.store.dashboard())
            if path == "/api/tickets":
                return self.respond({"tickets": self.store.tickets(qs.get("status", [None])[0], qs.get("q", [None])[0])})
            if path.startswith("/api/tickets/"):
                ticket_id = self.parse_id(path)
                return self.respond(self.store.ticket(ticket_id))
            if path == "/api/export.csv":
                rows = self.store.tickets(limit=None)
                columns = ("id", "title", "asset_tag", "priority", "status", "created_at", "due_at", "breached")
                stream = io.StringIO()
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                for t in rows:
                    writer.writerow({k: spreadsheet_safe(t[k]) for k in columns})
                body = stream.getvalue().encode("utf-8-sig")
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="infraops-tickets.csv"')
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            return self.respond({"error": "Not found"}, 404)
        except ValueError as exc:
            return self.respond({"error": str(exc)}, 400)
        except LookupError as exc:
            return self.respond({"error": str(exc)}, 404)

    @staticmethod
    def parse_id(path):
        value = path.removeprefix("/api/tickets/")
        if not value.isdecimal() or int(value) < 1:
            raise ValueError("Invalid ticket id")
        return int(value)

    def read_json(self):
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            raise ValueError("Content-Type must be application/json")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if not 0 < length <= 16_384:
            raise ValueError("Body must be 1-16384 bytes")
        try:
            return json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid JSON") from exc

    def do_POST(self):
        try:
            if urlsplit(self.path).path != "/api/tickets":
                return self.respond({"error": "Not found"}, 404)
            return self.respond(self.store.create_ticket(self.read_json()), 201)
        except ValueError as exc:
            return self.respond({"error": str(exc)}, 400)

    def do_PATCH(self):
        try:
            if not urlsplit(self.path).path.startswith("/api/tickets/"):
                return self.respond({"error": "Not found"}, 404)
            return self.respond(self.store.change_status(self.parse_id(urlsplit(self.path).path), self.read_json()))
        except ValueError as exc:
            return self.respond({"error": str(exc)}, 400)
        except LookupError as exc:
            return self.respond({"error": str(exc)}, 404)


def start_server(port=8765, db_path=None):
    path = db_path or os.environ.get("INFRAOPS_DB", str(ROOT / "data" / "infraops.sqlite"))
    handler = type("LocalHandler", (Handler,), {"store": Store(path)})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8765"))
    server = start_server(port)
    print(f"InfraOps Desk (local demo) http://127.0.0.1:{server.server_address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
