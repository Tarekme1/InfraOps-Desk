import csv
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.cookiejar import CookieJar
from urllib.request import HTTPCookieProcessor, build_opener
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import start_server, spreadsheet_safe, secure_cookie_attributes, login_source_address
from store import determine_priority, Store
from scripts.backup_db import backup, integrity_check, restore


class RulesTests(unittest.TestCase):
    def test_secure_cookie_mode_adds_secure_and_httponly_flags(self):
        with patch.dict(os.environ, {"MIHWAR_SECURE_COOKIES":"1"}):
            flags = secure_cookie_attributes()
            self.assertIn("; Secure", flags)
            self.assertIn("; HttpOnly", flags)
        with patch.dict(os.environ, {}, clear=True):
            self.assertNotIn("; Secure", secure_cookie_attributes())

    def test_login_forwarded_address_is_trusted_only_from_exact_proxy_peer(self):
        self.assertEqual(login_source_address("127.0.0.1", "203.0.113.9", "127.0.0.1"), "203.0.113.9")
        self.assertEqual(login_source_address("192.0.2.2", "203.0.113.9", "127.0.0.1"), "192.0.2.2")
        self.assertEqual(login_source_address("127.0.0.1", "203.0.113.9, 127.0.0.1", "127.0.0.1"), "127.0.0.1")

    def test_impact_urgency_priority_matrix(self):
        self.assertEqual(determine_priority(3, 3), "P1")
        self.assertEqual(determine_priority(3, 2), "P2")
        self.assertEqual(determine_priority(2, 2), "P3")
        self.assertEqual(determine_priority(1, 1), "P4")

    def test_priority_rejects_non_integer_values(self):
        for invalid in [True, "3", 0, 4, 1.2, None]:
            with self.assertRaises(ValueError):
                determine_priority(invalid, 2)


class DataIntegrityTests(unittest.TestCase):
    def test_login_throttle_locks_only_username_and_source_pair_and_can_clear(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "throttle.sqlite")
            for _ in range(5):
                store.record_login_failure("Demo-User", "127.0.0.1")
            self.assertEqual(store.login_allowed("demo-user", "127.0.0.1")[0], False)
            self.assertEqual(store.login_allowed("demo-user", "127.0.0.2")[0], True)
            store.clear_login_failures("DEMO-USER", "127.0.0.1")
            self.assertEqual(store.login_allowed("demo-user", "127.0.0.1"), (True, 0))

    def test_backup_restore_round_trip_and_pre_restore_safety_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            live = root / "live.sqlite"
            snapshot = root / "snapshot.sqlite"
            store = Store(live)
            store.ensure_user("backup-user", "SyntheticBackup-1!", "employee")
            user_id = store.authenticate("backup-user", "SyntheticBackup-1!")["id"]
            original = store.create_employee_ticket(user_id, {"title":"Original backup record","description":"before snapshot","asset_id":None,"impact":1,"urgency":1})
            backup(live, snapshot)
            store.create_employee_ticket(user_id, {"title":"Post backup record","description":"after snapshot","asset_id":None,"impact":1,"urgency":1})
            restore(snapshot, live)
            restored = Store(live)
            self.assertEqual([ticket["id"] for ticket in restored.employee_tickets(user_id)], [original["id"]])
            self.assertEqual(integrity_check(live), "ok")
            safety_copies = list(root.glob("live.sqlite.pre-restore-*.bak"))
            self.assertEqual(len(safety_copies), 1)
            self.assertEqual(len(Store(safety_copies[0]).employee_tickets(user_id)), 2)

    def test_restore_rejects_corrupt_backup_without_changing_live_database(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            live = root / "live.sqlite"
            broken = root / "broken.sqlite"
            Store(live)
            broken.write_bytes(b"not a sqlite database")
            with self.assertRaises((ValueError, sqlite3.DatabaseError)):
                restore(broken, live)
            self.assertEqual(integrity_check(live), "ok")

    def test_csv_cells_are_safe_in_spreadsheets(self):
        for value in ("=1+2", "+cmd", "-3+5", "@formula", " \t=SUM(A1:A2)"):
            self.assertTrue(spreadsheet_safe(value).startswith("'"))
        self.assertEqual(spreadsheet_safe("Normal incident title"), "Normal incident title")

    def test_dashboard_not_truncated_to_250(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "tickets.sqlite")
            for i in range(260):
                store.create_ticket({"title":f"Synthetic incident {i}","asset_id":1,"impact":1,"urgency":1})
            self.assertEqual(store.dashboard()["total"], 287)
            self.assertEqual(len(store.tickets()), 250)
            self.assertEqual(len(store.tickets(limit=None)), 287)

    def test_legacy_database_migration_preserves_demo_rows_and_allows_unlinked_reports(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "legacy.sqlite"
            db = sqlite3.connect(path)
            db.executescript("""
                CREATE TABLE assets(id INTEGER PRIMARY KEY,asset_tag TEXT NOT NULL UNIQUE,name TEXT NOT NULL,category TEXT NOT NULL,location TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'Active');
                CREATE TABLE tickets(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',asset_id INTEGER NOT NULL REFERENCES assets(id),impact INTEGER NOT NULL,urgency INTEGER NOT NULL,priority TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,due_at TEXT NOT NULL,resolved_at TEXT);
                CREATE TABLE ticket_events(id INTEGER PRIMARY KEY AUTOINCREMENT,ticket_id INTEGER NOT NULL REFERENCES tickets(id),event TEXT NOT NULL,note TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
                INSERT INTO assets VALUES(1,'DEMO-OLD-01','Old demo asset','IT','Demo location','Active');
                INSERT INTO tickets VALUES(41,'Existing fictional incident','Preserve me',1,2,2,'P3','Open','2026-10-20T10:00:00Z','2026-10-21T10:00:00Z',NULL);
                INSERT INTO ticket_events VALUES(51,41,'Created','Legacy event','2026-10-20T10:00:00Z');
            """)
            db.commit(); db.close()
            store = Store(path)
            prior = store.ticket(41)
            self.assertEqual(prior["asset_tag"], "DEMO-OLD-01")
            self.assertEqual(prior["events"][0]["note"], "Legacy event")
            store.ensure_user("migration-user", "SyntheticMigration-1!", "employee")
            user_id = store.authenticate("migration-user", "SyntheticMigration-1!")["id"]
            created = store.create_employee_ticket(user_id, {"title":"Unlinked demo service request","description":"Preserve old database rows","asset_id":None,"impact":1,"urgency":1})
            self.assertIsNone(created["asset_id"])
            with store.connect() as migrated:
                self.assertEqual(migrated.execute("PRAGMA foreign_key_check").fetchall(), [])


class APIIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.db = str(Path(cls.temp.name) / "test.sqlite")
        cls.server = start_server(0, cls.db)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        store = Store(cls.db)
        store.ensure_user("demo-tech", "LocalDemo-Only-123!", "technician")
        token, csrf, _ = store.create_session(1)
        cls.tech_headers = {"Cookie": f"m_session={token}", "X-CSRF-Token": csrf}
        store.ensure_user("demo-admin", "LocalAdmin-Only-123!", "admin")
        admin_token, admin_csrf, _ = store.create_session(2)
        cls.admin_headers = {"Cookie": f"m_session={admin_token}", "X-CSRF-Token": admin_csrf}
        store.ensure_user("other-tech", "LocalOtherTech-123!", "technician")
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def request(self, path, method="GET", payload=None, status=200, headers=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request_headers = dict(self.tech_headers)
        if payload is not None: request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        req = Request(self.url + path, data=data, method=method, headers=request_headers)
        try:
            with urlopen(req, timeout=5) as res:
                self.assertEqual(res.status, status)
                return res.read(), res.headers.get('Content-Type', '')
        except HTTPError as error:
            self.assertEqual(error.code, status)
            return error.read(), error.headers.get('Content-Type', '')

    def test_01_local_assets_and_dashboard(self):
        data = json.loads(self.request("/api/assets")[0])
        self.assertEqual(len(data["assets"]), 12)
        self.assertTrue(all(a["asset_tag"].startswith("IT-") for a in data["assets"]))
        dashboard = json.loads(self.request("/api/dashboard")[0])
        self.assertEqual(dashboard["assets"], 12)
        self.assertGreaterEqual(dashboard["total"], 25)
        self.assertGreater(dashboard["open"], 0)
        self.assertGreaterEqual(dashboard["breached"], 1)
        tickets = json.loads(self.request("/api/tickets")[0])["tickets"]
        dates = [ticket["created_at"] for ticket in tickets]
        self.assertTrue(any(date.startswith("2026-03") for date in dates))
        self.assertTrue(any(date.startswith("2026-10") for date in dates))
        first_record = json.loads(self.request(f"/api/tickets/{tickets[0]['id']}")[0])
        self.assertIn("not a record of plant operations", first_record["events"][0]["note"])

    def test_02_create_update_and_audit_events(self):
        body = {"title":"Backup agent failed to start", "description":"Fictional example only", "asset_id":1,"impact":3,"urgency":3}
        data = json.loads(self.request("/api/tickets", method="POST", payload=body, status=201)[0])
        self.assertEqual(data["priority"], "P1")
        self.assertEqual(data["status"], "Open")
        ticket = json.loads(self.request(f"/api/tickets/{data['id']}")[0])
        self.assertEqual(len(ticket["events"]), 1)
        changed = json.loads(self.request(f"/api/tickets/{data['id']}", method="PATCH", payload={"status":"Resolved","note":"Restarted mock service"})[0])
        self.assertEqual(changed["status"], "Resolved")
        self.assertIsNotNone(changed["resolved_at"])
        self.assertEqual(len(changed["events"]), 2)
        self.assertIn("Restarted mock service", changed["events"][-1]["note"])

    def test_03_invalid_input_is_rejected(self):
        data = json.loads(self.request("/api/tickets",method="POST",payload={"title":"x", "asset_id":999, "impact":"3", "urgency":5},status=400)[0])
        self.assertIn("error",data)
        self.assertIn("error", json.loads(self.request("/api/tickets/notanumber", status=400)[0]))
        self.assertIn("error", json.loads(self.request("/api/tickets/999999", status=404)[0]))

    def test_04_filter_search_and_csv(self):
        rows = json.loads(self.request("/api/tickets?q=IT-SW-01")[0])["tickets"]
        self.assertGreaterEqual(len(rows), 1)
        self.assertTrue(all(x["asset_tag"] == "IT-SW-01" for x in rows))
        rows = json.loads(self.request("/api/tickets?status=Resolved")[0])["tickets"]
        self.assertTrue(rows and all(x["status"] == "Resolved" for x in rows))
        csv_bytes, mime = self.request("/api/export.csv", headers=self.admin_headers)
        rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
        self.assertGreaterEqual(len(rows), 27)
        self.assertIn("text/csv",mime)

    def test_05_static_assets_and_health(self):
        html, mime = self.request("/")
        self.assertIn(b"InfraOps Desk",html)
        self.assertIn("text/html",mime)
        self.assertIn(b"Operations overview",html)
        self.assertIn(b"'use strict'", self.request("/static/app.js")[0])
        self.assertEqual(json.loads(self.request("/api/health")[0])["status"],"ok")

    def test_login_api_throttles_repeated_bad_passwords(self):
        Store(self.db).ensure_user("rate-limit-demo", "SyntheticRateLimit-1!", "technician")
        jar = CookieJar(); client = build_opener(HTTPCookieProcessor(jar))
        with client.open(self.url + "/api/session", timeout=5) as response:
            csrf = json.loads(response.read())["csrf_token"]
        for _ in range(5):
            req = Request(self.url + "/api/login", data=json.dumps({"username":"rate-limit-demo","password":"wrong-password"}).encode(), method="POST", headers={"Content-Type":"application/json","X-CSRF-Token":csrf})
            with self.assertRaises(HTTPError) as denied:
                client.open(req, timeout=5)
            self.assertEqual(denied.exception.code, 401)
            denied.exception.close()
        req = Request(self.url + "/api/login", data=json.dumps({"username":"rate-limit-demo","password":"SyntheticRateLimit-1!"}).encode(), method="POST", headers={"Content-Type":"application/json","X-CSRF-Token":csrf})
        with self.assertRaises(HTTPError) as limited:
            client.open(req, timeout=5)
        self.assertEqual(limited.exception.code, 429)
        self.assertGreater(int(limited.exception.headers["Retry-After"]), 0)
        limited.exception.close()

    def test_07_unknown_asset_and_invalid_status(self):
        bad_asset = {"title":"Unknown asset ticket", "asset_id":9999,"impact":2,"urgency":2}
        error = json.loads(self.request("/api/tickets", method="POST", payload=bad_asset, status=400)[0])
        self.assertEqual(error["error"], "Unknown asset")
        bad_filter = json.loads(self.request("/api/tickets?status=NotAStatus", status=400)[0])
        self.assertIn("Invalid status", bad_filter["error"])

    def test_08_status_transition_and_duplicate_rejection(self):
        created = json.loads(self.request("/api/tickets",method="POST",payload={
            "title":"Mock wireless degradation", "asset_id":6,"impact":2,"urgency":2},status=201)[0])
        tid = created["id"]
        progressing = json.loads(self.request(f"/api/tickets/{tid}",method="PATCH",payload={
            "status":"In Progress","note":"Checked synthetic network logs"})[0])
        self.assertEqual(progressing["status"],"In Progress")
        self.assertEqual(len(progressing["events"]),2)
        missing_resolution = json.loads(self.request(f"/api/tickets/{tid}",method="PATCH",payload={"status":"Resolved"},status=400)[0])
        self.assertIn("resolution note", missing_resolution["error"].lower())
        repeat = json.loads(self.request(f"/api/tickets/{tid}",method="PATCH",payload={
            "status":"In Progress","note":"Duplicated status"},status=400)[0])
        self.assertIn("already", repeat["error"])
        final = json.loads(self.request(f"/api/tickets/{tid}",method="PATCH",payload={
            "status":"Resolved","note":"Resolution checked"})[0])
        self.assertEqual(len(final["events"]),3)
        self.assertIsNotNone(final["resolved_at"])

    def test_09_no_source_exposure_and_security_headers(self):
        for path in ("/app.py", "/store.py", "/.env", "/static/../app.py"):
            self.assertEqual(json.loads(self.request(path,status=404)[0])["error"],"Not found")
        req = Request(self.url + "/", method="GET")
        with urlopen(req,timeout=5) as res:
            self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(res.headers.get("X-Frame-Options"), "DENY")
            self.assertEqual(res.headers.get("Referrer-Policy"), "no-referrer")

    def test_10_employee_login_csrf_ownership_and_role_boundaries(self):
        store = Store(self.db)
        store.ensure_user("employee-one", "SyntheticEmployee-1!", "employee")
        store.ensure_user("employee-two", "SyntheticEmployee-2!", "employee")

        def login(username, password):
            jar = CookieJar(); client = build_opener(HTTPCookieProcessor(jar))
            with client.open(self.url + "/api/session", timeout=5) as response:
                csrf = json.loads(response.read())["csrf_token"]
            body = json.dumps({"username":username,"password":password}).encode()
            req = Request(self.url + "/api/login", data=body, method="POST", headers={"Content-Type":"application/json","X-CSRF-Token":csrf})
            with client.open(req, timeout=5) as response:
                session = json.loads(response.read())
            return client, session["csrf_token"]

        first, first_csrf = login("employee-one", "SyntheticEmployee-1!")
        second, second_csrf = login("employee-two", "SyntheticEmployee-2!")
        payload = {"title":"Employee wireless issue", "description":"Synthetic employee report", "asset_id":None,"category":"شبكة","impact":2,"urgency":2}
        req = Request(self.url + "/api/employee/tickets", data=json.dumps(payload,ensure_ascii=False).encode(), method="POST", headers={"Content-Type":"application/json","X-CSRF-Token":first_csrf})
        with first.open(req, timeout=5) as response:
            created = json.loads(response.read())
        self.assertIsNone(created["asset_id"])
        self.assertEqual(created["category"], "شبكة")

        with first.open(self.url + f"/api/employee/tickets/{created['id']}", timeout=5) as response:
            self.assertEqual(json.loads(response.read())["id"], created["id"])
        with self.assertRaises(HTTPError) as forbidden_ticket:
            second.open(self.url + f"/api/employee/tickets/{created['id']}", timeout=5)
        self.assertEqual(forbidden_ticket.exception.code, 404)
        with self.assertRaises(HTTPError) as forbidden_admin:
            first.open(self.url + "/api/dashboard", timeout=5)
        self.assertEqual(forbidden_admin.exception.code, 403)

        assigned = json.loads(self.request(f"/api/tickets/{created['id']}/assign", method="PATCH",
            payload={"technician_id":3}, headers=self.admin_headers)[0])
        self.assertEqual(assigned["assigned_to"], 3)
        denied, _ = self.request(f"/api/tickets/{created['id']}", status=404)
        self.assertIn("not found", json.loads(denied)["error"].lower())
        denied_update, _ = self.request(f"/api/tickets/{created['id']}", method="PATCH",
            payload={"status":"In Progress","note":"Must not cross technician assignment"}, status=404)
        self.assertIn("not found", json.loads(denied_update)["error"].lower())
        assigned = json.loads(self.request(f"/api/tickets/{created['id']}/assign", method="PATCH",
            payload={"technician_id":1}, headers=self.admin_headers)[0])
        self.assertEqual(assigned["assigned_to"], 1)
        technician_view = json.loads(self.request(f"/api/tickets/{created['id']}")[0])
        self.assertEqual(technician_view["title"], "Employee wireless issue")
        self.request(f"/api/tickets/{created['id']}/notes", method="POST", payload={"note":"Checked the synthetic switch port","internal":True})
        self.request(f"/api/tickets/{created['id']}/notes", method="POST", payload={"note":"We are investigating your network report","internal":False})
        with first.open(self.url + f"/api/employee/tickets/{created['id']}", timeout=5) as response:
            employee_updates = json.loads(response.read())
        self.assertFalse(any("synthetic switch port" in event["note"] for event in employee_updates["events"]))
        self.assertTrue(any("investigating your network report" in event["note"] for event in employee_updates["events"]))
        progressing = json.loads(self.request(f"/api/tickets/{created['id']}", method="PATCH",
            payload={"status":"In Progress","note":"Reviewed synthetic connection details"})[0])
        resolved = json.loads(self.request(f"/api/tickets/{created['id']}", method="PATCH",
            payload={"status":"Resolved","note":"Applied and verified a demo network fix"})[0])
        self.assertEqual(resolved["status"], "Resolved")
        self.assertTrue(any(event["event"] == "Internal: Note" for event in resolved["events"]))
        self.assertEqual(resolved["events"][-1]["actor_username"], "demo-tech")
        with first.open(self.url + f"/api/employee/tickets/{created['id']}", timeout=5) as response:
            employee_result = json.loads(response.read())
        self.assertEqual(employee_result["status"], "Resolved")
        self.assertIn("Applied and verified", employee_result["events"][-1]["note"])
        wrong_owner_reopen = Request(self.url + f"/api/employee/tickets/{created['id']}/reopen", data=b"{}", method="POST",
            headers={"Content-Type":"application/json","X-CSRF-Token":second_csrf})
        with self.assertRaises(HTTPError) as reopen_denied:
            second.open(wrong_owner_reopen, timeout=5)
        self.assertEqual(reopen_denied.exception.code, 404)
        reopen = Request(self.url + f"/api/employee/tickets/{created['id']}/reopen", data=b"{}", method="POST",
            headers={"Content-Type":"application/json","X-CSRF-Token":first_csrf})
        with first.open(reopen, timeout=5) as response:
            self.assertEqual(json.loads(response.read())["status"], "Open")
        self.request(f"/api/tickets/{created['id']}", method="PATCH", payload={"status":"In Progress","note":"Rechecked after employee follow-up"})
        resolved_again = json.loads(self.request(f"/api/tickets/{created['id']}", method="PATCH",
            payload={"status":"Resolved","note":"Second verification completed"})[0])
        self.assertEqual(resolved_again["status"], "Resolved")
        self.assertEqual(resolved_again["events"][-1]["actor_username"], "demo-tech")
        with Store(self.db).connect() as db:
            employee_id = db.execute("SELECT id FROM users WHERE username='employee-one'").fetchone()[0]
        self.assertEqual(Store(self.db).employee_ticket(employee_id, created["id"])["status"], "Resolved")
        restarted = start_server(0, self.db)
        thread = threading.Thread(target=restarted.serve_forever, daemon=True); thread.start()
        try:
            with first.open(f"http://127.0.0.1:{restarted.server_address[1]}/api/employee/tickets/{created['id']}", timeout=5) as response:
                self.assertEqual(json.loads(response.read())["status"], "Resolved")
        finally:
            restarted.shutdown(); restarted.server_close(); thread.join(timeout=3)

        no_csrf = Request(self.url + "/api/employee/tickets", data=json.dumps(payload).encode(), method="POST", headers={"Content-Type":"application/json"})
        with self.assertRaises(HTTPError) as csrf_error:
            first.open(no_csrf, timeout=5)
        self.assertEqual(csrf_error.exception.code, 403)

    def test_06_persistence_across_store_instances(self):
        before = len(Store(self.db).tickets())
        Store(self.db).create_ticket({"title":"Test persistence across connections","asset_id":1,"impact":1,"urgency":1})
        self.assertEqual(len(Store(self.db).tickets()), before + 1)


if __name__ == "__main__":
    unittest.main()

