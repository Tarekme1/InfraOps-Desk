# InfraOps Desk

[![Smoke and API tests](https://github.com/Tarekme1/InfraOps-Desk/actions/workflows/tests.yml/badge.svg)](https://github.com/Tarekme1/InfraOps-Desk/actions/workflows/tests.yml)

Local IT incident and asset-management demonstration built around a small, testable Python API and responsive employee and operator interfaces. It uses synthetic accounts and requires no external services or third-party Python packages.

![Operations overview — fictional demo data](docs/overview.png)

*Screenshot: earlier local demo view. All incident, asset and SLA values are fictional.*

## Run locally

Requires Python 3.10 or newer.

```bash
python app.py
```

Before starting, provision synthetic roles with environment variables. In PowerShell:

```powershell
$env:MIHWAR_EMPLOYEE_USER = "employee-demo"
$env:MIHWAR_EMPLOYEE_PASSWORD = "replace-with-a-local-demo-password"
$env:MIHWAR_TECH_USER = "tech-demo"
$env:MIHWAR_TECH_PASSWORD = "replace-with-a-local-demo-password"
$env:MIHWAR_ADMIN_USER = "admin-demo"
$env:MIHWAR_ADMIN_PASSWORD = "replace-with-a-local-demo-password"
py -3 app.py
```

Open **http://127.0.0.1:8765/** for the technician/admin workspace and **http://127.0.0.1:8765/employee** for the Arabic RTL employee portal. Account credentials are upserted at startup and only password hashes are stored. Do not commit passwords. On the first run, SQLite is initialized in `data/infraops.sqlite` with six fictional assets and six sample incidents. The schema migration retains existing incidents and supports employee tickets without a linked asset.

## Test

```bash
python -m unittest discover -s tests -v
```

The test suite exercises priority rules, input validation, HTTP endpoints, persistence, assignment and status history, employee ownership isolation, role checks, CSRF, legacy schema migration, data export, access to unlisted paths, response security headers, and aggregate counts. GitHub Actions runs this suite on Python 3.10, 3.12 and 3.13. See [verification notes](docs/VERIFICATION.md) for observed results and limitations.

## Features

- Incident intake linked to a small device and infrastructure inventory.
- Arabic RTL employee portal for creating, tracking, and requesting reopening of owned tickets.
- Synthetic employee, technician, and administrator accounts with role checks and session-based CSRF protection.
- Admin assignment to configured technicians; technician view includes their assigned work and the unassigned queue.
- Impact + urgency priority calculation (P1–P4) with illustrative resolution targets.
- Open, in-progress and resolved states with an append-only action timeline.
- Dashboard counts, deadline breach indicators, filters and CSV export.
- Responsive interface, SQLite persistence and a dependency-free standard-library API.

## Project structure

| Path | Responsibility |
| --- | --- |
| `app.py` | Local HTTP server, routes and response handling |
| `store.py` | SQLite schema, incident business rules, persistence |
| `static/` | HTML, CSS and browser-side JavaScript |
| `tests/` | Unit and HTTP integration tests |
| `docs/` | UI screenshot and design notes |

## API overview

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Local readiness check |
| POST | `/api/login` | Authenticate a configured synthetic user |
| GET | `/employee` | Arabic employee portal |
| GET/POST | `/api/employee/tickets` | List or create only the signed-in employee's tickets |
| POST | `/api/employee/tickets/{id}/reopen` | Reopen an owned resolved ticket |
| PATCH | `/api/tickets/{id}/assign` | Admin assigns a configured technician |
| GET | `/api/assets` | Fictional assets |
| GET | `/api/dashboard` | Incident totals and recent cases |
| GET | `/api/tickets?status=&q=` | Filter incidents |
| GET | `/api/tickets/{id}` | Incident and history |
| POST | `/api/tickets` | Create incident |
| PATCH | `/api/tickets/{id}` | Change status, append action note |
| GET | `/api/export.csv` | Download incident list |

Create an incident with JSON including `title`, `asset_id`, `impact`, `urgency`, and optional `description`. Impact and urgency are integers from 1 to 3. A resolution transition requires a non-empty note. The employee portal also supports a self-service reopen request for resolved tickets.

## Scope and limitations

**This remains a local portfolio exercise, not a production service desk or actual employer deployment.** All data and service targets are fictional. The server intentionally binds to `127.0.0.1`. The new local authentication, roles, session cookies, CSRF checks, employee ownership and migrations are demonstration safeguards, not a production security certification. TLS, login throttling, operational backup and restore, notification delivery, business-hour SLA calendars, and an independent security review remain before real data or any network exposure. Do not expose it directly to the internet or use real employee, customer or factory information. The priority matrix is a demonstration rule, not a representation of the ITIL framework.

See [architecture and design choices](docs/ARCHITECTURE.md) and [security notes](SECURITY.md).
