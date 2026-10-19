# InfraOps Desk

Local IT incident and asset-management demonstration built around a small, testable Python API and a responsive browser interface. No accounts, external services, or third-party packages are required.

![Operations overview — fictional demo data](docs/overview.png)

*Screenshot: earlier local demo view. All incident, asset and SLA values are fictional.*

## Run locally

Requires Python 3.10 or newer.

```bash
python app.py
```

Open **http://127.0.0.1:8765/**. On the first run, SQLite is initialized in `data/infraops.sqlite` with six **fictional assets** and six sample incidents. Delete the generated database to restart with the original fixtures, or run `python scripts/reset_demo.py` with the server stopped.

## Test

```bash
python -m unittest discover -s tests -v
```

The 13 tests exercise priority rules, input validation, HTTP endpoints, persistence, incident status history, data export, access to unlisted paths, response security headers, and aggregate counts. The GitHub Actions workflow is configured to run the suite on supported Python versions after publication. See [verification notes](docs/VERIFICATION.md) for the last independently observed local result.

## Features

- Incident intake linked to a small device and infrastructure inventory.
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
| GET | `/api/assets` | Fictional assets |
| GET | `/api/dashboard` | Incident totals and recent cases |
| GET | `/api/tickets?status=&q=` | Filter incidents |
| GET | `/api/tickets/{id}` | Incident and history |
| POST | `/api/tickets` | Create incident |
| PATCH | `/api/tickets/{id}` | Change status, append action note |
| GET | `/api/export.csv` | Download incident list |

Create an incident with JSON including `title`, `asset_id`, `impact`, `urgency`, and optional `description`. Impact and urgency are integers from 1 to 3. Use a PATCH body with `status` and optional `note` to record an update.

## Scope and limitations

**This is a standalone portfolio exercise, not a production service desk or actual employer deployment.** All data and service targets are fictional. The server intentionally binds to `127.0.0.1`; it does not implement authentication, authorization, multi-user concurrency controls, notifications, business-hour SLA calendars or backups. Do not expose it directly to the internet or use real employee, customer or factory information. The priority matrix is a demonstration rule, not a representation of the ITIL framework.

See [architecture and design choices](docs/ARCHITECTURE.md) and [security notes](SECURITY.md).
