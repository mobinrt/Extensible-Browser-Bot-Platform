# Testing

## Local checks

From the repository root, use Python 3.12 and Node 22:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements-dev.lock
python -m pip install --no-deps -e ./backend
cd backend
python -m compileall -q app migrations tests
ruff check .
mypy app
python -m pytest -q
cd ../frontend
npm ci
npm run typecheck
npm run build
```

Without service URLs, integration tests **skip**. Never count those skips as passes.
The unit suite covers bot/registry contracts, state validation, configuration, browser
selection and cleanup, challenge provenance, CAPTCHA/manual flow, submission guards,
response/frame correlation, redirects, malformed/unreadable responses and failure codes.
Mocked outcomes validate logic, not live CAPTCHA acceptance.

## PostgreSQL and real Grid fixtures

Use a **disposable** database: tests create/drop tables and migration tests downgrade
the schema. Never point `TEST_DATABASE_URL` or test `DATABASE_URL` at application history.
Start separate test services (these names/ports must be unused):

```bash
docker run --rm -d --name bot-test-db \
  -e POSTGRES_USER=bots -e POSTGRES_PASSWORD=local_test_only -e POSTGRES_DB=bot_test \
  -p 127.0.0.1:55432:5432 postgres:16.9-alpine
docker run --rm -d --name bot-test-grid --shm-size=2g \
  --add-host=host.docker.internal:host-gateway \
  -p 127.0.0.1:4444:4444 -p 127.0.0.1:17900:7900 \
  selenium/standalone-chrome:4.51.0-20261010
# Wait for pg_isready and Grid /status ready=true.
export DATABASE_URL=postgresql+psycopg://bots:local_test_only@127.0.0.1:55432/bot_test
export TEST_DATABASE_URL="$DATABASE_URL"
export SELENIUM_TEST_URL=http://127.0.0.1:4444
export TEST_FIXTURE_HOST=host.docker.internal
cd backend
../.venv/bin/python -m pytest -q
BROWSER_TEST_MODE=HEADFUL ../.venv/bin/python -m pytest -q \
  tests/test_browser_fixture.py -k 'not live and not console'
# After testing, stop only these disposable services:
docker stop bot-test-db bot-test-grid
```

PostgreSQL tests cover API validation/history, migrations, concurrent claims, lease
expiry, immutable terminal states/IDs, independent challenge commits and worker
cleanup. Browser fixtures serve local HTML and actual HTTP responses; Chrome performs
real fetches and CDP reads their bodies. Five cases cover accepted/rejected login,
HTTP-200 application rejection, malformed response and local smoke. The fixture's
synthetic CAPTCHA state tests integration; it is not a solver or a live success claim.

`TEST_FIXTURE_HOST` must reach the test process from Chrome. Docker Grid needs the
host-gateway mapping above; local Chrome uses `127.0.0.1` by default.

For native UC, install `backend/requirements-uc.lock` in the same venv and use matching
installed binaries. Run from `backend/` (Headful needs a display):

```bash
TEST_BROWSER_BACKEND=undetected-chrome CHROME_BINARY=/usr/bin/google-chrome \
  CHROMEDRIVER_BINARY=/usr/local/bin/chromedriver BROWSER_TEST_MODE=HEADLESS \
  ../.venv/bin/python -m pytest -q tests/test_browser_fixture.py -k 'not live and not console'
# Repeat with BROWSER_TEST_MODE=HEADFUL on the display used by Chrome.
```

## Docker and full-stack acceptance

```bash
docker compose config --quiet
docker compose -f docker-compose.yml -f docker-compose.uc.yml config --quiet
docker compose up -d --build
python3 scripts/acceptance.py --restart
```

The acceptance script queues `local-smoke` in both modes, requires final success and
checks that the same rows survive PostgreSQL/API/worker restart. It adds ordinary
smoke history; it never creates/drops tables or removes volumes. Use a separate
Compose project and unused published ports if the application must stay uninterrupted.

Repeat after opting into the UC overlay using the README. Check the UC processes and
both viewer endpoints:

```bash
docker compose exec worker supervisorctl status bot-worker xvfb vnc novnc
curl --fail -o /dev/null http://localhost:7901/vnc.html
curl --fail -o /dev/null http://localhost:7900/vnc.html
```

A Compose config pass alone does not prove image build or startup. Build both worker
images and verify the running service uses the intended backend. Use the UC venv's
`/opt/bot-venv/bin/python`, rather than the Selenium base image's system Python.

The optional console browser test requires `UI_TEST_URL` reachable from its test browser
and an independently running API/worker/database. It launches local-smoke through the
UI and requires final success in the detail drawer. In unattended runs it is skipped.

## Genuine live tests

Live tests contact the assigned external demo and demand actual success. They are
excluded from unattended CI and should not be repeated unnecessarily:

```bash
# backend working directory; expose the relevant Headful viewer first.
RUN_LIVE_DEMO=1 BROWSER_TEST_MODE=HEADFUL DEMO_USERNAME=demo DEMO_PASSWORD=demo \
  SELENIUM_TEST_URL=http://127.0.0.1:4444 ../.venv/bin/python -m pytest -q -s \
  tests/test_browser_fixture.py::test_live_demo_opt_in
```

For local UC also set `TEST_BROWSER_BACKEND` and binary paths as above. A blocked
live test fails; it is never converted into a passing skip. This direct browser test
does not prove database persistence. Use a queued run and inspect its API record for
that. [Actual live findings](ARCAPTCHA_FINDINGS.md) distinguish human assistance,
backend/mode and evidence limits.

## Cleanup verification — 6 November 2026

Executed against the cleaned source:

- Python compilation, Ruff and mypy: passed (30 application files).
- Local suite without service URLs: **92 passed, 21 skipped**. These skips were not passes.
- Full Grid regression in the rebuilt worker image, using a disposable PostgreSQL
  container/database: **111 passed, 2 skipped**, one Starlette/AnyIO deprecation warning.
  The skips were the opt-in live CAPTCHA and console tests; console acceptance ran separately.
- Grid Headful real browser/HTTP fixtures: **5 passed, 2 deselected**. Headless fixture
  coverage is included in the full regression.
- Rebuilt UC image real browser/HTTP fixtures: **5 passed per mode**, Headful and
  Headless. Each mode emitted five upstream UC `locale.getdefaultlocale` deprecation warnings.
- Both rebuilt worker images: queued `local-smoke` SUCCEEDED in both modes. The same
  four test rows remained SUCCEEDED after their respective worker-container restarts.
  Queue/worker checks used separate acceptance databases, never application history.
- Frontend typecheck and production build: passed. Real running-console browser smoke:
  **1 passed**, through UI → API → queue → UC worker → browser → UI. This added one
  ordinary smoke row to application history, with no schema changes or destructive fixtures.
- Base and UC Compose configuration validation: passed. Both worker images rebuilt.
  A fresh UC container reached RUNNING for worker, Xvfb, VNC and noVNC; its viewer
  returned HTTP 200. The deployed Grid and UC viewers also returned HTTP 200.
- Both rebuilt worker Python environments: `pip check` passed. Local Markdown file
  links and `git diff --check` passed. Existing Python ASTs were unchanged except for
  removing an unused, unreferenced `ApiError` model; application API schemas are unchanged.

Temporary test tools were copied separately into disposable containers; they were
not added to production dependencies or the repository. Initial temporary test-harness
attempts stopped on daemon bind-mount visibility and a missing pytest compatibility
shim before application tests ran. File copies and the complete pytest tooling resolved
both setup issues. Disposable test containers were removed. Existing application
services were neither replaced nor restarted, and the application PostgreSQL volume
was not removed or used as a destructive test fixture.

**NOT TESTED during cleanup:** new live Arcaptcha/CAPTCHA attempts, fresh PostgreSQL
service restart or host reboot persistence, native ARM/Windows/macOS execution.
The historical seven human-assisted UC Headful successes and Headless blocking were
checked through read-only database inspection and retained as sanitized evidence.
The documented full-stack `acceptance.py --restart` command additionally checks a
PostgreSQL/API restart when explicitly run in the review environment.
