"""Local-only IT Incident & Asset demo, Python 3.10+, no external packages."""
import csv
import io
import ipaddress
import json
import os
import secrets
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from store import Store


def secure_cookie_attributes(http_only=True):
    flags = "; SameSite=Strict; Path=/"
    if http_only:
        flags += "; HttpOnly"
    if os.environ.get("MIHWAR_SECURE_COOKIES") == "1":
        flags += "; Secure"
    return flags


def login_source_address(peer_address, forwarded_for, trusted_proxy):
    """Honor one proxy-provided client IP only from an explicitly trusted peer."""
    if not trusted_proxy or peer_address != trusted_proxy or not forwarded_for:
        return peer_address
    try:
        return str(ipaddress.ip_address(forwarded_for.strip()))
    except ValueError:
        return peer_address


def spreadsheet_safe(value):
    """Prevent spreadsheet formula execution when CSV is opened interactively."""
    text = str(value)
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "\u0027" + text
    return text

ROOT = Path(__file__).resolve().parent
ASSETS = {"/": (ROOT / "static/index.html", "text/html; charset=utf-8"),
          "/employee": (ROOT / "static/employee.html", "text/html; charset=utf-8"),
          "/static/app.js": (ROOT / "static/app.js", "text/javascript; charset=utf-8"),
          "/static/style.css": (ROOT / "static/style.css", "text/css; charset=utf-8"),
          "/static/admin.css": (ROOT / "static/admin.css", "text/css; charset=utf-8"),
          "/static/employee.js": (ROOT / "static/employee.js", "text/javascript; charset=utf-8"),
          "/static/employee.css": (ROOT / "static/employee.css", "text/css; charset=utf-8")}


class Handler(BaseHTTPRequestHandler):
    store = None
    server_version = "InfraOpsDemo/1.0"

    def cookie_attributes(self, http_only=True):
        return secure_cookie_attributes(http_only)

    def session(self):
        cookies = self.headers.get("Cookie", "")
        token = next((part.strip().split("=", 1)[1] for part in cookies.split(";")
                      if part.strip().startswith("m_session=")), None)
        return self.store.get_session(token), token

    def cookie(self, name):
        for part in self.headers.get("Cookie", "").split(";"):
            key, sep, value = part.strip().partition("=")
            if sep and key == name:
                return value
        return None

    def require_user(self, roles=None, csrf=False):
        user, _ = self.session()
        if not user:
            self.respond({"error": "Authentication required"}, 401)
            return None
        if roles and user["role"] not in roles:
            self.respond({"error": "Forbidden"}, 403)
            return None
        if csrf and not secrets.compare_digest(user["csrf_token"], self.headers.get("X-CSRF-Token", "")):
            self.respond({"error": "Invalid CSRF token"}, 403)
            return None
        return user

    def log_message(self, fmt, *args):
        print("[http] " + fmt % args)

    def respond(self, data, status=200, extra_headers=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
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
        self.send_header("Content-Security-Policy", "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        path = url.path
        qs = parse_qs(url.query)
        try:
            if path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if path in ASSETS:
                return self.static(path)
            if path == "/api/session":
                user, _ = self.session()
                if not user:
                    csrf = secrets.token_urlsafe(24)
                    return self.respond({"user": None, "csrf_token": csrf}, extra_headers={"Set-Cookie": f"m_csrf={csrf}{self.cookie_attributes()}"})
                return self.respond({"user": {"username": user["username"], "role": user["role"]}, "csrf_token": user["csrf_token"]})
            if path == "/api/employee/assets":
                user = self.require_user({"employee"})
                if not user: return
                return self.respond({"assets": self.store.assets()})
            if path == "/api/employees":
                if not self.require_user({"admin"}): return
                return self.respond({"employees": self.store.employees()})
            if path == "/api/technicians":
                if not self.require_user({"admin"}): return
                return self.respond({"technicians": self.store.technicians()})
            if path == "/api/employee/tickets":
                user = self.require_user({"employee"})
                if not user: return
                return self.respond({"tickets": self.store.employee_tickets(user["id"])})
            if path.startswith("/api/employee/tickets/"):
                user = self.require_user({"employee"})
                if not user: return
                ticket = self.store.employee_ticket(user["id"], self.parse_employee_id(path))
                ticket["events"] = [event for event in ticket["events"] if not event["event"].startswith("Internal:")]
                return self.respond(ticket)
            if path == "/employee":
                return self.static("/employee")
            if path == "/api/health":
                return self.respond({"status": "ok", "app": "InfraOps Desk", "mode": "local demo"})
            if path == "/api/assets":
                if not self.require_user({"technician", "admin"}): return
                return self.respond({"assets": self.store.assets()})
            if path == "/api/dashboard":
                user = self.require_user({"technician", "admin"})
                if not user: return
                return self.respond(self.store.dashboard(user["id"] if user["role"] == "technician" else None))
            if path == "/api/tickets":
                user = self.require_user({"technician", "admin"})
                if not user: return
                assigned = user["id"] if user["role"] == "technician" else None
                return self.respond({"tickets": self.store.tickets(qs.get("status", [None])[0], qs.get("q", [None])[0], assigned_user=assigned)})
            if path.startswith("/api/tickets/"):
                user = self.require_user({"technician", "admin"})
                if not user: return
                ticket_id = self.parse_id(path)
                ticket = self.store.ticket(ticket_id) if user["role"] == "admin" else self.store.technician_ticket(user["id"], ticket_id)
                return self.respond(ticket)
            if path == "/api/export.csv":
                if not self.require_user({"admin"}): return
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

    @staticmethod
    def parse_employee_id(path):
        value = path.removeprefix("/api/employee/tickets/")
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
            path = urlsplit(self.path).path
            if path == "/api/login":
                payload = self.read_json()
                if (not isinstance(payload, dict) or not isinstance(payload.get("username"), str) or not isinstance(payload.get("password"), str)
                        or not 1 <= len(payload["username"]) <= 80 or not 1 <= len(payload["password"]) <= 256):
                    raise ValueError("Username and password are required")
                if not self.cookie("m_csrf") or not secrets.compare_digest(self.cookie("m_csrf"), self.headers.get("X-CSRF-Token", "")):
                    return self.respond({"error": "Invalid CSRF token"}, 403)
                remote_address = login_source_address(self.client_address[0], self.headers.get("X-Forwarded-For"),
                                                      os.environ.get("MIHWAR_TRUSTED_PROXY_IP"))
                allowed, retry_after = self.store.login_allowed(payload["username"], remote_address)
                if not allowed:
                    return self.respond({"error": "Too many sign-in attempts. Try again later."}, 429,
                                        {"Retry-After": str(retry_after)})
                user = self.store.authenticate(payload["username"], payload["password"])
                if not user:
                    self.store.record_login_failure(payload["username"], remote_address)
                    return self.respond({"error": "Invalid username or password"}, 401)
                self.store.clear_login_failures(payload["username"], remote_address)
                token, csrf, expires = self.store.create_session(user["id"])
                expiry = datetime.strptime(expires, '%Y-%m-%dT%H:%M:%SZ').strftime('%a, %d %b %Y %H:%M:%S GMT')
                return self.respond({"user": {"username": user["username"], "role": user["role"]}, "csrf_token": csrf}, 200,
                    {"Set-Cookie": f"m_session={token}{self.cookie_attributes()}; Expires={expiry}"})
            if path == "/api/logout":
                user = self.require_user(csrf=True)
                if not user: return
                _, token = self.session()
                self.store.logout(token)
                return self.respond({"ok": True}, extra_headers={"Set-Cookie": f"m_session={self.cookie_attributes()}; Max-Age=0"})
            if path == "/api/employees":
                if not self.require_user({"admin"}, csrf=True): return
                payload = self.read_json()
                if not isinstance(payload, dict):
                    raise ValueError("Body must be a JSON object")
                employee = self.store.create_employee(payload.get("username"), payload.get("password"))
                return self.respond({"employee": employee}, 201)
            if path.startswith("/api/employee/tickets/") and path.endswith("/reopen"):
                user = self.require_user({"employee"}, csrf=True)
                if not user: return
                ticket_id = self.parse_employee_id(path.removesuffix("/reopen"))
                return self.respond(self.store.reopen_employee_ticket(user["id"], ticket_id))
            if path.startswith("/api/tickets/") and path.endswith("/notes"):
                user = self.require_user({"technician", "admin"}, csrf=True)
                if not user: return
                payload = self.read_json()
                if not isinstance(payload, dict):
                    raise ValueError("Body must be a JSON object")
                ticket_id = self.parse_id(path.removesuffix("/notes"))
                if user["role"] == "technician":
                    self.store.technician_ticket(user["id"], ticket_id)
                return self.respond(self.store.add_ticket_note(ticket_id, user["id"], payload.get("note"), payload.get("internal", False)))
            user = self.require_user({"employee"}, csrf=True) if path == "/api/employee/tickets" else self.require_user({"technician", "admin"}, csrf=True) if path == "/api/tickets" else None
            if path not in {"/api/tickets", "/api/employee/tickets"}:
                return self.respond({"error": "Not found"}, 404)
            if not user: return
            payload = self.read_json()
            ticket = self.store.create_employee_ticket(user["id"], payload) if path == "/api/employee/tickets" else self.store.create_ticket(payload, user["id"])
            return self.respond(ticket, 201)
        except ValueError as exc:
            return self.respond({"error": str(exc)}, 400)
        except LookupError as exc:
            return self.respond({"error": str(exc)}, 404)

    def do_PATCH(self):
        try:
            path = urlsplit(self.path).path
            if not path.startswith("/api/tickets/"):
                return self.respond({"error": "Not found"}, 404)
            payload = self.read_json()
            if path.endswith("/assign"):
                user = self.require_user({"admin"}, csrf=True)
                if not user: return
                self.store.assign_ticket(self.parse_id(path.removesuffix("/assign")), payload.get("technician_id") if isinstance(payload, dict) else None, user["id"])
                return self.respond(self.store.ticket(self.parse_id(path.removesuffix("/assign"))))
            user = self.require_user({"technician", "admin"}, csrf=True)
            if not user: return
            ticket_id = self.parse_id(path)
            if user["role"] == "technician":
                self.store.technician_ticket(user["id"], ticket_id)
            return self.respond(self.store.change_status(ticket_id, payload, user["id"]))
        except ValueError as exc:
            return self.respond({"error": str(exc)}, 400)
        except LookupError as exc:
            return self.respond({"error": str(exc)}, 404)


def start_server(port=8765, db_path=None):
    path = db_path or os.environ.get("INFRAOPS_DB", str(ROOT / "data" / "infraops.sqlite"))
    handler = type("LocalHandler", (Handler,), {"store": Store(path)})
    for name, key, role in (("MIHWAR_EMPLOYEE_USER", "MIHWAR_EMPLOYEE_PASSWORD", "employee"),
                            ("MIHWAR_TECH_USER", "MIHWAR_TECH_PASSWORD", "technician"),
                            ("MIHWAR_ADMIN_USER", "MIHWAR_ADMIN_PASSWORD", "admin")):
        username, password = os.environ.get(name), os.environ.get(key)
        if username and password:
            handler.store.ensure_user(username, password, role)
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
