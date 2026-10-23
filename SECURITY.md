# Security and data handling

This repository intentionally uses fictional demonstration data, never live factory, employee or customer records.

## Development safeguards

- The HTTP server is bound to the loopback interface `127.0.0.1` by default.
- New tickets and status updates validate request JSON, payload size and value ranges.
- Synthetic accounts are configured through environment variables; the application stores PBKDF2-HMAC-SHA256 password hashes, not plaintext passwords.
- Session identifiers are random, stored as hashes, sent in `HttpOnly; SameSite=Strict` cookies, and expire after eight hours.
- Mutating authenticated requests require a per-session CSRF token. Login uses a same-site double-submit token.
- Employee ticket reads and reopening are restricted to the owner. Technician/admin routes check roles; technicians see unassigned tickets and their own assigned tickets, while administrators can assign work and export.
- Content Security Policy and existing clickjacking, MIME-sniffing and referrer protections are applied to app pages and API responses.
- SQLite migrations preserve existing demo records while adding account, session, ownership and assignment fields.
- Database queries use parameter placeholders.
- User-controlled text is escaped before being inserted into the browser's rendered HTML.
- CSV values starting with spreadsheet formula characters receive a protective prefix.
- Runtime SQLite files, temporary files and secrets are excluded by `.gitignore`.

## Not intended for production

This remains a local demonstration and is not cleared for real employee, customer, factory or other sensitive data. There is no TLS termination, login throttling or lockout, tested operational backup/restore process, secure account administration UI, or independent security review. Session cookies are intended for the loopback-only HTTP development server. Do not expose the app on a public interface or pilot it with real data. A production implementation requires deployment-specific security design, TLS, monitoring, recovery testing and authorization.

If you find a security issue, report it privately rather than opening a public issue containing sensitive details.
