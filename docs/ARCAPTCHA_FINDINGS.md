# Arcaptcha findings

## Verified behavior

On 6 November 2026, the optional UC Headful worker completed **seven consecutive
genuine successful queued demo logins**, with **human CAPTCHA completion**. Each row
contains a real `getChallengeID` value and `browser_login_http_200_expected_msg`
evidence. The [sanitized PostgreSQL export](evidence/uc-live-runs.json) includes all
seven rows and the adjacent UC Headless blocks. 

The export was read from the existing application database during cleanup. Human
completion is confirmed by the operator's account; the database records outcomes,
not human input events or historical image identity. This is an observed sample,
not a general success-rate estimate or evidence of automated solving.

UC Headless was explicitly rejected as `BLOCKED / CAPTCHA_SITE_BLOCKED / captcha`,
including the run at 13:42:31 Tehran time. Standard Selenium Grid Headful and Headless
were also blocked. [Grid evidence](evidence/grid-blocking.json) retains earlier queued
negative outcomes and the 5 November Docker Grid comparison. In that comparison,
both modes initialized without rejection during a five-second no-click window;
one ordinary checkbox click caused one create POST/201 followed by the blocked
warning. Neither answer nor login followed. The provider's policy reason is unknown;
HTTP 201 from challenge creation is not CAPTCHA acceptance.

An [earlier host UC success trace](evidence/uc-host-success.json) separately records
one legitimate getter ID, one login POST, HTTP 200, the expected application message,
and cleanup. It used Selenium 4.52.0 / Chrome 156 in an isolated host environment.
The integrated Docker images retain Selenium 4.31.0 / Chrome 155. Host results alone
do not validate that different deployment; current Docker checks are in [TESTING](TESTING.md).

## What success means

The bot reads the widget's named `getChallengeID` getter, validates the ID and commits
it before human waiting or credential entry. The public widget's create-query `id`
is a `bowman_id`, not trusted challenge identity. A legitimate hidden token and selected
checkbox permit submission; final success requires the browser's actual POST
`/api/login` to return HTTP 200 with JSON `msg` exactly
`You are logged in successfully!`. Missing or ambiguous evidence cannot succeed.

Headful Chrome on Xvfb remains **Headful**, even inside Docker. The noVNC operator
completes the ordinary CAPTCHA. No automated solver, token injection, forged success
response or verification bypass is implemented. UC is a local browser backend, not a
Grid capability. No service vulnerability or sole detection cause was established.

## Reproduction and evidence scope

Deploy the UC overlay using the [README](../README.md#select-the-uc-backend), select
`arcaptcha-demo` and `HEADFUL`, and complete the normal CAPTCHA on port 7901 during
`WAITING_FOR_HUMAN`. Inspect the run through `GET /api/v1/runs/<run-id>` for its
persisted challenge ID, terminal state and evidence. Headless selects actual headless
Chrome and may return the known block. Live attempts are manual, opt-in evaluations;
cleanup does not repeat them.

For standard Grid metadata diagnosis, the retained diagnostic tool makes no login
submission and exports only allowlisted metadata. It requires explicit enablement:

```bash
docker compose exec -e ARCAPTCHA_DIAGNOSTICS_ENABLED=true worker \
  python -m app.bots.arcaptcha.diagnose --mode HEADLESS
```

That command uses the default Grid worker. In a UC container use
`/opt/bot-venv/bin/python` instead of `python`; the diagnostic still uses Grid. Production UC
worker diagnostics instead identify the selected backend. Detailed provenance and
failure boundaries are described in [ARCHITECTURE](ARCHITECTURE.md).

Only sanitized run metadata, diagnostic summaries and one success trace are retained.
No profiles, credentials, cookies, tokens or raw network captures are submission evidence.
Upstream DOM and acceptance policy can change; these observations do not guarantee
future success or explain why the provider blocked another configuration.
