# Submission checklist

Completed and executed:

- [x] Existing architecture preserved: React, API, PostgreSQL queue, separate worker, Selenium.
- [x] Correct visible wrapper targeting; hidden token + selected state handled separately.
- [x] Named challenge getter provenance traced in current public widget code.
- [x] Create-request `bowman_id` never silently persisted as challenge_id.
- [x] Immediate independent ID commit and retention on failure tested with PostgreSQL.
- [x] Actual browser HTTP + JSON evidence tested; HTTP 200 alone cannot succeed.
- [x] Manual in-flight submission guard; no retry after ambiguous click.
- [x] Explicit live widget rejection produces BLOCKED in both modes and stays in history.
- [x] Owner/lease/state/terminal/challenge protections tested.
- [x] Real deterministic RemoteWebDriver fixtures and smoke pass Headful and Headless.
- [x] Actual React→API→queue→worker→Selenium→React success verified.
- [x] Native PostgreSQL restart retains five acceptance records.
- [x] Backend compile, pytest, Ruff, mypy; frontend clean install/typecheck/build pass.
- [x] npm and Python dependency locks; Docker/CI use locked installs.
- [x] Valid Compose configuration, migration gates, loopback ports and SSH instructions.
- [x] Registration interface and minimal example documented/tested.
- [x] Screenshots and sanitized real outputs saved; limitations retained honestly.

Required before an unconditional submission-ready claim:

- [ ] Live real challenge ID is obtained and committed before later processing.
- [ ] Live normal CAPTCHA completion, credentials, one Login submission and genuine
      server-backed success are observed and stored. Current site rejects both modes.
- [ ] Docker images build and six services start successfully. Current pulls return 403/RBAC denial.
- [ ] Deployed Selenium Grid/CDP response bodies work inside Docker.
- [ ] noVNC works locally and through an SSH tunnel; manual completion resumes correctly.
- [ ] Named Postgres volume retains history across container restarts.
- [ ] Independent reviewer follows README from a fresh clone successfully.

No CAPTCHA-blocking bonus, live success rate or hosted CI success is claimed.
See TEST_RESULTS and REVIEWER_REPORT; passing unit tests is not sufficient to tick the open gates.
