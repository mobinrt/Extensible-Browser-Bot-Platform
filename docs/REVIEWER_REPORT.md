> **November 5 update:** the Docker stack is now healthy. Four controlled observations
> establish explicit rejection after checkbox interaction during the create exchange,
> in both modes; they do not establish the service's policy reason. Opt-in private JSONL
> diagnostics, readiness/pre-click guards and 102 passing regression tests are documented
> in [ARCAPTCHA_ROOT_CAUSE_ANALYSIS](ARCAPTCHA_ROOT_CAUSE_ANALYSIS.md).
> The original November 4 report below is retained as historical evidence.

# Implementation audit and requirements matrix

**Verdict: not yet ready for an unconditional hiring submission.** The deterministic
implementation and native full-stack path are verified. Real Arcaptcha rejects both
browser modes before issuing an ID, and registry restrictions prevent Docker deployment.

## Problems found and repaired

- Hidden CAPTCHA inputs were treated as visible/clickable controls. The page adapter
  now separates normal lookup, clickable lookup, hidden reads and selected state.
- Default selectors did not match the inspected site; current and manually observed
  wrapper IDs are supported. Generic iframe crawling and arbitrary CSS success guesses
  were removed; no iframe is required by the inspected widget.
- Challenge extraction lacked authoritative provenance. Public widget code exposes a
  named server-state getter. The create query's `bowman_id` is not persisted as challenge_id.
- Login verification depended on invented/configured DOM markers. A scoped Chrome
  observer correlates actual browser login responses and requires HTTP + expected JSON.
- Manual in-flight submissions could be duplicated. Request observation suppresses
  submission; a dispatched click is not retried after stale/transport errors.
- Headless checked readiness too early; a bounded automatic-completion wait now precedes
  a human-required block. Headful resumes RUNNING after its bounded manual wait.
- Real upstream rejection before ID creation was misclassified as a missing-ID failure.
  The confirmed widget blocked warning now produces accurate `CAPTCHA_SITE_BLOCKED`.
- Expired owners could renew leases/write; challenges could be truncated/replaced.
  Writes now reject expired ownership and preserve the first complete ID. Terminal
  status cannot bypass finish, and successful persistence requires evidence.
- Transport timeouts were unbounded; setup failures could orphan an already returned
  driver. Client/database timeouts, setup cleanup, final deadline check and categorized
  connection/timeout outcomes were added.
- Compose was invalid YAML; raw DB password interpolation broke URL-reserved characters.
  The healthcheck and SQLAlchemy component-based URL construction fix both.
- Frontend had no lockfile, could reopen closed detail views with stale polls, hid some
  status filters and depended on externally blocking font CSS. These are repaired;
  the existing console and architecture remain intact.
- CI omitted lint/type/integration gates. It now includes locked dependencies,
  PostgreSQL/API/migration and deterministic browser checks; live CAPTCHA is opt-in.
- Previous documents claimed the site could not be inspected and required meaningless
  success selectors. Documentation now reflects retrieved sources and actual blocked runs.

## Original hiring requirements

Each status below applies to the **complete original requirement**, not merely source existence.

1. **Extensible browser bot platform — VERIFIED.** `domain/contracts.py`, registry,
   examples. Registry tests add an independent bot without changing platform core;
   native UI→worker smoke succeeds.
2. **Selenium bot targeting the assigned demo — VERIFIED.** `ArcaptchaPage.open` and
   fixed-target configuration; actual remote browser sessions loaded the live demo.
3. **Legitimate checkbox click — VERIFIED.** `ArcaptchaPage.click_checkbox`; wrapper
   targeting tests, fixture clicks and actual live post-click blocked widget evidence.
4. **Extract a real live challenge_id — BLOCKED.** `read_challenge_id` uses the named
   widget getter plus validated semantic DOM fallback. Dynamic fixture IDs pass, but the
   live site's getter returned undefined after its explicit block. No query UUID was substituted.
5. **Persist live ID immediately — BLOCKED.** Callback and repository independent commit
   are verified by real PostgreSQL tests during bot execution and subsequent failure.
   The live site issued no ID, so a live persistence claim cannot be made.
6. **Fill configured credentials and submit — BLOCKED.** `fill_credentials`, submit
   guard and tests work against real HTTP/browser fixtures, including `demo` in an
   email input. Live execution correctly stopped before credentials/submission because of the block.
7. **Verify actual final server result — BLOCKED.** `browser/network.py` verifies real
   fixture HTTP/JSON responses through RemoteWebDriver/CDP; malformed/missing/rejected
   outcomes fail closed. No live login was submitted/accepted.
8. **Accurate success/failure/blocked/timeout states — VERIFIED.** Domain transitions,
   worker/repository, real DB error tests, browser response tests and actual live BLOCKED
   history. This does not imply all possible external failures were reproduced.
9. **Headful and Headless — VERIFIED for native Selenium.** Real fixtures/smoke passed
   both modes; real demo blocks were recorded in both modes. **Docker noVNC/manual
   CAPTCHA completion remains IMPLEMENTED_NOT_VERIFIED** due image pulls/site rejection.
10. **Persistent run history — VERIFIED for PostgreSQL/native stack.** Schema, repository,
    API/UI and real DB tests; five actual rows retained over server restart. Named Docker
    volume retention remains IMPLEMENTED_NOT_VERIFIED until container acceptance runs.
11. **Reliable Docker Compose desktop/server deployment — BLOCKED.** Valid config,
    six-service dependency gates, loopback ports, healthchecks, locked builds and SSH
    instructions exist; registry 403/RBAC errors prevent build/start/noVNC validation.
12. **Comprehensive tests/documentation — VERIFIED within stated scope.** Final deterministic
    suite, lint/type/build, real DB/browser/UI tests and evidence files were executed.
    Live success and Docker acceptance remain explicit open gates; CI workflow is implemented
    but a hosted GitHub Actions run was not triggered in this workspace.
13. **Documented registration interface/minimal example — VERIFIED.** Typed Bot protocol,
    registry tests, `examples/example_bot.py` and `docs/new-bot.md`; real smoke execution.
14. **Reproducible reviewer setup using README only — IMPLEMENTED_NOT_VERIFIED.** Commands,
    dependency locks, exact configuration, modes, diagnostics and acceptance script are
    included. Local installations/builds pass, but an independent fresh Docker reviewer
    walkthrough could not complete under the current registry restrictions.

Optional CAPTCHA-blocking improvement bonus: **not claimed**. No bypass/stealth/solver
is present and no success-rate experiment establishes an improvement.

## Implementation boundaries

A network observer that loses body access yields BLOCKED rather than trusting a toast.
Browser deadlines are checked between bounded commands, not enforced by OS process
termination. With all workers stopped, expired rows are reaped when a worker returns.
A DB failure after an external action can leave an indeterminate timeout; no exactly-once
external execution promise is made. The first challenge ID is retained over manual resets.
Local API/noVNC access is trusted-use only, with no public-service authentication layer.

## Remaining acceptance gates

1. Use a network where the real widget issues a legitimate challenge. Verify the named
   getter dynamically, independent DB commit, normal manual completion if necessary,
   one Login request, expected browser JSON response and stored final evidence. The
   current evidence does not justify a source workaround for site rejection.
2. Run documented Compose builds/startup with working registry access. Check deployed
   Grid response-body observation, noVNC locally and via SSH, and volume retention with
   `python3 scripts/acceptance.py --restart`.
3. Complete an independent fresh-clone README walkthrough before claiming submission readiness.

[Actual commands and counts](TEST_RESULTS.md), [provenance](RECONNAISSANCE.md),
[UI evidence](evidence/ui-smoke.png), [live blocked evidence](evidence/live-site-blocked.png).


## Changed-file inventory

Runtime changes:
`backend/app/bots/arcaptcha/{page.py,bot.py,diagnose.py}`,
`backend/app/infrastructure/browser/{network.py,selenium_factory.py}`,
`backend/app/core/config.py`, `backend/app/domain/contracts.py`,
`backend/app/infrastructure/database/{repository.py,session.py}`, and
`backend/app/worker/main.py`. Database models received only lint import ordering;
no schema replacement was needed.

Deployment/reproducibility:
`.env.example`, `docker-compose.yml`, both Dockerfiles,
`backend/pyproject.toml`, new `backend/requirements.lock` and `requirements-dev.lock`,
new `frontend/package-lock.json`, `.github/workflows/ci.yml`, `.gitignore`, and
new `scripts/acceptance.py`.

Frontend:
`src/api/client.ts`, `src/hooks/useConsole.ts`, `src/pages/Dashboard.tsx`,
`src/components/RunDetail.tsx`, `src/style.css`, new `src/viewer.ts` and
`src/vite-env.d.ts`. The custom noVNC port is wired through a public build argument.

Tests:
`test_api_integration.py`, `test_bot_outcomes.py`, `test_browser_fixture.py`,
`test_config.py`, `test_postgres_integration.py`, new `test_network.py` and
`test_page.py`, and `fixtures/arcaptcha_demo.html`. Domain/migration tests received
lint import ordering fixes. Existing registry tests still pass unchanged.

Documents:
`README.md`, `docs/RECONNAISSANCE.md`, `TEST_RESULTS.md`, `REVIEWER_REPORT.md`,
`SUBMISSION_CHECKLIST.md`, `architecture.md`, `new-bot.md`, and sanitized files in
`docs/evidence/`. No local secrets or generated dependency/build directories are tracked.
