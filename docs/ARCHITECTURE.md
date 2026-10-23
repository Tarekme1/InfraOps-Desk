# Architecture and design decisions

InfraOps Desk uses a small standard-library Python service, a local SQLite database and static browser clients. The development service is loopback-only and can provision synthetic employee, technician and administrator accounts from environment variables.

The browser calls the JSON API; the HTTP layer authenticates sessions, checks roles and CSRF tokens, validates request structure, and the store owns domain rules. Records are stored in `assets`, `users`, `sessions`, `tickets`, `ticket_owners` and `ticket_events`. Passwords use salted PBKDF2-HMAC-SHA256. Session tokens are random, only their SHA-256 hashes are stored, and sessions expire after eight hours. Ticket events preserve creation, assignment and status history. Employee ownership is stored separately from ticket fields and is derived from the authenticated session.

Existing databases are migrated transactionally when the former required asset reference must become optional. The migration preserves ticket and event IDs/history and adds category/assignment fields; a regression test checks row preservation and SQLite foreign-key integrity.

## Priority rules

The supplied impact and urgency each range from 1 (low) to 3 (high). A combined score of 6 maps to P1; 5 to P2; 4 to P3; and 2–3 to P4. Demo target times are 1, 4, 24 and 72 hours respectively. These are elapsed-hour **illustrations**, not customer contract SLAs.

## Behavior and trade-offs

- Each request creates its own SQLite connection and commits or rolls back its transaction.
- Parameterized SQL avoids assembling untrusted inputs into database query values.
- Dashboard counts use SQL aggregation and are not limited by the 250-row incident view.
- Employee list/detail/reopen operations filter by the authenticated owner. Technicians see unassigned work and their own assignments; administrators see all tickets and can assign a configured technician.
- A resolved ticket may be reopened only by its employee owner. Technician status changes append notes to the visible event timeline.
- CSV values beginning with spreadsheet formula operators are prefixed for safer opening in spreadsheet software.
- The local demo still lacks TLS, login throttling, a secure account-management interface, tested backup/restore, operational monitoring and independent security review. These are required before real data or network exposure.
