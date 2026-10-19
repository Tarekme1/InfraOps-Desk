# Architecture and design decisions

InfraOps Desk uses a small standard-library Python service, a local SQLite database and a static browser client. Keeping the deployment local makes the application reproducible without requiring accounts, API keys, database services or hosting.

The browser calls the JSON API; the HTTP layer validates request structure and the store owns all domain rules. Records are stored in three tables: `assets`, `tickets`, and `ticket_events`. Ticket events are appended for status transitions, rather than overwriting historical notes.

## Priority rules

The supplied impact and urgency each range from 1 (low) to 3 (high). A combined score of 6 maps to P1; 5 to P2; 4 to P3; and 2–3 to P4. Demo target times are 1, 4, 24 and 72 hours respectively. These are elapsed-hour **illustrations**, not customer contract SLAs.

## Behavior and trade-offs

- Each request creates its own SQLite connection and commits or rolls back its transaction.
- Parameterized SQL avoids assembling untrusted inputs into database query values.
- Dashboard counts use SQL aggregation and are not limited by the 250-row incident view.
- Incidents retain an action history, but this does not provide identity-backed auditability because there are no user accounts.
- CSV values beginning with spreadsheet formula operators are prefixed for safer opening in spreadsheet software.
- For a real multi-user deployment, add authentication, permissions, controlled state transitions, database migrations, observability, a tested backup policy and service-level calendars before considering hosting.
