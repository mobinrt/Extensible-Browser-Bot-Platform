# Architecture and guarantees

## Components and lifecycle

The React console calls FastAPI, which inserts a `QUEUED` PostgreSQL row and returns
202 without doing browser work. The dedicated worker claims a row, creates a fresh
browser, executes the registered bot, closes the browser and persists the outcome.
Alembic owns schema changes; PostgreSQL is both queue and durable run history.

```text
React/nginx → FastAPI → PostgreSQL ← worker → Grid or local UC Chrome
                                              ↑
                                      human through noVNC

QUEUED → RUNNING ⇄ WAITING_FOR_HUMAN
             └──→ SUCCEEDED | FAILED | BLOCKED | TIMED_OUT
WAITING_FOR_HUMAN can also transition directly to any terminal state.
```

`app/api` owns HTTP contracts, `application/registry.py` discovers bot factories,
`domain/contracts.py` defines typed bot/context/result protocols, `bots` owns target
interaction and `infrastructure` owns browser launch, observation and persistence.
Bots receive a context, never ORM sessions or HTTP request objects.

## Queue ownership and persistence

Workers claim with PostgreSQL `FOR UPDATE SKIP LOCKED`. Claiming, challenge updates,
heartbeat, human-wait transitions and finalization each commit independently.
`record_challenge` returns only after commit; subsequent CAPTCHA or credential failure
cannot roll it back. The first ID is immutable; repeating it is idempotent, replacing
or truncating it is rejected.

Every active write requires the owner, an active status and an unexpired lease.
Expired owners cannot renew or write. Terminal rows are immutable; finalization
clears ownership and records timestamps, duration, categorized errors and evidence.
Workers reap expired leases as `TIMED_OUT`, never automatically replaying possibly
completed external actions. With all workers stopped, reaping waits for a restart.
Multiple workers can claim separate jobs, though the configured Grid has one slot.
There is no exactly-once guarantee for external form effects.

Deadlines are checked between operations and after bot return. WebDriver's transport,
page and script limits are 30 seconds; logical deadlines are best effort around
blocking commands. Database connect, statement and pool acquisition are bounded.
Heartbeats stop on ownership loss or database errors. An outage can prevent final
persistence after an external effect; the lease reaper records timeout without replay.
The page observer closes in `finally`; the worker attempts browser cleanup even on
failure. Grid idle-session expiry bounds sessions lost before Python receives a driver.

## Browser backends

`selenium-grid` uses RemoteWebDriver and the standard Selenium container.
`undetected-chrome` uses a local UC factory with matching installed Chrome/driver,
a fresh profile and a private driver copy. Its wrapper tracks owned descendants,
bounds process termination and removes the profile. UC dependencies are optional;
production Selenium remains pinned at 4.31.0 in both images.

The UC overlay replaces only the worker image/command and console viewer URL.
Supervisor runs Python from `/opt/bot-venv`, Xvfb, VNC and noVNC. UC Headful runs on
Xvfb and is visible on port 7901; Grid's viewer stays on 7900. Headless selects actual
headless Chrome; a virtual display does not convert Headful into Headless.

## Arcaptcha evidence boundary

The adapter ordinarily clicks the visible wrapper and reads the widget's named
`getChallengeID` getter, which the inspected public widget registers against
`challenge.challenge_id`. Explicitly named DOM metadata is a validated fallback.
The create-query `id` is called `bowman_id` upstream and is not trusted as a challenge
ID. Tokens, guessed UUIDs and arbitrary legacy CSS cannot supply challenge identity.
The first observed ID commits before human waiting, credential entry or submission.

A selected nested checkbox plus a legitimate nonempty hidden token permit submission.
Headful can enter a bounded `WAITING_FOR_HUMAN` window; after normal completion the
bot resumes and fills credentials. This avoids challenge overlays obstructing inputs.
An observed manual submission, including an in-flight request, suppresses another click.
A dispatched click is never retried after an ambiguous transport failure.

Final acceptance uses Chrome performance events and CDP response-body observation of
the browser's own POST to the exact demo origin/path and top frame. Only HTTP 200 plus
JSON `msg` equal to `You are logged in successfully!` succeeds. HTTP/application
rejection fails; ambiguous/unreadable responses block; absent responses time out.
Duplicate requests, redirects and malformed bodies fail closed. Selenium 4.31 lacks
the needed newer BiDi response-body surface, so Chrome-specific CDP stays in
`infrastructure/browser/network.py`. No Python-side login, token injection, solver
service or response fabrication is used.

## Extending and operating

1. Implement `descriptor` and `run(ctx)` under `app/bots/` and register its zero-argument
   factory in `build_registry`. Duplicate IDs are rejected and each run gets a fresh bot.
2. Use `ctx.driver`, check deadlines between blocking steps, and immediately call
   `ctx.record_challenge` for legitimate metadata. Stop if its commit fails.
3. Use `report_manual_wait`/`report_running` for human interaction. Return a terminal
   `BotResult` with observed success evidence or raise a static `BotRunError(code, stage, status)`.
4. Close bot-owned observers in `finally`; the worker owns final browser quit. Add
   deterministic regression tests and browser fixtures as appropriate.

`bots/examples/example_bot.py` is a minimal example. Registry tests prove a third bot
can be added without changes to API, worker, database or frontend. A different browser
engine needs both a factory and compatible page adapters; Selenium bots use Selenium APIs.

Compose gates startup on migrations and retains PostgreSQL's named volume. Secrets
enter through environment variables. API/UI/viewers bind loopback; the API is trusted-use
and unauthenticated. Request payloads, credentials, cookies, tokens, headers and raw
exceptions are excluded from worker logs and stored errors. Opt-in diagnostics use
allowlisted metadata in a private volume; only curated sanitized evidence belongs in Git.
