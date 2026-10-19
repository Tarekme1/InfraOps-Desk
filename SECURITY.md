# Security and data handling

This repository intentionally uses fictional demonstration data, never live factory, employee or customer records.

## Development safeguards

- The HTTP server is bound to the loopback interface `127.0.0.1` by default.
- New tickets and status updates validate request JSON, payload size and value ranges.
- Database queries use parameter placeholders.
- User-controlled text is escaped before being inserted into the browser's rendered HTML.
- CSV values starting with spreadsheet formula characters receive a protective prefix.
- Runtime SQLite files, temporary files and secrets are excluded by `.gitignore`.

## Not intended for production

There are no user accounts, access controls, CSRF defenses or TLS termination. Do not expose the app on a public interface or run it with sensitive real-world data. A production implementation would require an authenticated service boundary and an independent security review.

If you find a security issue, report it privately rather than opening a public issue containing sensitive details.
