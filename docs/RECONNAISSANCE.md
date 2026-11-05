# Arcaptcha reconnaissance — November 4, 2026

## Evidence and scope

The supplied manual DevTools inspection is a starting observation. During this audit,
HTTPS retrieval of the live demo and its **current public JavaScript** succeeded with
network permission. Live Selenium runs in both modes later reached the real checkbox and were explicitly
blocked by the widget. The named getter existed and matched the observed widget,
but returned undefined. No successful CAPTCHA/login or live ID persistence is claimed.
See `docs/evidence/live-site-blocked.png` and TEST_RESULTS.

Public sources retrieved:

- https://demo.arcaptcha.co/ (references `/assets/index-IlKv7DUw.js`)
- https://demo.arcaptcha.co/assets/index-IlKv7DUw.js
  SHA256 `c57fd3786fcad40fcc2ff1b71cc62e62ac91d8b2b0de5c64f48a0af9325c9597`
- https://widget.arcaptcha.ir/1/api.js
  SHA256 `f1a3c2641cd7114bb773aca95d07a5836acac25c9a1dc1b72f6736340567e64c`
- https://widget.arcaptcha.ir/dist/checkbox.js
  SHA256 `eb22361cc55ef85e92d5d75b53741531850ea645af1c3725354878de6c569afc`

These are mutable URLs. Hashes document exactly which code informed the adapter;
they are not pinned application dependencies. No CAPTCHA payloads, tokens, cookies,
or response recordings are committed.

## Interaction and solved state

The demo bundle defines `#email`, `#password`, a form Login button, and demo/demo
credentials. Its Login click handler prevents the default form action and makes an
Axios JSON POST to the demo's `/api/login`. Thus the email input's HTML validation
must not be reimplemented in Python to reject `demo`.

The current checkbox bundle defines **`#arc-checkbox`**, with a localized aria-label,
and nested `#input-checkbox`. The supplied manual snapshot had **`#ar-checkbox`**.
Both known wrapper IDs are supported, without relying on a generated widget ID or
clicking the hidden nested checkbox. No iframe handling is needed by this inspected
implementation; an iframe-based future release requires renewed reconnaissance.

The widget renders a selected nested checkbox when its solved state becomes true.
The adapter requires that selected DOM state **and** a nonempty legitimate hidden
`#arcaptcha-token` value. Neither needs to be displayed. These are submit prerequisites,
never final login evidence. No widget state or token is written by production code.

## Challenge identifier provenance

**The create-request `id` must not be used as challenge_id.** In the inspected checkbox
bundle, the create function receives a `bowman_id` from collection logic and places it
in that URL. This does not establish that it equals the server's challenge identifier.
The network adapter records only whether that candidate request was observed; it never
persists its query value.

The bundle separately handles the decoded create result's `content`, commits it as
`challenge`, and registers a **read-only `getChallengeID` function** for each widget.
That getter returns the selected widget's **`challenge.challenge_id`**. The adapter
locates the widget via `.arcaptcha-vue` and its actual `data-widget-id`, checks that
there is an own registry entry, and calls that named getter. It does not call a token
accessor, decode encrypted responses, guess request internals, or hardcode an ID.
This is explicit semantic evidence, stronger than the unrelated query UUID.

A fallback accepts only DOM fields explicitly named `challenge_id` or
`data-challenge-id`, validates bounded identifier syntax, and records the source.
Arbitrary legacy challenge CSS and iframe query guesses are no longer trusted.
Missing/changed getter or invalid identifier fails with `CHALLENGE_ID_UNAVAILABLE`.
The callback commits the identifier before credentials, CAPTCHA waiting or submission.
The initial challenge remains immutable if a later manual widget reset creates another.

## Final login evidence

The network observer is enabled before navigation and binds to the top document's
frame ID afterward. It accepts only a POST to the exact demo origin and `/api/login`,
with no query, from that frame, and correlates response/loading events by the browser's
request ID. It ignores request bodies and headers. Duplicates are deduplicated;
redirects, multiple login requests, failed transport and unparseable bodies fail closed.

After loading finishes, `Network.getResponseBody` reads the actual browser response.
Success requires **HTTP 200 and JSON `msg` exactly equal to the observed successful
login message**. Other application messages reject; missing/unrecognized evidence
cannot succeed. No Python HTTP login request is made. A manual in-flight login
suppresses bot submission even before its response arrives.

The demo's success toast is driven by the Axios response message, as confirmed by
its bundle. Production currently uses network JSON evidence, not a potentially stale
or cosmetic toast. Legacy success/failure CSS settings are accepted but ignored.

## Selenium transport choice

Inspected the installed/pinned **Selenium 4.31.0 wheel**: `webdriver.Remote` exposes
`execute_cdp_cmd` and `client_config`; its `common/bidi/network.py` module is absent.
There is no supported response-body BiDi surface in this pin. The Chrome-specific
adapter therefore uses performance logs and remote CDP through WebDriver's HTTP
endpoint, without a direct host-only debugger connection. See also Selenium's
[4.28 release notes](https://www.selenium.dev/blog/2025/selenium-4-28-released/) for
remote CDP support. Tests must prove the deployed Grid path; local driver API success
alone is not proof of the Docker Grid configuration.

The configured Selenium image tag is listed in the project's
[official release](https://github.com/SeleniumHQ/docker-selenium/releases/tag/4.51.0-20261010).
Image existence and successful pull/deployment are separate claims.

## Rechecking after upstream changes

1. Start Headful through the worker, view noVNC, and inspect the actual wrapper.
2. Confirm the named getter still reads the server-created challenge state before solving.
3. Confirm immediate DB persistence while CAPTCHA/login are still pending.
4. Complete the challenge normally; allow one Login click. Observe actual HTTP status
   and application message. Do not export tokens, credentials or full HAR files.
5. Test rejected credentials as well. Run the fixture suite before changing the adapter.

For a broken metadata integration, the smallest useful sanitized artifact is the
public getter definition plus its source URL/version and the names/types of the widget
registry and challenge field. An entire HAR, cookies or a CAPTCHA token is unnecessary.


## Actual live outcome

The visible `.arc-widget-error` displayed the explicit English blocked warning. The
inspected bundle emits that warning for its blocked challenge type, hides the checkbox,
and rejects creation without committing a challenge. Production recognizes the
observed English/Persian blocked warning as `CAPTCHA_SITE_BLOCKED` (`BLOCKED`, stage
`captcha`), including when it occurs before an ID exists. This negative signal never
counts as positive verification evidence. Real queued runs recorded that outcome in
both modes; no fabricated ID or login submission was used to proceed past the block.
