# Bot Research Engineer — Extensible Browser Bot Platform

FastAPI queues browser jobs in PostgreSQL. A separate worker executes Selenium
RemoteWebDriver bots; React displays durable history, failure stages and evidence.
The registry includes the assigned Arcaptcha demo and an independent local browser smoke bot.

**Submission status: live CAPTCHA/login and Docker acceptance are blocked.** The current public demo
code was inspected and the implementation repaired; real Headful and Headless runs
were explicitly rejected by the widget and accurately stored as BLOCKED. Read [actual test results](docs/TEST_RESULTS.md)
and [the reviewer report](docs/REVIEWER_REPORT.md) for what really ran. Source inspection
or passing unit tests alone does not establish a successful live CAPTCHA/login or Docker deployment.

## Architecture

```mermaid
flowchart LR
  UI[React / nginx] --> API[FastAPI]
  API --> DB[(PostgreSQL queue and history)]
  W[Dedicated worker] --> DB
  W --> S[Selenium standalone Chrome]
  H[Human operator via noVNC] --> S
```

The API returns `202 QUEUED` without browser work. Workers claim with PostgreSQL
`FOR UPDATE SKIP LOCKED`, commit challenge IDs independently, maintain ownership leases,
and finalize results. Expired jobs become timed out; they are never replayed automatically.
[Architecture and guarantees](docs/architecture.md).

## Prerequisites and platforms

- Docker Engine and Compose v2 or newer; internet access to images, packages and the demo.
- At least 4 GB available RAM; Chrome gets 2 GB shared memory.
- The Compose browser is explicitly **linux/amd64**. Linux amd64 is the target deployment.
  Windows/macOS require Docker Desktop Linux containers. ARM hosts need amd64 emulation;
  native ARM and desktop OS behavior have not been verified here.
- Local development uses Python 3.12 and Node 22. Locks record the tested Python 3.12
  dependency set and npm dependency graph. No production credentials belong in source.

## Clean installation

From this repository's root:

```bash
cp .env.example .env
# Edit POSTGRES_PASSWORD and NOVNC_PASSWORD; keep DEMO_USERNAME=demo and DEMO_PASSWORD=demo.
# Use an 8-character random noVNC password (VNC supports at most 8 characters).
docker compose config --quiet
docker compose up -d --build
docker compose ps
curl --fail http://localhost:8000/api/v1/health/ready
```

Open UI **http://localhost:8080**, API docs **http://localhost:8000/api/v1/docs**,
and Headful browser **http://localhost:7900**. Compose also wires a customized
`NOVNC_PORT` into the UI viewer links; native Vite development can set `VITE_NOVNC_URL`. Default exposed ports bind only to loopback.
PostgreSQL and WebDriver have no public ports. `migrate` must finish successfully before
API/worker start; postgres, selenium, api and frontend have health checks.

Select **Local Browser Smoke Test**, choose Headless, launch and wait for `SUCCEEDED`.
Repeat Headful and verify its browser in noVNC. Then try Arcaptcha after reading its
limitations below. Queue creation or a browser window alone is not a passed smoke run.

On a server, forward the UI, API (optional) and viewer:

```bash
ssh -L 8080:127.0.0.1:8080 -L 8000:127.0.0.1:8000 -L 7900:127.0.0.1:7900 user@server
```

Use the same localhost addresses. Keep noVNC, WebDriver and the unauthenticated local
API off the public internet. Only one Chrome session is configured at a time.

## Configuration

`.env.example` contains local public demo credentials, timeout budgets and four CSS settings:

- `ARCAPTCHA_CHECKBOX_SELECTOR="#arc-checkbox, #ar-checkbox"`
- `ARCAPTCHA_USERNAME_SELECTOR=#email`
- `ARCAPTCHA_PASSWORD_SELECTOR=#password`
- `ARCAPTCHA_SUBMIT_SELECTOR=form button`

The current downloaded widget uses `#arc-checkbox`; the supplied manual snapshot used
`#ar-checkbox`. Both are legitimate wrapper candidates. A changed upstream DOM needs
fresh inspection. Do not use the generated full widget ID. Legacy
`ARCAPTCHA_CHALLENGE_SELECTOR`, `ARCAPTCHA_SOLVED_SELECTOR`,
`ARCAPTCHA_SUCCESS_SELECTOR`, `ARCAPTCHA_FAILURE_SELECTOR` are deprecated and **ignored**;
you no longer need to configure arbitrary CSS evidence to enable success.

Compose passes the raw `POSTGRES_PASSWORD` separately. Settings builds a SQLAlchemy
URL with correct escaping, including reserved password characters. An explicit
`DATABASE_URL` remains supported outside Compose and must be URL-encoded normally.
`DEMO_USERNAME` and `DEMO_PASSWORD` remain worker-side settings and cannot be supplied
through run creation. Existing `.env` files are not overwritten; refresh obsolete
selector overrides when upgrading. Quote literal `$` in Compose env files as supported
by Compose (single quotes preserve it). Never commit `.env`.

Timing defaults: `RUN_TIMEOUT_SECONDS=180`, `MANUAL_TIMEOUT_SECONDS=90`,
`SELENIUM_WAIT_SECONDS=12`, `LEASE_SECONDS=45`, `HEARTBEAT_SECONDS=10`.
Heartbeat must be less than half a lease. WebDriver transport, page and script commands
have a 30-second timeout; logical deadlines are checked between commands. PostgreSQL
connections/statements and pool acquisition are bounded too. Run deadlines are best
effort around blocking commands, not process-isolation guarantees.

## Arcaptcha execution and evidence

The bot navigates to `https://demo.arcaptcha.co`, ordinarily clicks the visible wrapper,
and reads the widget's **named `getChallengeID` getter**. Public widget code registers
this getter to return `challenge.challenge_id` from decoded server-created challenge
state. The create URL's `id` is called `bowman_id` in that code and is **not trusted** as
a challenge ID. A semantic DOM fallback accepts only explicitly named challenge fields.
No guessed UUID or hidden CAPTCHA token is used as an ID source.

The ID is committed before entering credentials or waiting for CAPTCHA completion.
A nonempty legitimate hidden token plus the nested checkbox's selected state permit
submission; hidden elements are read without a visibility requirement.

- **Headless:** uses `--headless=new`; waits briefly for ordinary widget completion.
  A human-only challenge produces `BLOCKED`, preserving an obtained ID. An explicit
  site block is `CAPTCHA_SITE_BLOCKED`, even if no ID was issued.
- **Headful:** opens Chrome on the Selenium container's virtual display. During
  `WAITING_FOR_HUMAN`, use noVNC to complete the normal challenge within the bounded
  manual window. The bot resumes automatically. An already observed manual login,
  including one still in flight, suppresses the bot's Login click.

Final verification uses session performance events and remote CDP to read the response
from the **browser's own** POST `/api/login`. Only HTTP 200 plus the expected successful
JSON application message permits `SUCCEEDED`. HTTP 200 alone, a selected checkbox,
a token, a click or a toast cannot do so. Rejection is `FAILED`; observer/body ambiguity
is `BLOCKED`; missing responses/manual deadlines are `TIMED_OUT`. Login is never retried
after an ambiguous click or transport error. No token injection, CAPTCHA bypass,
stealth evasion or third-party solvers are implemented.

[Detailed provenance and transport rationale](docs/RECONNAISSANCE.md).

## States, API and history

Supported states: `QUEUED`, `RUNNING`, `WAITING_FOR_HUMAN`, `SUCCEEDED`, `FAILED`,
`BLOCKED`, `TIMED_OUT`. Only active runs can finalize; terminal rows are immutable.
A lost/expired lease cannot renew or write challenge/status updates. Challenge IDs
cannot be overwritten silently. The UI displays state, ID, codes, stage and final evidence,
polls updates and supports status-filtered paginated history.

```bash
curl http://localhost:8000/api/v1/bots
curl -i -X POST http://localhost:8000/api/v1/runs \
  -H 'Content-Type: application/json' \
  -d '{"bot_id":"local-smoke","browser_mode":"HEADLESS"}'
curl 'http://localhost:8000/api/v1/runs?limit=20&offset=0&status=SUCCEEDED'
curl http://localhost:8000/api/v1/runs/<run-id>
```

Unknown bot/mode or invalid UUID: 422; unknown run: 404; database unavailable: 503.
No target URLs or passwords are accepted from public run requests.

`docker compose restart` and `docker compose down` followed by `up -d` retain the
`pgdata` volume and history. **`docker compose down -v` deletes history.**
Record a run ID before restart and GET the same ID afterward to verify retention.

## Tests

From the repository root (use `python3` where `python` is unavailable):

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements-dev.lock
python -m pip install --no-deps -e ./backend
cd backend
python -m compileall -q app
python -m pytest -q
ruff check .
mypy app
cd ../frontend
npm ci
npm run typecheck
npm run build
```

Without service URLs the integration tests **skip**, not pass. Set `TEST_DATABASE_URL`
to a dedicated disposable PostgreSQL database (tests create/drop tables and migration
tests downgrade the schema). Never use the application's history database for tests.
Set `DATABASE_URL` to that test URL as well for test API/worker imports.

For isolated service tests, start dedicated disposable services (do not reuse the
application history database). These local-only test credentials are intentionally
separate from the application's passwords:

```bash
docker run --rm -d --name bot-test-db \
  -e POSTGRES_USER=bots -e POSTGRES_PASSWORD=local_test_only -e POSTGRES_DB=bot_test \
  -p 127.0.0.1:55432:5432 postgres:16.9-alpine
# Set a temporary viewer password in your shell first (maximum 8 characters).
export SE_VNC_PASSWORD='<your temporary viewer password>'
docker run --rm -d --name bot-test-grid --shm-size=2g \
  --add-host=host.docker.internal:host-gateway -e SE_VNC_PASSWORD \
  -p 127.0.0.1:4444:4444 -p 127.0.0.1:17900:7900 \
  selenium/standalone-chrome:4.51.0-20261010
# Wait for Postgres readiness and Grid /status ready=true before running tests.
export DATABASE_URL=postgresql+psycopg://bots:local_test_only@127.0.0.1:55432/bot_test
export TEST_DATABASE_URL="$DATABASE_URL"
export SELENIUM_TEST_URL=http://127.0.0.1:4444
export TEST_FIXTURE_HOST=host.docker.internal
```

The separate test Grid's Headful viewer is **http://localhost:17900**, using the temporary
password above. Stop test services afterward with `docker stop bot-test-db bot-test-grid`.
For real browser tests set `SELENIUM_TEST_URL` to the Grid URL.
The HTTP fixture server runs in the test process; if Chrome is in Docker, add
`--add-host=host.docker.internal:host-gateway` to its container and set
`TEST_FIXTURE_HOST=host.docker.internal`. Local ChromeDriver can use the default
`127.0.0.1`. The deterministic fixture uses real browser fetches and real HTTP
responses; it is not a CAPTCHA solver or a simulation claimed as live acceptance.

```bash
cd backend
# Export TEST_DATABASE_URL and DATABASE_URL for an empty test DB first.
SELENIUM_TEST_URL=http://127.0.0.1:4444 python -m pytest -q
BROWSER_TEST_MODE=HEADFUL SELENIUM_TEST_URL=http://127.0.0.1:4444 \
  python -m pytest -q tests/test_browser_fixture.py -k 'not live'
# Live/manual test; success is demanded, never converted to a passing skip:
RUN_LIVE_DEMO=1 BROWSER_TEST_MODE=HEADFUL DEMO_USERNAME=demo DEMO_PASSWORD=demo \
  SELENIUM_TEST_URL=http://127.0.0.1:4444 \
  python -m pytest -q -s tests/test_browser_fixture.py::test_live_demo_opt_in
```

For deterministic full-stack acceptance (both modes and history retained across service
restart), run `python3 scripts/acceptance.py --restart` from the repository root.
To inspect metadata without exporting tokens or submitting login, run
`docker compose exec worker python -m app.bots.arcaptcha.diagnose --mode HEADLESS`.

The live test checks browser behavior, not DB persistence. Full worker acceptance must
also verify the queued run's ID and terminal evidence through the API. CI runs unit,
Postgres/API, migration and real deterministic browser checks, plus frontend builds.
It excludes live CAPTCHA success from unattended gates.

## Troubleshooting and limitations

- `docker compose logs --tail=100 api worker selenium migrate`: check service readiness
  and categorized errors. Passwords, tokens and network bodies must not be logged.
- The UI uses local system font fallbacks; it does not wait for Google Fonts.
- Image pull `403`, RBAC denial or DNS failure: fix the deployment network/registry
  access; a Compose config pass does not prove a working deployment.
- Browser unavailable: check Grid health, RAM, shared memory, architecture and URL.
- `CHALLENGE_ID_UNAVAILABLE`: inspect the named getter and actual DOM; never substitute
  the create-query UUID or CAPTCHA token. See reconnaissance for the minimal diagnostic.
- `NETWORK_OBSERVER_UNAVAILABLE` or `LOGIN_RESPONSE_UNREADABLE`: the deployed remote
  Chrome/driver must support performance logs and response-body CDP. Fail closed.
- CAPTCHA blocked: try Headful normal manual completion. This is not a successful run.
- A manual widget reset may create a new challenge; history intentionally retains the
  first independently committed ID. Multiple login requests make verification ambiguous.
- Stale leases are reaped by a running worker. With all workers stopped, recovery happens
  when a worker restarts; no claim of exactly-once external effects is made.
- A DB outage can make an externally completed action indeterminate. The reaper records
  timeout rather than replaying the action or inventing success.
- Live CAPTCHA, deployed Grid response observation, noVNC and full Compose persistence
  must pass in the review environment before calling the repository submission-ready.

## Add a bot

Implement the typed `Bot` protocol and register a factory in `build_registry`; no
execution, storage, API or UI core changes are needed. Use context callbacks for immediate
challenge persistence and human-wait reporting. The included `local-smoke` is a minimal
Selenium implementation. [New-bot guide](docs/new-bot.md),
[submission checklist](docs/SUBMISSION_CHECKLIST.md).
