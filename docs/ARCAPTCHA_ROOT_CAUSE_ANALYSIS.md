# ARCaptcha blocking: root cause analysis — November 5, 2026

## Executive summary

**The observed failure is an explicit site rejection during challenge creation, after
one ordinary checkbox click.** Both Headful and Headless reproduce it. In neither
mode was a block seen during the five-second initialized, no-click observation window.

The browser sent `POST https://api.arcaptcha.ir/arcaptcha/api/create`, received **201**,
then the widget displayed its blocked warning. No answer or login request followed.
HTTP 201 is transport/application endpoint evidence, not CAPTCHA acceptance.

**The site's policy reason remains unknown.** The evidence does not establish Selenium
fingerprint detection, IP reputation, an account problem, or a client/Grid compatibility
bug. No evasion, proxy rotation, forged tokens, security-flag changes, or solver services
were introduced. `BLOCKED / CAPTCHA_SITE_BLOCKED / captcha` remains the correct result.

## Reproduction and scope

Four fresh sessions were executed sequentially through the existing Docker Grid. Each
received a fresh run UUID and a private JSONL artifact. These were diagnostic sessions,
not production queue rows, and did not fill credentials or submit Login. The worker's
normal instrumentation instead uses the existing queued run UUID; an integration test
verifies that the JSONL terminal record matches the actual persisted terminal status.

The comparison ran the instrumented source from `/tmp/arcaptcha-debug` in the existing
worker container. This left the deployed worker process, application database and image
unchanged during observation. No failed live case was retried. Two clicks total were
performed: one each in the explicitly requested B/D cases.

[Four-case manifest](evidence/arcaptcha-20261105/comparison.jsonl) ·
[Computed timelines/status summary](evidence/arcaptcha-20261105/summary.json).

## Actual environment

- Python Selenium binding: **4.31.0**.
- Selenium Grid: **4.51.0** (revision prefix `35c5fab`).
- Chrome and ChromeDriver: **155.0.8059.79**, matching exactly, Linux amd64.
- CDP capability version: **155.0.8059.79**; page-load strategy `normal`;
  `acceptInsecureCerts=false`.
- Project launch options remain `--window-size=1360,900`, plus `--headless=new` only
  in Headless. The actual existing Grid session also reports `--enable-automation`
  and `--no-sandbox`; those existing launcher arguments were observed, not added or
  modified by this work. No automation indicator was hidden.
- No WebDriver proxy configuration/argument or proxy environment variable was present
  in the observed worker sessions. This does not measure transparent host/VPN routing
  or prove container and desktop browser egress equivalence.
- All three public target hosts resolved to `185.143.233.133` and `185.143.234.133`.
- Navigation and widget JavaScript returned **200**; no resource `loadingFailed`
  events or TLS/DNS/connection-error codes were recorded in any comparison case.
- The existing API, frontend, PostgreSQL and Selenium services were healthy, and the
  worker was running. The November 4 registry/startup restriction is historical;
  it is not the cause of today's running stack's CAPTCHA rejection.

The desktop's installed Chrome reports 156.0.8078.79. The user's previously successful
normal Chrome login is user-supplied historical evidence; that profile/login was not
re-executed. It is not a matched browser-version/profile/egress control. Case A proves
that the current Selenium Headful page/widget initialize before any click.

The binding and Grid have different release versions, but matching Chrome/driver,
successful RemoteWebDriver commands, working CDP/performance logs, registered widget
metadata and passing real Grid fixtures provide no evidence of a compatibility defect
causing this rejection. Selenium's [Chrome documentation](https://www.selenium.dev/documentation/webdriver/browsers/chrome/)
explains the browser/driver major-version requirement; equality of binding and Grid
release numbers is not inferred as a repair requirement.

## Checkpoint timeline and four-case comparison

Times are milliseconds relative to each diagnostic run start, including browser creation
and environment checks. `elapsed_ms` is the time an observation was recorded;
`occurred_elapsed_ms` on network events uses Chrome event timestamps. A buffered log
entry appearing after PAGE_LOADED in file sequence does not imply the request began
then. DOM rejection time is the first polling observation, not an exact paint timestamp.

1. **A — Headful, no click: executed; NO_REJECTION_OBSERVED.** PAGE_LOADED 3413.639;
   WIDGET_DETECTED 3437.192; finished 8768.177 after the five-second observation window.
   Zero create/answer/login requests; no site block or severe console error.
2. **B — Headful, one ordinary click: executed; SITE_REJECTION.** PAGE_LOADED 6225.432;
   WIDGET_DETECTED 6253.262; BEFORE_CHECKBOX_CLICK 6312.132;
   AFTER_CHECKBOX_CLICK 6338.947. Create request occurred at 6736.229; its HTTP 201
   response occurred at 7345.931. SITE_BLOCK_DETECTED at 7484.585, stage
   `challenge_creation`, **1145.638 ms after the completed click**. Finished 7558.755.
3. **C — Headless, no click: executed; NO_REJECTION_OBSERVED.** PAGE_LOADED 3970.412;
   WIDGET_DETECTED 3993.525; finished 9152.326 after the five-second observation window.
   Zero create/answer/login requests; no site block or severe console error.
4. **D — Headless, one ordinary click: executed; SITE_REJECTION.** PAGE_LOADED 4844.975;
   WIDGET_DETECTED 4866.529; BEFORE_CHECKBOX_CLICK 4907.076;
   AFTER_CHECKBOX_CLICK 4931.677. Create request occurred at 5245.182; its HTTP 201
   response occurred at 5877.729. SITE_BLOCK_DETECTED at 6144.462, stage
   `challenge_creation`, **1212.785 ms after the completed click**. Finished 6220.783.

B/D each made exactly one observed create POST, zero answer POSTs, and zero login POSTs.
No CHALLENGE_ID_OBSERVED, CAPTCHA_SOLVED, LOGIN_SUBMITTED or LOGIN_RESPONSE_OBSERVED
checkpoint was emitted. No verification success is claimed. No-click observation is
bounded evidence, not proof that a longer-lived session could never be rejected.

The comparison captured an earlier instrumentation revision: PAGE_LOADED's initial
checkbox/widget flags were not yet probed and must not be interpreted as measured
absence. The later WIDGET_DETECTED/CHECKBOX_LOCATED checkpoints are measured. Final
code now probes those flags before PAGE_LOADED. The request timeline and rejection
findings above do not depend on the initial defaults. Network entries in those first
artifacts can inherit the preceding `checkbox` stage; timestamps and SITE_BLOCK_DETECTED
establish the actual transition. Final code forwards the current page stage to network events.

## Browser/network observations and classification

`CAPTCHA_SITE_BLOCKED` is raised only when a displayed `.arcaptcha-vue .arc-widget-error`
contains the widget's known English/Persian blocked prefix. It is not inferred from
HTTP status, a missing selector, a missing ID, a generic red error, or a timeout.

The current public widget source described in [RECONNAISSANCE](RECONNAISSANCE.md)
has an explicit blocked challenge branch that displays the observed message. The
recorded DOM signal and create-response sequence establish that the normal widget flow
rejected the session. The encoded create payload/body was not decoded or guessed;
its internal status/reason is not claimed as directly observed JSON evidence.

B/D each had one severe console entry when logs were drained at the end; A/C had none.
Free-form console messages and stacks are intentionally discarded. Stored error
categories/source URLs are sanitized. These entries are not evidence that a JavaScript
bug caused the policy rejection; console observation order also is not error occurrence order.

Infrastructure is classified independently:

- Explicit displayed blocked warning: `CAPTCHA_SITE_BLOCKED`, BLOCKED (`SITE_REJECTION`).
- Failed relevant browser requests: `CAPTCHA_NETWORK_ERROR` (`NETWORK_ERROR`).
- Other displayed widget error when readiness/metadata cannot be obtained:
  `CAPTCHA_WIDGET_ERROR` (`WIDGET_ERROR`).
- Unready widget: `WIDGET_NOT_READY`, TIMED_OUT. Loaded widget with missing control:
  `CHECKBOX_TIMEOUT`, TIMED_OUT. Malformed CSS: `CHECKBOX_SELECTOR_INVALID` (`SELENIUM_ERROR`).
- Navigation timeout remains NAVIGATION_TIMEOUT; WebDriver/transport exceptions remain
  separately classified. None of those emits SITE_BLOCK_DETECTED without its DOM evidence.

## Confirmed findings versus unresolved hypotheses

Confirmed:

- Navigation, initialization and the visible checkbox work through the actual Grid.
- No pre-click rejection was observed in these four bounded cases.
- Both ordinary click cases lead to a completed create HTTP exchange and explicit widget rejection.
- Rejection occurs before obtaining an ID, solving, answering or submitting the login form.
- Headless mode alone cannot explain rejection: Headful is also rejected.
- There is no observed browser/driver version mismatch, DNS failure, TLS error or resource
  transport failure explaining these cases.

Unresolved hypotheses, **not conclusions**:

- Site risk/policy handling of automated sessions or fresh browser profiles.
- Container/desktop differences in browser release, session history or network egress/reputation.
- Other site-side rules whose decision inputs are not exposed by the observed interface.

Determining which policy input caused rejection needs supported vendor/server-side
information or a legitimately matched manual control. Fingerprint manipulation, hiding
webdriver, changing IPs, bypassing browser security or decoding guessed encrypted
internals would neither be justified evidence nor an allowed repair.

## Targeted implementation repairs

- Added explicit widget readiness before click: the matching widget must register its
  supported getter and the real visible wrapper must be enabled.
- Added site-block checks after navigation, during initialization and immediately before
  click. An already rejected session is not clicked. A rejected click is not retried.
- Added separate network/widget/selector failure classification without weakening final
  server-backed success verification.
- Added optional generic checkpoint callback to BotContext; REST responses and bot
  registration remain compatible. Engine-specific diagnostics remain in browser infrastructure.
- Added opt-in private JSONL artifacts linked to the real worker run UUID, bounded event
  capture, immediate flush, sanitized console/network/environment information and final
  persistence acknowledgement. Diagnostic failures log static warnings without changing
  the underlying bot outcome. No diagnostic payload enters production result_metadata.
- LOGIN_SUBMITTED is emitted for the correlated actual browser POST, including manual
  submission, rather than assuming a button click produced a request.
- Added configuration, private worker volume/permissions and an idle-Grid comparison CLI.
- Fixed the deterministic HTTP fixture's secure-context assumption: its server supplies
  a fresh fixture UUID instead of requiring browser crypto.randomUUID on a private HTTP
  IP. This is a fixture repair, not the reason for the real site's rejection.

These repairs improve execution ordering and diagnosis. **They do not resolve the site's block.**

## Tests and deployment validation

- Full regression suite inside the existing Docker network, with a new disposable
  database: **102 passed, 2 skipped, 1 warning, 10.24 s**. Skips are explicit live-login
  success and separate UI acceptance; this work instead executed the four controlled
  live cases above. Production history was not used as a test schema.
- Deterministic real Grid/browser fixtures in Headless: **5 passed, 2 deselected, 8.85 s**.
- Headful real Grid fixtures: **5 passed, 2 deselected, 8.91 s**. Ruff and mypy passed;
  mypy checked **29 source files**. Compilation and Compose configuration passed.
  Raw outputs are saved alongside the evidence.
- Native pytest without integration URLs: **81 passed, 20 skipped** at the initial
  instrumentation stage. It is not described as a full integration pass.
- An initial native attempt with a host HTTP fixture address failed four browser
  navigations (4 failed, 98 passed, 2 skipped). The deployed browser could not reach
  that fixture server. Running fixtures inside Docker resolved this separate test
  infrastructure problem; it was never called a site rejection.
- Existing Starlette/AnyIO deprecation warning remains; it did not fail the suite.
- Compose configuration parses. The first standard worker build failed after direct
  PyPI timeouts; a public dependency mirror was used for the subsequent build. The
  mirror build **succeeded** with identical dependency pins. The worker alone was
  recreated after confirming zero active runs. Diagnostics remained disabled by default;
  the dedicated artifact volume was writable. Deployed page/diagnostic code hashes match
  the repository and API readiness returned `ready`. Other services and history were retained.
- No frontend source or browser launch flag was modified in this task.

## Enable, inspect and disable diagnostics

Default: `ARCAPTCHA_DIAGNOSTICS_ENABLED=false`. Native output defaults to `diagnostics/`
(or `ARCAPTCHA_DIAGNOSTICS_DIRECTORY`). Compose uses a dedicated local named volume
at `/srv/diagnostics`; files are created exclusively with mode 0600 and flushed per
record. Capture is bounded to 1000 records plus RUN_FINISHED; this is diagnostic
sampling, not a full HAR. The directory is not served by the UI or included in image build contexts.

From the repository root, after building the worker:

```bash
docker compose build worker
# If your dependency registry requires a mirror, use the existing supported build arg:
# docker compose build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ worker

# Enable only for future normal worker jobs; use the existing UI to launch one run.
ARCAPTCHA_DIAGNOSTICS_ENABLED=true docker compose up -d --no-deps worker

# On an idle Grid, perform the four observations. This makes two clicks, no logins.
docker compose run --rm --no-deps -e ARCAPTCHA_DIAGNOSTICS_ENABLED=true \
  worker python -m app.bots.arcaptcha.diagnose --compare --observe-seconds 5

# Or run just one selected case; no automatic retry:
docker compose run --rm --no-deps -e ARCAPTCHA_DIAGNOSTICS_ENABLED=true \
  worker python -m app.bots.arcaptcha.diagnose --case A --observe-seconds 5

mkdir -p diagnostics
docker compose cp worker:/srv/diagnostics/. ./diagnostics/
# Worker job artifact: diagnostics/<run-id>.jsonl
# Comparison output maps its fresh diagnostic run IDs to filenames.

# Disable recording again; retained local artifacts are not deleted.
ARCAPTCHA_DIAGNOSTICS_ENABLED=false docker compose up -d --no-deps worker
```

Do not run comparisons while another job owns the single browser slot. `--mode` remains
supported for a single observation; `--no-click` selects observation without interaction.
The CLI requires the explicit diagnostics flag. It never submits credentials or Login.

Files include UTC/elapsed times, mode, allowlisted compatibility data, readiness,
observed interaction/rejection, sanitized request/status sequence and console taxonomy.
They exclude passwords, cookies, auth headers, tokens, raw payloads, browser storage,
raw fingerprint data, URL query strings and full capabilities. Unknown console text
is discarded rather than risking incomplete secret redaction. Ordinary artifacts stay
ignored by git; the four reviewed/sanitized comparison artifacts are explicitly curated
under `docs/evidence/arcaptcha-20261105/`.

The remaining external blocker is the site's create-stage rejection. An HTTP 201 or
code changes alone do not establish a solved CAPTCHA or a successful live login.
