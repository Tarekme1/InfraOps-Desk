# Verification notes

Checked locally on October 19, 2026 (Linux, Python 3.13, Node.js 22).

## Observed results

- `python -m unittest discover -s tests -v`: **13 tests passed** locally.
- `node --check static/app.js`: syntax check passed.
- HTML parser accepted `static/index.html`.
- ZIP CRC check was successful after packaging.

The checks cover server API behavior, input validation, persistence, CSV output, sample-data counts, denial of unlisted paths, status transitions and common response headers. All records are fictional.

## Not yet verified

- Automated browser end-to-end run: **not completed**. The execution environment blocked the localhost request inside Chromium. This is an environment restriction, not a passing browser test.
- GitHub Actions: **not run yet** at the time of packaging; CI must be checked after the repository is published.
- Real deployment, authentication, concurrent multi-user use, external network access, and backup/restore: **out of scope**.

### Reproduce

```bash
python -m unittest discover -s tests -v
node --check static/app.js
```

The second command is an optional client-side syntax check and requires Node.js. The application itself needs only Python 3.10+.
