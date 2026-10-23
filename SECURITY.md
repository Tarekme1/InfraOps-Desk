# Security and data handling

This repository intentionally uses fictional demonstration data, never live factory, employee or customer records.

## Development safeguards

- The HTTP server is bound to the loopback interface `127.0.0.1` by default.
- New tickets and status updates validate request JSON, payload size and value ranges.
- Synthetic accounts are configured through environment variables; the application stores PBKDF2-HMAC-SHA256 password hashes, not plaintext passwords.
- Session identifiers are random, stored as hashes, sent in `HttpOnly; SameSite=Strict` cookies, and expire after eight hours.
- Set `MIHWAR_SECURE_COOKIES=1` only when a TLS reverse proxy serves the app; it adds the `Secure` flag to session and CSRF cookies. The server trusts forwarded client IPs only when the socket peer exactly matches `MIHWAR_TRUSTED_PROXY_IP`, and then accepts only one valid IP address.
- Mutating authenticated requests require a per-session CSRF token. Login uses a same-site double-submit token.
- Five failed sign-ins for the same username/source pair, or 20 for a source address, within 15 minutes trigger a 15-minute lockout. Usernames and addresses are hashed in the throttle table; successful sign-in clears the username/source bucket.
- Employee ticket reads and reopening are restricted to the owner. Technician/admin routes check roles; technicians see unassigned tickets and their own assigned tickets, while administrators can assign work and export.
- Content Security Policy and existing clickjacking, MIME-sniffing and referrer protections are applied to app pages and API responses.
- SQLite migrations preserve existing demo records while adding account, session, ownership and assignment fields.
- Database queries use parameter placeholders.
- User-controlled text is escaped before being inserted into the browser's rendered HTML.
- CSV values starting with spreadsheet formula characters receive a protective prefix.
- Operator work notes are private by default when created through the interface; employee-visible updates are explicitly selected. Employee APIs suppress internal events server-side.
- `scripts/backup_db.py` uses SQLite's online backup API and validates integrity/foreign keys. Restore rejects corrupt input and creates a verified pre-restore copy before replacement.
- Runtime SQLite files, temporary files and secrets are excluded by `.gitignore`.

## Not intended for production

This remains a local demonstration and is not cleared for real employee, customer, factory or other sensitive data. The throttle and backup/restore helpers have automated local tests, but there is no TLS termination, scheduled/off-site encrypted backup, secure account-management interface, monitoring/alerting, tested operational recovery objective, or independent security review. Session cookies are intended for the loopback-only HTTP development server. Do not expose the app on a public interface or pilot it with real data. A production implementation requires deployment-specific security design, TLS, trusted-proxy configuration, operational monitoring, recovery testing and organizational authorization.

If you find a security issue, report it privately rather than opening a public issue containing sensitive details.
