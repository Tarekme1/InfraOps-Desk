"""SQLite persistence and business rules for a local, fictional IT incident demo."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

PRIORITY_HOURS = {"P1": 1, "P2": 4, "P3": 24, "P4": 72}
VALID_STATUSES = ("Open", "In Progress", "Resolved")


def utcnow():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def as_datetime(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def determine_priority(impact, urgency):
    if type(impact) is not int or type(urgency) is not int or not (1 <= impact <= 3 and 1 <= urgency <= 3):
        raise ValueError("Impact and urgency must be integers from 1 to 3")
    score = impact + urgency
    return "P1" if score == 6 else "P2" if score == 5 else "P3" if score == 4 else "P4"


class Store:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self):
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY,
                asset_tag TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                location TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'Active'
            );
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                asset_id INTEGER NOT NULL REFERENCES assets(id),
                impact INTEGER NOT NULL CHECK(impact BETWEEN 1 AND 3),
                urgency INTEGER NOT NULL CHECK(urgency BETWEEN 1 AND 3),
                priority TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Open',
                created_at TEXT NOT NULL,
                due_at TEXT NOT NULL,
                resolved_at TEXT
            );
            CREATE TABLE IF NOT EXISTS ticket_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL REFERENCES tickets(id),
                event TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tickets_status_due ON tickets(status, due_at);
            CREATE INDEX IF NOT EXISTS idx_events_ticket ON ticket_events(ticket_id, id);
            """)
            total = db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
            if total == 0:
                db.executemany("INSERT INTO assets(asset_tag,name,category,location) VALUES(?,?,?,?)", [
                    ("DEMO-SRV-01", "Application Server", "Server", "Demo Server Room"),
                    ("DEMO-SW-01", "Core Switch", "Networking", "Demo Network Rack"),
                    ("DEMO-CCTV-01", "Camera NVR", "Surveillance", "Demo Security Room"),
                    ("DEMO-LAP-01", "Office Laptop", "Endpoint", "Demo Office"),
                    ("DEMO-PRN-01", "Shared Printer", "Peripheral", "Demo Reception"),
                    ("DEMO-AP-01", "Wireless Access Point", "Networking", "Demo Office"),
                ])
                now = utcnow()
                demo = [
                    ("Core switch intermittent packet loss", "Intermittent connectivity in demo network", 2, 3, 3, "In Progress", -7),
                    ("NVR recording alert", "Fictional recorder storage warning", 3, 2, 3, "Open", -3),
                    ("Office printer queue blocked", "Demo staff unable to print", 5, 2, 2, "Open", -1),
                    ("Application service restart needed", "Simulated background job failure", 1, 2, 2, "Resolved", -18),
                    ("Laptop disk cleanup", "Fictional endpoint storage issue", 4, 1, 1, "Resolved", -48),
                    ("Access point roaming issue", "Simulated Wi-Fi user disconnects", 6, 2, 1, "Open", -0.5),
                ]
                for title, desc, asset_id, impact, urgency, status, hours_back in demo:
                    created = now + timedelta(hours=hours_back)
                    priority = determine_priority(impact, urgency)
                    due = created + timedelta(hours=PRIORITY_HOURS[priority])
                    resolved = iso(created + timedelta(hours=1)) if status == "Resolved" else None
                    cur = db.execute("""INSERT INTO tickets(title,description,asset_id,impact,urgency,priority,status,created_at,due_at,resolved_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""", (title, desc, asset_id, impact, urgency, priority, status, iso(created), iso(due), resolved))
                    db.execute("INSERT INTO ticket_events(ticket_id,event,note,created_at) VALUES(?,?,?,?)",
                               (cur.lastrowid, "Created", "Fictional demonstration data", iso(created)))

    def assets(self):
        with self.connect() as db:
            return [dict(x) for x in db.execute("SELECT * FROM assets ORDER BY asset_tag")]

    @staticmethod
    def _decorate(ticket):
        t = dict(ticket)
        t["breached"] = t["status"] != "Resolved" and as_datetime(t["due_at"]) < utcnow()
        return t

    def tickets(self, status=None, search=None, limit=250):
        sql = """SELECT t.*,a.asset_tag,a.name AS asset_name,a.category AS asset_category
            FROM tickets t JOIN assets a ON a.id=t.asset_id WHERE 1=1"""
        params = []
        if status:
            if status not in VALID_STATUSES:
                raise ValueError("Invalid status")
            sql += " AND t.status=?"
            params.append(status)
        if search:
            if len(search) > 100:
                raise ValueError("Search term too long")
            sql += " AND (t.title LIKE ? OR a.asset_tag LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        sql += " ORDER BY CASE t.status WHEN 'Resolved' THEN 1 ELSE 0 END, t.due_at ASC, t.id DESC"
        if limit is not None:
            if type(limit) is not int or not 1 <= limit <= 10000:
                raise ValueError("Invalid limit")
            sql += " LIMIT ?"
            params.append(limit)
        with self.connect() as db:
            return [self._decorate(r) for r in db.execute(sql, params)]

    def create_ticket(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Body must be a JSON object")
        title, desc = payload.get("title"), payload.get("description", "")
        aid = payload.get("asset_id")
        if not isinstance(title, str) or not 5 <= len(title.strip()) <= 120:
            raise ValueError("Title must be between 5 and 120 characters")
        if not isinstance(desc, str) or len(desc) > 1500:
            raise ValueError("Description too long")
        if type(aid) is not int or aid < 1:
            raise ValueError("Valid asset_id required")
        priority = determine_priority(payload.get("impact"), payload.get("urgency"))
        created = utcnow()
        due = created + timedelta(hours=PRIORITY_HOURS[priority])
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM assets WHERE id=?", (aid,)).fetchone():
                raise ValueError("Unknown asset")
            cur = db.execute("""INSERT INTO tickets(title,description,asset_id,impact,urgency,priority,status,created_at,due_at)
              VALUES(?,?,?,?,?,?,?,?,?)""", (title.strip(), desc.strip(), aid, payload["impact"], payload["urgency"], priority, "Open", iso(created), iso(due)))
            ticket_id = cur.lastrowid
            db.execute("INSERT INTO ticket_events(ticket_id,event,note,created_at) VALUES(?,?,?,?)", (ticket_id, "Created", "", iso(created)))
        return self.ticket(ticket_id)

    def ticket(self, ticket_id):
        with self.connect() as db:
            row = db.execute("""SELECT t.*,a.asset_tag,a.name AS asset_name,a.category AS asset_category
                              FROM tickets t JOIN assets a ON a.id=t.asset_id WHERE t.id=?""", (ticket_id,)).fetchone()
            if row is None:
                raise LookupError("Ticket not found")
            ticket = self._decorate(row)
            ticket["events"] = [dict(x) for x in db.execute("SELECT event,note,created_at FROM ticket_events WHERE ticket_id=? ORDER BY id", (ticket_id,))]
            return ticket

    def change_status(self, ticket_id, payload):
        if not isinstance(payload, dict):
            raise ValueError("Body must be a JSON object")
        status, note = payload.get("status"), payload.get("note", "")
        if status not in VALID_STATUSES:
            raise ValueError("Invalid status")
        if not isinstance(note, str) or len(note) > 500:
            raise ValueError("Note must be 500 characters or fewer")
        with self.connect() as db:
            row = db.execute("SELECT status FROM tickets WHERE id=?", (ticket_id,)).fetchone()
            if row is None:
                raise LookupError("Ticket not found")
            if row["status"] == status:
                raise ValueError("Ticket already has this status")
            when = iso(utcnow())
            db.execute("UPDATE tickets SET status=?,resolved_at=? WHERE id=?", (status, when if status == "Resolved" else None, ticket_id))
            db.execute("INSERT INTO ticket_events(ticket_id,event,note,created_at) VALUES(?,?,?,?)", (ticket_id, "Status: " + row["status"] + " → " + status, note.strip(), when))
        return self.ticket(ticket_id)

    def dashboard(self):
        # Aggregation is not capped by the paginated incident queue.
        with self.connect() as db:
            stats = db.execute("""SELECT COUNT(*) AS total,
                SUM(CASE WHEN status != 'Resolved' THEN 1 ELSE 0 END) AS open,
                SUM(CASE WHEN status = 'Resolved' THEN 1 ELSE 0 END) AS resolved,
                SUM(CASE WHEN status != 'Resolved' AND due_at < ? THEN 1 ELSE 0 END) AS breached,
                SUM(CASE WHEN status != 'Resolved' AND priority = 'P1' THEN 1 ELSE 0 END) AS p1_open
                FROM tickets""", (iso(utcnow()),)).fetchone()
            asset_total = db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        return {"assets": asset_total, "open": stats["open"] or 0,
                "resolved": stats["resolved"] or 0, "breached": stats["breached"] or 0,
                "p1_open": stats["p1_open"] or 0, "total": stats["total"],
                "priority_rules_hours": PRIORITY_HOURS, "recent": self.tickets(limit=6)}
