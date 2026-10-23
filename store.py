"""SQLite persistence and business rules for the MIHWAR IT operations workspace."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import hashlib
import hmac
import secrets

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
                asset_id INTEGER REFERENCES assets(id),
                assigned_to INTEGER REFERENCES users(id),
                category TEXT NOT NULL DEFAULT 'IT',
                impact INTEGER NOT NULL CHECK(impact BETWEEN 1 AND 3),
                urgency INTEGER NOT NULL CHECK(urgency BETWEEN 1 AND 3),
                priority TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Open',
                created_at TEXT NOT NULL,
                due_at TEXT NOT NULL,
                resolved_at TEXT
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('employee','technician','admin'))
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash BLOB PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                csrf_token TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS login_attempts (
                bucket TEXT PRIMARY KEY,
                failures INTEGER NOT NULL,
                window_started_at TEXT NOT NULL,
                locked_until TEXT
            );
            CREATE TABLE IF NOT EXISTS ticket_owners (
                ticket_id INTEGER PRIMARY KEY REFERENCES tickets(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS ticket_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL REFERENCES tickets(id),
                actor_id INTEGER REFERENCES users(id),
                event TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tickets_status_due ON tickets(status, due_at);
            CREATE INDEX IF NOT EXISTS idx_events_ticket ON ticket_events(ticket_id, id);
            CREATE INDEX IF NOT EXISTS idx_ticket_owners_user ON ticket_owners(user_id,ticket_id);
            """)
            total = db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
            if total == 0:
                # A realistic, internally consistent sample scenario for review. Dates
                # are illustrative and must not be represented as actual plant records.
                db.executemany("INSERT INTO assets(asset_tag,name,category,location) VALUES(?,?,?,?)", [
                    ("IT-SRV-01", "Production Systems Server", "Server", "Control Room"),
                    ("IT-SW-01", "Core Network Switch", "Networking", "Main Comms Rack"),
                    ("IT-NVR-01", "Security Video Recorder", "Surveillance", "Security Office"),
                    ("IT-WS-01", "Quality Lab Workstation", "Endpoint", "Quality Laboratory"),
                    ("IT-PRN-01", "Dispatch Label Printer", "Peripheral", "Dispatch Area"),
                    ("IT-AP-01", "Warehouse Wireless Access Point", "Networking", "Warehouse Zone B"),
                    ("IT-HMI-01", "Packaging Line HMI", "Endpoint", "Packaging Line 2"),
                    ("IT-SCAN-01", "Receiving Barcode Scanner", "Peripheral", "Receiving Bay"),
                    ("IT-NAS-01", "Engineering File Storage", "Storage", "Control Room"),
                    ("IT-FW-01", "Site Perimeter Firewall", "Networking", "Main Comms Rack"),
                    ("IT-UPS-01", "Control Room UPS", "Power", "Control Room"),
                    ("IT-CAM-02", "Loading Bay Camera", "Surveillance", "Loading Bay"),
                ])
                # Fixed dates make the sample timeline stable and repeatable.
                samples = [
                    ("Label queue delayed at dispatch", "Dispatch label jobs remained queued after the print service stopped responding. Queue cleared and a test label was verified.", 5, "Printing", 2, 2, "Resolved", "2026-03-03T07:42:00Z", 1.8),
                    ("Warehouse wireless coverage drop", "Handheld devices lost connectivity near warehouse zone B during a shift change. Access point channel utilization was reviewed.", 6, "Network", 2, 2, "Resolved", "2026-03-08T11:16:00Z", 3.2),
                    ("Quality workstation storage warning", "The quality lab workstation reported low disk space while exporting inspection records. Temporary files were reviewed and cleared.", 4, "Endpoint", 2, 1, "Resolved", "2026-03-14T09:05:00Z", 4.1),
                    ("Receiving scanner battery not charging", "The receiving barcode scanner did not charge in its dock. Dock power and battery condition were checked.", 8, "Endpoint", 1, 2, "Resolved", "2026-03-22T06:48:00Z", 2.4),
                    ("Core switch interface errors", "Interface counters on the main comms rack showed intermittent errors. Patch lead and port health were inspected.", 2, "Network", 3, 2, "Resolved", "2026-04-02T13:21:00Z", 2.7),
                    ("Engineering share access interrupted", "Engineering clients could not reconnect to the shared project folder after a network maintenance window. Name resolution and share permissions were checked.", 9, "Storage", 2, 2, "Resolved", "2026-04-11T08:32:00Z", 3.6),
                    ("Packaging HMI login delay", "Operator sign-in at packaging line 2 took longer than usual. Device connectivity and authentication service response were reviewed.", 7, "Operations IT", 3, 2, "Resolved", "2026-04-19T05:54:00Z", 2.1),
                    ("Perimeter firewall backup check", "The scheduled configuration backup did not appear in the expected archive. Job status and destination capacity were verified.", 10, "Security", 2, 1, "Resolved", "2026-04-28T15:10:00Z", 5.5),
                    ("Security recorder disk threshold alert", "The recorder reported that available storage had crossed its configured warning threshold. Retention status and disk health were reviewed.", 3, "Surveillance", 2, 2, "Resolved", "2026-05-06T10:44:00Z", 3.1),
                    ("UPS maintenance notification", "The control room UPS reported a battery maintenance notification. Self-test results were captured for facilities follow-up.", 11, "Power", 2, 1, "Resolved", "2026-05-15T07:20:00Z", 6.2),
                    ("Dispatch printer calibration request", "Label alignment drift was reported on the dispatch printer. Calibration output was reviewed with the operator.", 5, "Printing", 1, 2, "Resolved", "2026-05-27T12:03:00Z", 2.0),
                    ("Core services response slowdown", "Several internal applications responded slowly during the morning shift. Server resource utilization and service logs were checked.", 1, "Server", 3, 2, "Resolved", "2026-06-04T06:37:00Z", 3.3),
                    ("Loading bay camera feed unavailable", "The loading bay camera feed was unavailable in the security client. Link status and recorder channel assignment were checked.", 12, "Surveillance", 2, 2, "Resolved", "2026-06-13T14:25:00Z", 2.8),
                    ("Warehouse access point reboot observed", "A warehouse access point restarted unexpectedly. Uplink stability and device event history were reviewed.", 6, "Network", 2, 2, "Resolved", "2026-06-25T04:58:00Z", 3.9),
                    ("Quality export folder permission request", "A quality team member requested access to the controlled inspection export folder. The request was checked against the approved role list.", 4, "Access", 1, 1, "Resolved", "2026-07-03T09:40:00Z", 7.0),
                    ("Engineering storage capacity review", "Shared engineering storage approached its planning threshold. Usage by top-level folder was reviewed for capacity planning.", 9, "Storage", 2, 2, "Resolved", "2026-07-17T11:12:00Z", 4.4),
                    ("Packaging line HMI time offset", "The packaging HMI clock differed from the site time source. Synchronization status was checked after a scheduled restart.", 7, "Operations IT", 2, 2, "Resolved", "2026-07-29T05:36:00Z", 3.0),
                    ("Receiving handheld cannot sync", "A receiving handheld completed scans locally but did not synchronize its latest batch. Wireless reachability and application status were checked.", 8, "Endpoint", 2, 2, "Resolved", "2026-08-07T07:58:00Z", 2.9),
                    ("Main comms rack temperature alert", "An environmental sensor reported elevated rack temperature. Airflow and room cooling status were escalated for facilities review.", 2, "Facilities IT", 3, 3, "Resolved", "2026-08-18T16:14:00Z", 0.7),
                    ("Firewall rule review request", "A temporary outbound rule was submitted for review with a stated business owner and expiry date. Approval evidence was requested before change.", 10, "Security", 2, 2, "Resolved", "2026-08-26T08:20:00Z", 5.6),
                    ("Dispatch label service intermittent", "Two dispatch stations reported intermittent label delays. Service availability and printer connectivity are being monitored.", 5, "Printing", 2, 3, "In Progress", "2026-09-04T06:31:00Z", None),
                    ("Quality lab wireless authentication", "A lab workstation intermittently failed wireless authentication after its credential rotation. Device identity and policy status are under review.", 4, "Network", 2, 2, "Resolved", "2026-09-12T10:02:00Z", 3.8),
                    ("Production systems backup verification", "The latest backup job completed with a warning. Restore-point integrity and available capacity are being checked.", 1, "Backup", 3, 2, "In Progress", "2026-09-23T13:46:00Z", None),
                    ("Loading bay camera image quality", "The loading bay image appears degraded during low-light hours. Lens condition and camera exposure settings were requested for inspection.", 12, "Surveillance", 1, 2, "Open", "2026-10-02T18:10:00Z", None),
                    ("Warehouse handheld roaming delay", "A handheld device paused while moving between warehouse zones. Roaming behavior and access point coverage are being assessed.", 6, "Network", 2, 2, "In Progress", "2026-10-09T07:24:00Z", None),
                    ("Engineering storage growth alert", "A capacity alert was raised for the engineering share. Current growth rate and retention needs are being reviewed.", 9, "Storage", 2, 2, "Open", "2026-10-16T11:05:00Z", None),
                    ("Control room UPS self-test warning", "A self-test warning was logged by the control room UPS. Facilities inspection is pending and no power interruption is reported.", 11, "Power", 2, 2, "Open", "2026-10-21T05:50:00Z", None),
                ]
                for title, desc, asset_id, category, impact, urgency, status, created_text, resolution_hours in samples:
                    created = as_datetime(created_text)
                    priority = determine_priority(impact, urgency)
                    due = created + timedelta(hours=PRIORITY_HOURS[priority])
                    resolved = iso(created + timedelta(hours=resolution_hours)) if resolution_hours is not None else None
                    cur = db.execute("""INSERT INTO tickets(title,description,asset_id,category,impact,urgency,priority,status,created_at,due_at,resolved_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (title, desc, asset_id, category, impact, urgency, priority, status, created_text, iso(due), resolved))
                    db.execute("INSERT INTO ticket_events(ticket_id,event,note,created_at) VALUES(?,?,?,?)",
                               (cur.lastrowid, "Created", "Sample scenario record created for product review; not a record of plant operations.", created_text))
                    if status == "Resolved":
                        db.execute("INSERT INTO ticket_events(ticket_id,event,note,created_at) VALUES(?,?,?,?)",
                                   (cur.lastrowid, "Status: Open → Resolved", "Sample scenario: the described check was completed and recorded.", resolved))
        self._migrate_legacy_ticket_schema()
        with self.connect() as db:
            event_columns = {row[1] for row in db.execute("PRAGMA table_info(ticket_events)")}
            if "actor_id" not in event_columns:
                db.execute("ALTER TABLE ticket_events ADD COLUMN actor_id INTEGER REFERENCES users(id)")

    def _migrate_legacy_ticket_schema(self):
        """Allow unlinked employee reports while preserving the original local demo rows."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            info = conn.execute("PRAGMA table_info(tickets)").fetchall()
            columns = {row[1]: row for row in info}
            if "asset_id" not in columns:
                return
            needs_rebuild = bool(columns["asset_id"][3])
            needs_category = "category" not in columns
            needs_assigned = "assigned_to" not in columns
            if not needs_rebuild and not needs_category and not needs_assigned:
                return
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""CREATE TABLE tickets_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                asset_id INTEGER REFERENCES assets(id),
                assigned_to INTEGER REFERENCES users(id),
                category TEXT NOT NULL DEFAULT 'IT',
                impact INTEGER NOT NULL CHECK(impact BETWEEN 1 AND 3),
                urgency INTEGER NOT NULL CHECK(urgency BETWEEN 1 AND 3),
                priority TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Open',
                created_at TEXT NOT NULL,
                due_at TEXT NOT NULL,
                resolved_at TEXT
            )""")
            fields = ["id", "title", "description", "asset_id"]
            assigned_expr = "assigned_to" if "assigned_to" in columns else "NULL"
            category_expr = "category" if "category" in columns else "'IT'"
            fields.extend(["impact", "urgency", "priority", "status", "created_at", "due_at", "resolved_at"])
            conn.execute(f"INSERT INTO tickets_new({','.join(fields)},assigned_to,category) SELECT {','.join(fields)},{assigned_expr},{category_expr} FROM tickets")
            conn.execute("DROP TABLE tickets")
            conn.execute("ALTER TABLE tickets_new RENAME TO tickets")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status_due ON tickets(status,due_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ticket ON ticket_events(ticket_id,id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ticket_owners_user ON ticket_owners(user_id,ticket_id)")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def hash_password(password, salt=None):
        salt = salt or secrets.token_bytes(16)
        return salt, hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 240_000)

    def ensure_user(self, username, password, role):
        if not isinstance(username, str) or not 1 <= len(username.strip()) <= 80:
            raise ValueError("Username must be 1 to 80 characters")
        if not isinstance(password, str) or not 12 <= len(password) <= 256:
            raise ValueError("Demo password must be 12 to 256 characters")
        if role not in ("employee", "technician", "admin"):
            raise ValueError("Invalid role")
        username = username.strip()
        salt, password_hash = self.hash_password(password)
        with self.connect() as db:
            db.execute("""INSERT INTO users(username,password_salt,password_hash,role) VALUES(?,?,?,?)
                ON CONFLICT(username) DO UPDATE SET password_salt=excluded.password_salt,
                password_hash=excluded.password_hash,role=excluded.role""", (username, salt, password_hash, role))

    def authenticate(self, username, password):
        with self.connect() as db:
            user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not user:
            # Keep the unknown-user path computationally similar to a failed password check.
            self.hash_password(password, b"m1hwar-demo-salt")
            return None
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), user["password_salt"], 240_000)
        return dict(user) if hmac.compare_digest(candidate, user["password_hash"]) else None

    @staticmethod
    def _login_buckets(username, remote_address):
        identity = (username.strip().casefold() + "\0" + remote_address).encode("utf-8", "replace")
        source = ("source\0" + remote_address).encode("utf-8", "replace")
        return hashlib.sha256(identity).hexdigest(), hashlib.sha256(source).hexdigest()

    def login_allowed(self, username, remote_address):
        buckets = self._login_buckets(username, remote_address)
        with self.connect() as db:
            rows = db.execute("SELECT locked_until FROM login_attempts WHERE bucket IN (?,?)", buckets).fetchall()
            remaining = [ (as_datetime(row["locked_until"]) - utcnow()).total_seconds()
                          for row in rows if row["locked_until"] ]
            if any(seconds > 0 for seconds in remaining):
                return False, max(1, int(max(remaining) + 0.999))
            db.execute("DELETE FROM login_attempts WHERE bucket IN (?,?) AND locked_until IS NOT NULL", buckets)
            return True, 0

    def record_login_failure(self, username, remote_address):
        buckets = self._login_buckets(username, remote_address)
        now = utcnow()
        window = now - timedelta(minutes=15)
        with self.connect() as db:
            db.execute("DELETE FROM login_attempts WHERE window_started_at<?", (iso(now - timedelta(days=1)),))
            for index, bucket in enumerate(buckets):
                row = db.execute("SELECT failures,window_started_at FROM login_attempts WHERE bucket=?", (bucket,)).fetchone()
                count = row["failures"] + 1 if row and as_datetime(row["window_started_at"]) > window else 1
                started = row["window_started_at"] if count > 1 else iso(now)
                threshold = 5 if index == 0 else 20
                locked = iso(now + timedelta(minutes=15)) if count >= threshold else None
                db.execute("INSERT INTO login_attempts(bucket,failures,window_started_at,locked_until) VALUES(?,?,?,?) "
                           "ON CONFLICT(bucket) DO UPDATE SET failures=excluded.failures,window_started_at=excluded.window_started_at,locked_until=excluded.locked_until",
                           (bucket, count, started, locked))

    def clear_login_failures(self, username, remote_address):
        with self.connect() as db:
            db.execute("DELETE FROM login_attempts WHERE bucket=?", (self._login_buckets(username, remote_address)[0],))

    def create_session(self, user_id, ttl_hours=8):
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        expires = iso(utcnow() + timedelta(hours=ttl_hours))
        token_hash = hashlib.sha256(token.encode("ascii")).digest()
        with self.connect() as db:
            db.execute("INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at) VALUES(?,?,?,?)",
                       (token_hash, user_id, csrf, expires))
        return token, csrf, expires

    def get_session(self, token):
        if not token:
            return None
        digest = hashlib.sha256(token.encode("ascii", "ignore")).digest()
        with self.connect() as db:
            row = db.execute("""SELECT s.csrf_token,s.expires_at,u.id,u.username,u.role FROM sessions s
                JOIN users u ON u.id=s.user_id WHERE s.token_hash=?""", (digest,)).fetchone()
        if not row or as_datetime(row["expires_at"]) <= utcnow():
            return None
        return dict(row)

    def delete_session(self, token):
        digest = hashlib.sha256(token.encode("ascii", "ignore")).digest()
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (digest,))

    def create_employee_ticket(self, user_id, payload):
        if not isinstance(payload, dict):
            raise ValueError("Body must be a JSON object")
        title, desc = payload.get("title"), payload.get("description", "")
        aid = payload.get("asset_id")
        if not isinstance(title, str) or not 5 <= len(title.strip()) <= 120:
            raise ValueError("Title must be between 5 and 120 characters")
        if not isinstance(desc, str) or len(desc) > 1500:
            raise ValueError("Description too long")
        if aid is not None and (type(aid) is not int or aid < 1):
            raise ValueError("Invalid asset selection")
        category = payload.get("category", "IT")
        if not isinstance(category, str) or len(category.strip()) > 80:
            raise ValueError("Invalid category")
        priority = determine_priority(payload.get("impact"), payload.get("urgency"))
        created = utcnow()
        due = created + timedelta(hours=PRIORITY_HOURS[priority])
        with self.connect() as db:
            if aid is not None and not db.execute("SELECT 1 FROM assets WHERE id=?", (aid,)).fetchone():
                raise ValueError("Unknown asset")
            cur = db.execute("""INSERT INTO tickets(title,description,asset_id,category,impact,urgency,priority,status,created_at,due_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""", (title.strip(), desc.strip(), aid, category.strip(), payload["impact"], payload["urgency"], priority, "Open", iso(created), iso(due)))
            ticket_id = cur.lastrowid
            db.execute("INSERT INTO ticket_owners(ticket_id,user_id) VALUES(?,?)", (ticket_id, user_id))
            db.execute("INSERT INTO ticket_events(ticket_id,actor_id,event,note,created_at) VALUES(?,?,?,?,?)", (ticket_id, user_id, "Created", "", iso(created)))
        return self.ticket(ticket_id)

    def employee_tickets(self, user_id):
        with self.connect() as db:
            ids = [row[0] for row in db.execute("SELECT ticket_id FROM ticket_owners WHERE user_id=? ORDER BY ticket_id DESC", (user_id,))]
        tickets = [self.ticket(ticket_id) for ticket_id in ids]
        for ticket in tickets:
            ticket["events"] = [event for event in ticket["events"] if not event["event"].startswith("Internal:")]
        return tickets

    def employee_ticket(self, user_id, ticket_id):
        with self.connect() as db:
            owner = db.execute("SELECT 1 FROM ticket_owners WHERE ticket_id=? AND user_id=?", (ticket_id, user_id)).fetchone()
        if not owner:
            raise LookupError("Ticket not found")
        return self.ticket(ticket_id)

    def technician_ticket(self, user_id, ticket_id):
        ticket = self.ticket(ticket_id)
        if ticket.get("assigned_to") not in (None, user_id):
            raise LookupError("Ticket not found")
        return ticket

    def logout(self, token):
        self.delete_session(token)

    def technicians(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT id,username FROM users WHERE role='technician' ORDER BY username")]

    def assign_ticket(self, ticket_id, technician_id, actor_id):
        with self.connect() as db:
            ticket = db.execute("SELECT id FROM tickets WHERE id=?", (ticket_id,)).fetchone()
            user = db.execute("SELECT username FROM users WHERE id=? AND role='technician'", (technician_id,)).fetchone()
            actor = db.execute("SELECT username FROM users WHERE id=?", (actor_id,)).fetchone()
            if not ticket: raise LookupError("Ticket not found")
            if not user: raise ValueError("Choose a valid technician")
            when = iso(utcnow())
            db.execute("UPDATE tickets SET assigned_to=? WHERE id=?", (technician_id, ticket_id))
            db.execute("INSERT INTO ticket_events(ticket_id,actor_id,event,note,created_at) VALUES(?,?,?,?,?)",
                       (ticket_id, actor_id, "Assigned", f"Assigned to {user['username']} by {actor['username']}", when))

    def reopen_employee_ticket(self, user_id, ticket_id):
        with self.connect() as db:
            owner = db.execute("SELECT 1 FROM ticket_owners WHERE ticket_id=? AND user_id=?", (ticket_id, user_id)).fetchone()
            ticket = db.execute("SELECT status FROM tickets WHERE id=?", (ticket_id,)).fetchone()
            if not owner or not ticket:
                raise LookupError("Ticket not found")
            if ticket["status"] != "Resolved":
                raise ValueError("Only resolved tickets can be reopened")
            when = iso(utcnow())
            db.execute("UPDATE tickets SET status='Open',resolved_at=NULL WHERE id=?", (ticket_id,))
            db.execute("INSERT INTO ticket_events(ticket_id,actor_id,event,note,created_at) VALUES(?,?,?,?,?)",
                       (ticket_id, user_id, "Reopened", "Employee requested the ticket be reopened", when))
        return self.ticket(ticket_id)

    def assets(self):
        with self.connect() as db:
            return [dict(x) for x in db.execute("SELECT * FROM assets ORDER BY asset_tag")]

    @staticmethod
    def _decorate(ticket):
        t = dict(ticket)
        t["breached"] = t["status"] != "Resolved" and as_datetime(t["due_at"]) < utcnow()
        return t

    def tickets(self, status=None, search=None, limit=250, assigned_user=None):
        sql = """SELECT t.*,a.asset_tag,a.name AS asset_name,a.category AS asset_category
            ,u.username AS assigned_username FROM tickets t LEFT JOIN assets a ON a.id=t.asset_id
            LEFT JOIN users u ON u.id=t.assigned_to WHERE 1=1"""
        params = []
        if assigned_user is not None:
            sql += " AND (t.assigned_to=? OR t.assigned_to IS NULL)"
            params.append(assigned_user)
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

    def create_ticket(self, payload, actor_id=None):
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
        category = payload.get("category", "IT")
        if not isinstance(category, str) or len(category.strip()) > 80:
            raise ValueError("Invalid category")
        priority = determine_priority(payload.get("impact"), payload.get("urgency"))
        created = utcnow()
        due = created + timedelta(hours=PRIORITY_HOURS[priority])
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM assets WHERE id=?", (aid,)).fetchone():
                raise ValueError("Unknown asset")
            cur = db.execute("""INSERT INTO tickets(title,description,asset_id,category,impact,urgency,priority,status,created_at,due_at)
              VALUES(?,?,?,?,?,?,?,?,?,?)""", (title.strip(), desc.strip(), aid, category.strip(), payload["impact"], payload["urgency"], priority, "Open", iso(created), iso(due)))
            ticket_id = cur.lastrowid
            db.execute("INSERT INTO ticket_events(ticket_id,actor_id,event,note,created_at) VALUES(?,?,?,?,?)", (ticket_id, actor_id, "Created", "", iso(created)))
        return self.ticket(ticket_id)

    def ticket(self, ticket_id):
        with self.connect() as db:
            row = db.execute("""SELECT t.*,a.asset_tag,a.name AS asset_name,a.category AS asset_category,u.username AS assigned_username
                              FROM tickets t LEFT JOIN assets a ON a.id=t.asset_id LEFT JOIN users u ON u.id=t.assigned_to WHERE t.id=?""", (ticket_id,)).fetchone()
            if row is None:
                raise LookupError("Ticket not found")
            ticket = self._decorate(row)
            ticket["events"] = [dict(x) for x in db.execute("""SELECT e.event,e.note,e.created_at,e.actor_id,u.username AS actor_username
                FROM ticket_events e LEFT JOIN users u ON u.id=e.actor_id WHERE e.ticket_id=? ORDER BY e.id""", (ticket_id,))]
            return ticket

    def change_status(self, ticket_id, payload, actor_id=None):
        if not isinstance(payload, dict):
            raise ValueError("Body must be a JSON object")
        status, note = payload.get("status"), payload.get("note", "")
        if status not in VALID_STATUSES:
            raise ValueError("Invalid status")
        if not isinstance(note, str) or len(note) > 500:
            raise ValueError("Note must be 500 characters or fewer")
        if status == "Resolved" and not note.strip():
            raise ValueError("A resolution note is required before resolving a ticket")
        with self.connect() as db:
            row = db.execute("SELECT status FROM tickets WHERE id=?", (ticket_id,)).fetchone()
            if row is None:
                raise LookupError("Ticket not found")
            if row["status"] == status:
                raise ValueError("Ticket already has this status")
            when = iso(utcnow())
            db.execute("UPDATE tickets SET status=?,resolved_at=? WHERE id=?", (status, when if status == "Resolved" else None, ticket_id))
            db.execute("INSERT INTO ticket_events(ticket_id,actor_id,event,note,created_at) VALUES(?,?,?,?,?)", (ticket_id, actor_id, "Status: " + row["status"] + " → " + status, note.strip(), when))
        return self.ticket(ticket_id)

    def add_ticket_note(self, ticket_id, actor_id, note, internal=False):
        if not isinstance(note, str) or not note.strip() or len(note) > 500:
            raise ValueError("Note must contain 1-500 characters")
        if type(internal) is not bool:
            raise ValueError("Internal flag must be boolean")
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM tickets WHERE id=?", (ticket_id,)).fetchone():
                raise LookupError("Ticket not found")
            db.execute("INSERT INTO ticket_events(ticket_id,actor_id,event,note,created_at) VALUES(?,?,?,?,?)",
                (ticket_id, actor_id, "Internal: Note" if internal else "Update", note.strip(), iso(utcnow())))
        return self.ticket(ticket_id)

    def dashboard(self, assigned_user=None):
        # Aggregation is not capped by the paginated incident queue.
        with self.connect() as db:
            where = " WHERE assigned_to=? OR assigned_to IS NULL" if assigned_user is not None else ""
            params = [assigned_user] if assigned_user is not None else []
            stats = db.execute(f"""SELECT COUNT(*) AS total,
                SUM(CASE WHEN status != 'Resolved' THEN 1 ELSE 0 END) AS open,
                SUM(CASE WHEN status = 'Resolved' THEN 1 ELSE 0 END) AS resolved,
                SUM(CASE WHEN status != 'Resolved' AND due_at < ? THEN 1 ELSE 0 END) AS breached,
                SUM(CASE WHEN status != 'Resolved' AND priority = 'P1' THEN 1 ELSE 0 END) AS p1_open
                FROM tickets""" + where, ([iso(utcnow())] + params)).fetchone()
            asset_total = db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        return {"assets": asset_total, "open": stats["open"] or 0,
                "resolved": stats["resolved"] or 0, "breached": stats["breached"] or 0,
                "p1_open": stats["p1_open"] or 0, "total": stats["total"],
                "priority_rules_hours": PRIORITY_HOURS, "recent": self.tickets(limit=6, assigned_user=assigned_user)}

