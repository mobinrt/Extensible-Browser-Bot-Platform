# Architecture and guarantees

The React console calls FastAPI, which inserts a QUEUED PostgreSQL row and returns
202. A separate worker claims one row using `SELECT FOR UPDATE SKIP LOCKED`, starts
a fresh RemoteWebDriver session, runs the registered bot and stores a terminal result.
Bots receive a typed context, not ORM sessions or HTTP request objects.

## Ownership and transactions

Claiming, challenge updates, heartbeat, human-wait transitions and finalization each
commit in independent transactions. `record_challenge` returns only after its transaction
commits; later credential failures cannot roll it back. An already saved ID can be
repeated idempotently, but cannot be replaced with another ID or silently truncated.
Every active write checks owner, active status and an unexpired lease. An expired
owner cannot revive a lease. Terminal transitions use `finish`, record timestamps and
clear ownership; they cannot be made through the transient-state method.

A running worker expires abandoned leases to TIMED_OUT. It never requeues jobs with
possibly completed external effects. With no workers, the durable rows wait until a
worker resumes. Multiple workers can safely claim separate jobs, though the configured
Grid has one browser slot. No exactly-once guarantee for remote form effects is made.

## Time and cleanup

Run deadlines are checked between operations and after bot return. WebDriver's HTTP,
page and script timeouts are 30 seconds. A blocked command can extend the logical
run deadline by its transport timeout; this is bounded best-effort execution, not
process-level termination. Database connect, statement, pool and TCP liveness settings
bound common network stalls. Heartbeats stop on ownership loss/database errors.

The page observer closes in a bot `finally`; the worker always attempts `driver.quit`
and then stores a categorized outcome. Startup after a driver has been created also
attempts cleanup on setup errors. A crash before session creation returns can leave
an orphan unknown to Python; Grid's idle session timeout is a secondary cleanup bound.
Database outages may prevent final persistence; a subsequent worker's lease reaper
records an indeterminate timeout without replay.

## Evidence boundaries

The Arcaptcha adapter clicks the visible wrapper and reads the named widget
`getChallengeID` getter, explicitly registered against server-created
`challenge.challenge_id`. It does not repurpose the create request's `bowman_id` query
value, or read a hidden token as a challenge ID. Named DOM metadata is a validated fallback.
The first observed ID is committed immediately; subsequent manual resets retain it.

Solved state requires a legitimate nonempty hidden token and selected nested checkbox.
Final success additionally requires the browser's POST `/api/login`, matched by exact
origin/path/method/top frame and request ID, HTTP 200 and expected JSON application
message. Unknown states fail closed. An observed in-flight manual submission suppresses
automatic submission. An ambiguous submit click cannot be retried by the stale-element wait.

Chrome-specific performance/CDP logic belongs in `infrastructure/browser/network.py`;
it is absent from domain contracts. Selenium 4.31's installed surface supports remote
CDP but lacks the newer BiDi network body reader needed here. The actual deployed Grid
path remains a separate integration gate. No CSS setting can manufacture login success.

## Extensibility and deployment

The registry exposes bot descriptors and constructs fresh implementations. A new bot
only needs a protocol implementation, factory registration and tests; API/storage/UI
remain unchanged. A different browser engine needs its own factory **and** compatible
page adapter; replacing a factory cannot translate Selenium element APIs.

Compose uses six services, a one-shot migration gate and a named Postgres volume.
Secrets enter through environment variables; raw DB password components are escaped
with SQLAlchemy URL construction. API, UI and noVNC bind loopback. The API is trusted-use,
unauthenticated, and has no arbitrary target/credential submission endpoints. Request
payloads, tokens, headers and raw exceptions are excluded from worker logs and stored
errors. Only allowlisted result evidence/codes and challenge metadata reach history.
