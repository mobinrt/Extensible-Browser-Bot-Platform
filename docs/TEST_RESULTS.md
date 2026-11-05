# Additional verification — November 5, 2026

The Docker stack is now running; November 4 startup restrictions below are historical.
The targeted ARCaptcha diagnosis is documented in
[ARCAPTCHA_ROOT_CAUSE_ANALYSIS](ARCAPTCHA_ROOT_CAUSE_ANALYSIS.md).

Executed for this change:

- `.venv/bin/python -m pytest -q` with no integration URLs at the initial instrumentation
  stage: **81 passed, 20 skipped**.
- Full regression inside the running worker's Docker network against a newly created
  disposable database: **102 passed, 2 skipped, 1 warning in 10.24 s**.
  [Raw output](evidence/arcaptcha-20261105/pytest.txt). The skips are opt-in live-login
  success and separate UI acceptance, neither silently treated as successful.
- Real Headless Grid HTTP/browser fixtures: **5 passed, 2 deselected in 8.85 s**.
- Real Headful Grid HTTP/browser fixtures: **5 passed, 2 deselected in 8.91 s**.
- `cd backend; ../.venv/bin/ruff check .`: passed.
- `cd backend; ../.venv/bin/mypy app`: passed, **29 source files**.
- `python3 -m compileall -q backend/app`: passed.
- `docker compose config --quiet`: passed.
- Four fresh-session live observations (A/B Headful, C/D Headless): A/C no rejection
  observed over five seconds after initialization; B/D explicit site rejection after
  one checkbox click and one create POST/201 response. Neither answer nor Login was
  requested. This is **not** a successful CAPTCHA/login acceptance run.
- Initial native HTTP-fixture routing failed four navigations (4 failed, 98 passed,
  2 skipped). Moving the fixture runner into Docker removed this test-network issue;
  its dynamic fixture UUID also no longer needs a browser secure context.
- `docker compose build worker`: failed after PyPI timeouts/no matching distribution
  through that inaccessible index. No dependency version was changed to hide it.
- `docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ worker`:
  succeeded with the same locked versions. This package mirror is unrelated to browser
  networking and is not an evasion proxy.
- `docker compose up -d --no-deps worker`: succeeded after verifying zero active runs.
  Diagnostics default false and writable private artifact directory were verified in
  the deployed worker; its code hashes match source. API readiness remained `ready`.
  All original application services remain running; production history was retained.

The full Docker regression runner used the instrumented source and temporary local
pytest/httpx tooling copied into the existing worker container. Its exact invocation,
after copying `backend/app`, `tests`, `migrations`, `alembic.ini`, `pyproject.toml` and
pytest dependencies under `/tmp/arcaptcha-debug` and `/tmp/arcaptcha-pytest-site`, was:

```bash
docker compose exec -T postgres createdb -U bots arcaptcha_rca_20261105
docker compose exec -T -w /tmp/arcaptcha-debug \
  -e PYTHONPATH=/tmp/arcaptcha-pytest-site -e PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 worker \
  python -c 'import os,socket,pytest; from app.core.config import get_settings; from sqlalchemy.engine import make_url; settings=get_settings(); test_url=make_url(settings.database_url).set(database="arcaptcha_rca_20261105").render_as_string(hide_password=False); os.environ.update(DATABASE_URL=test_url,TEST_DATABASE_URL=test_url,SELENIUM_TEST_URL=settings.selenium_url,TEST_FIXTURE_HOST=socket.gethostbyname(socket.gethostname())); get_settings.cache_clear(); raise SystemExit(pytest.main(["-q"]))'
```

The password remained in process memory/environment; it was not printed. Tests dropped
only their disposable database's test tables. No production table/volume was used as
a destructive fixture. No frontend code was changed, so no new frontend result is claimed.
The temporary test database and native test cluster were cleaned up after verification.
The original application services remained running. See the RCA for diagnostic
enable/inspect commands, environment, timelines and limits.

---

# Executed verification — November 4, 2026 (Asia/Tehran)

This replaces the old November 3 report. Counts below are actual executions on the
modified repository. A skipped or externally blocked acceptance criterion is not a pass.

## Environment

Python 3.12.3; Selenium Python 4.31.0; PostgreSQL 16.15; Chrome 156.0.8078.79;
ChromeDriver 156.0.8078.80; Node 22.23.4; npm 12.2.1; Docker Engine 29.8.0;
Compose 5.7.0. Local browser tests use **webdriver.Remote over HTTP to ChromeDriver**,
not an in-process local-driver API. The Docker Selenium Grid path was not executed.

The temporary PostgreSQL cluster was initialized with trust authentication **only on
127.0.0.1:55432 and a /tmp socket**, using disposable `bot_test` and separate
`bot_acceptance` databases. This is test setup, not a production authentication recommendation.

## Final deterministic backend checks

Working directory `backend`; `.venv` is in the repository root:

```bash
export DATABASE_URL=postgresql+psycopg://bots@127.0.0.1:55432/bot_test
export TEST_DATABASE_URL="$DATABASE_URL"
export SELENIUM_TEST_URL=http://127.0.0.1:55444
../.venv/bin/python -m pytest -q
../.venv/bin/python -m compileall -q app
../.venv/bin/ruff check .
../.venv/bin/mypy app
```

- **pytest: 82 passed, 2 skipped, 1 warning in 16.13 s.**
- Skips: explicit opt-in live CAPTCHA test and separate opt-in running-UI acceptance.
  Both were exercised separately as described below.
- Compile: pass.
- Ruff: all checks passed.
- Mypy: no issues in 28 source files.
- `python -m pip check`: no broken requirements.
- Warning: Starlette's TestClient uses a deprecated AnyIO BlockingPortal alias. It did
  not fail any test; upstream API compatibility should be reviewed during dependency updates.

Coverage includes real PostgreSQL migrations, API validation/history/errors, competing
claims, expired leases, immutable terminal/challenge records, cross-session immediate
commits, worker cleanup and transport-error classification. Controlled unit fixtures
cover selectors, hidden reads, solved prerequisites, missing credentials/controls/IDs,
manual intervention/resume, submission guards, deadlines, request/frame correlation,
duplicates, redirects, unreadable/malformed bodies and HTTP-200 application rejection.

[Raw final pytest output](evidence/backend-pytest.txt), [mypy output](evidence/mypy.txt).

## Real deterministic browser/HTTP checks

```bash
# backend working directory
SELENIUM_TEST_URL=http://127.0.0.1:55444 \
  ../.venv/bin/python -m pytest -q tests/test_browser_fixture.py -k 'not live'
BROWSER_TEST_MODE=HEADFUL SELENIUM_TEST_URL=http://127.0.0.1:55444 \
  ../.venv/bin/python -m pytest -q tests/test_browser_fixture.py -k 'not live and not console'
```

Headless fixture/smoke run: **5 passed, 1 deselected, 12.45 s** before the additional
opt-in UI test was added; those five also pass in the final full suite. Headful final: **5 passed, 2 deselected in 14.41 s**; output is recorded in [headful-browser.txt](evidence/headful-browser.txt).

The fixture runs an actual HTTP server. Chrome generates a dynamic UUID through the
fixture's named getter and submits a real fetch. Tests observe its response through
remote CDP/performance logs. Cases: success; HTTP rejection; HTTP 200 application
rejection; malformed response; local smoke. The tests assert one HTTP submission even
when `submit()` is invoked twice. Fixture success is never described as live CAPTCHA success.

## React and native full-stack acceptance

The native API (8000), Vite UI (5181), dedicated worker and acceptance database were
started separately with environment overrides, preserving the existing `.env` file.

- API readiness: HTTP 200, `status=ready`.
- `python3 scripts/acceptance.py`: both queued `local-smoke` modes reached `SUCCEEDED`
  with `observed_local_ready_text`; [recorded IDs](evidence/native-smoke.txt).
- `UI_TEST_URL=http://127.0.0.1:5181 UI_TEST_SCREENSHOT=<repo>/docs/evidence/ui-smoke.png
  SELENIUM_TEST_URL=http://127.0.0.1:55444 ../.venv/bin/python -m pytest -q
  tests/test_browser_fixture.py::test_console_launch_smoke`: **1 passed in 5.10 s**.
  It selected a bot in the actual React UI, launched it, and observed final evidence
  after API→PostgreSQL→worker→Selenium execution. [Screenshot](evidence/ui-smoke.png).
- PostgreSQL was stopped and restarted without deleting its data directory. API history
  retained the **same five run IDs, states, error codes and challenge-presence values**:
  three smoke/UI successes and two live blocks. [Restart record](evidence/native-persistence.txt).
  This is real database restart persistence, **not Docker-volume acceptance**.

The initial UI navigation failed twice with the 30 s renderer timeout. Investigation
found its external Google Fonts CSS import. Removing that runtime dependency fixed the
navigation and the UI test passed. System font fallbacks preserve the console layout.

## Frontend reproducibility/build

Working directory `frontend`:

```bash
npm ci --no-audit --no-fund --cache /tmp/bot-npm-cache
npm ci --offline --no-audit --no-fund --cache /tmp/bot-npm-cache
npm run typecheck
npm run build
```

Both clean installs completed; final offline install added 67 packages in 2 s.
Typecheck passed. Final production build passed in **1.74 s**, with 33 modules transformed.
[Build output](evidence/frontend-build.txt). npm 12 reported its esbuild install-script
approval warning; the installed platform binary built successfully without changing
machine approval settings. CI and Docker use `npm ci` with the committed lockfile.

## Live Arcaptcha: genuine blocked outcome

The strict opt-in Headless success test was attempted through Selenium and **failed**
with `CHALLENGE_ID_UNAVAILABLE` before the explicit site-block classification fix.
It did not skip or infer success. A Headful sanitized diagnostic then confirmed:

- Visible real checkbox clicked; create request observed.
- One widget registry entry, matching the DOM's data-widget-id.
- Named `getChallengeID` exists, but its value is undefined (length zero).
- The real widget displayed its explicit blocked warning.

After repairing classification, real queued worker runs recorded:

- **HEADLESS: BLOCKED / CAPTCHA_SITE_BLOCKED / captcha; no ID obtained.**
- **HEADFUL: BLOCKED / CAPTCHA_SITE_BLOCKED / captcha; no ID obtained.**

[Actual run records](evidence/live-run-outcomes.json), [site screenshot](evidence/live-site-blocked.png).
The public site refused the browser before issuing challenge state, so neither run
entered credentials, submitted login or obtained final success evidence. No CAPTCHA
was solved or bypassed. No live success, live challenge persistence or manual-completion
success is claimed. Headful's site-level rejection prevented a manual puzzle window.

Public demo and widget scripts were retrieved successfully; provenance is in
[RECONNAISSANCE](RECONNAISSANCE.md). The create query ID was not used as a substitute.

## Docker: attempted, externally blocked

Commands actually attempted from the repository root:

```bash
docker version
docker compose version
docker compose config --quiet
docker compose build
docker compose build api
docker compose up -d
docker compose ps
docker compose logs --tail=100
```

Initial config failed because the old healthcheck contained broken YAML quoting.
The fixed final config passes. Docker daemon access works with execution permission.

- Full build failed before application build: registry HEAD for
  `docker.io/library/nginx:1.27-alpine` returned **403 Forbidden**.
- Independent API build failed at `python:3.12.10-slim` metadata with **403 Forbidden**.
- Startup failed pulling `selenium/standalone-chrome:4.51.0-20261010`: **RBAC access denied**;
  the pinned Postgres image was unavailable locally. Official Selenium release notes
  list the tag; this environment's denial is not evidence the tag does not exist.
- `compose ps` had no running application services; logs contained no service execution.
- **Not verified:** image builds, six-service startup, deployed Grid CDP observation,
  noVNC desktop/server access, named-volume retention across container restarts.

## Installation diagnostics

Direct uv/PyPI clients timed out. A curl-backed local transport also timed out and
was abandoned. Public mirror downloads plus existing cached package wheels allowed
all required Python tooling to install. The first combined download stopped mid-mypy
wheel; the smaller pure-Python mypy wheel and persistent cache resolved it. Dependency
consistency was then checked. No source pin was relaxed to make tests pass.

Official ChromeDriver download returned 403; a public browser-binary mirror supplied
the matching driver. Google Chrome itself was already installed. Temporary download
and service files live outside source. No secrets or CAPTCHA payloads were copied into evidence.

Temporary native validation services were stopped after evidence capture; the disposable
Postgres data directory was retained. No application Docker services were left running.
