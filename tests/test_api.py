import csv
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import start_server, spreadsheet_safe
from store import determine_priority, Store


class RulesTests(unittest.TestCase):
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
    def test_csv_cells_are_safe_in_spreadsheets(self):
        for value in ("=1+2", "+cmd", "-3+5", "@formula", " \t=SUM(A1:A2)"):
            self.assertTrue(spreadsheet_safe(value).startswith("'"))
        self.assertEqual(spreadsheet_safe("Normal incident title"), "Normal incident title")

    def test_dashboard_not_truncated_to_250(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "tickets.sqlite")
            for i in range(260):
                store.create_ticket({"title":f"Synthetic incident {i}","asset_id":1,"impact":1,"urgency":1})
            self.assertEqual(store.dashboard()["total"], 266)
            self.assertEqual(len(store.tickets()), 250)
            self.assertEqual(len(store.tickets(limit=None)), 266)


class APIIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.db = str(Path(cls.temp.name) / "test.sqlite")
        cls.server = start_server(0, cls.db)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def request(self, path, method="GET", payload=None, status=200):
        data = json.dumps(payload).encode() if payload is not None else None
        req = Request(self.url + path, data=data, method=method, headers={"Content-Type":"application/json"} if payload is not None else {})
        try:
            with urlopen(req, timeout=5) as res:
                self.assertEqual(res.status, status)
                return res.read(), res.headers.get('Content-Type', '')
        except HTTPError as error:
            self.assertEqual(error.code, status)
            return error.read(), error.headers.get('Content-Type', '')

    def test_01_local_assets_and_dashboard(self):
        data = json.loads(self.request("/api/assets")[0])
        self.assertEqual(len(data["assets"]), 6)
        self.assertTrue(all(a["asset_tag"].startswith("DEMO-") for a in data["assets"]))
        dashboard = json.loads(self.request("/api/dashboard")[0])
        self.assertEqual(dashboard["assets"], 6)
        self.assertGreater(dashboard["open"], 0)
        self.assertGreaterEqual(dashboard["breached"], 1)

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
        rows = json.loads(self.request("/api/tickets?q=DEMO-SW-01")[0])["tickets"]
        self.assertGreaterEqual(len(rows), 1)
        self.assertTrue(all(x["asset_tag"] == "DEMO-SW-01" for x in rows))
        rows = json.loads(self.request("/api/tickets?status=Resolved")[0])["tickets"]
        self.assertTrue(rows and all(x["status"] == "Resolved" for x in rows))
        csv_bytes, mime = self.request("/api/export.csv")
        rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
        self.assertGreaterEqual(len(rows), 6)
        self.assertIn("text/csv",mime)

    def test_05_static_assets_and_health(self):
        html, mime = self.request("/")
        self.assertIn(b"InfraOps Desk",html)
        self.assertIn("text/html",mime)
        self.assertIn(b"Operations overview",html)
        self.assertIn(b"'use strict'", self.request("/static/app.js")[0])
        self.assertEqual(json.loads(self.request("/api/health")[0])["status"],"ok")

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

    def test_06_persistence_across_store_instances(self):
        before = len(Store(self.db).tickets())
        Store(self.db).create_ticket({"title":"Test persistence across connections","asset_id":1,"impact":1,"urgency":1})
        self.assertEqual(len(Store(self.db).tickets()), before + 1)


if __name__ == "__main__":
    unittest.main()
