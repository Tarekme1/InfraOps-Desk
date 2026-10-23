# Architecture and design decisions

InfraOps Desk uses a small standard-library Python service, a local SQLite database and static browser clients. The development service is loopback-only and can provision synthetic employee, technician and administrator accounts from environment variables.

The browser calls the JSON API; the HTTP layer authenticates sessions, checks roles and CSRF tokens, validates request structure, and the store owns domain rules. Records are stored in `assets`, `users`, `sessions`, `login_attempts`, `tickets`, `ticket_owners` and `ticket_events`. Passwords use salted PBKDF2-HMAC-SHA256. Session tokens are random, only their SHA-256 hashes are stored, and sessions expire after eight hours. Failed login buckets are keyed by hashes of normalized username/source and source alone; five failures per username/source or 20 per source in 15 minutes cause a 15-minute lockout. Ticket events preserve creation, assignment, status and work-note history; internal notes use an event namespace filtered by employee APIs. Employee ownership is stored separately from ticket fields and is derived from the authenticated session.

The app remains loopback-bound. Behind a same-host TLS proxy, `MIHWAR_SECURE_COOKIES=1` marks cookies Secure. Forwarded client addresses are used for login throttling only when the direct peer equals the explicitly configured `MIHWAR_TRUSTED_PROXY_IP`, and the forwarded header contains exactly one valid IP address.

Existing databases are migrated transactionally when the former required asset reference must become optional. The migration preserves ticket and event IDs/history and adds category/assignment fields; a regression test checks row preservation and SQLite foreign-key integrity.

## Priority rules

The supplied impact and urgency each range from 1 (low) to 3 (high). A combined score of 6 maps to P1; 5 to P2; 4 to P3; and 2–3 to P4. Demo target times are 1, 4, 24 and 72 hours respectively. These are elapsed-hour **illustrations**, not customer contract SLAs.

## Behavior and trade-offs

- Each request creates its own SQLite connection and commits or rolls back its transaction.
- Parameterized SQL avoids assembling untrusted inputs into database query values.
- Dashboard counts use SQL aggregation and are not limited by the 250-row incident view.
- Employee list/detail/reopen operations filter by the authenticated owner. Technicians see unassigned work and their own assignments; administrators see all tickets and can assign a configured technician.
- A resolved ticket may be reopened only by its employee owner. Technician status changes append notes to the visible event timeline.
- Technicians/admins can add separate internal and employee-visible work notes. Internal notes are filtered in both employee list and detail responses.
- CSV values beginning with spreadsheet formula operators are prefixed for safer opening in spreadsheet software.
- The local demo still lacks TLS, a secure account-management interface, scheduled/off-site backups, operational monitoring and independent security review. These are required before real data or network exposure.

## Backup and restore

`scripts/backup_db.py` uses SQLite's online backup API, runs `integrity_check` and `foreign_key_check`, refuses backup overwrite, and restores through a verified temporary file. When replacing an existing database it first writes a verified timestamped safety copy. Restore requires the application to be stopped so SQLite file handles are closed. This proves a local functional round trip only; off-site storage, encryption, schedules, retention, recovery objectives and restore drills remain deployment responsibilities.
