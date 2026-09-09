# Validation record

Authoring environment: Windows, 2026-09-09.

Executed successfully:

- `python -m unittest discover -s tests -v`: 7 tests passed, including invalid-input subcases.
- `python -m compileall -q scripts tests`: all Python files compiled.

Blocked by environment:

- `docker build -t postfix-smtp-relay:local .`: Docker executable not found.
- `wsl --list --quiet`: Windows Subsystem for Linux is not installed.
- Consequently, Docker Compose validation, image/package installation, generated
  configuration inspection by real Postfix, `postfix check`, SMTP probes and queue
  persistence checks could not run here.

The integration script and GitHub Actions workflow implement those runtime checks;
they are not recorded as passing. Run `python3 tests/integration.py` on a Linux
Docker host and resolve any failures before releasing or deploying. Perform the
README site acceptance checks to validate real source IP preservation, firewall,
certificate trust and M365 connector behavior.
